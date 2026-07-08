"""
Krishna Intelligence — Forensic CCTV Video Analysis Suite
Version 14.0 Pro Enterprise

Features:
  - Secure login: the app authenticates against the Krishna web panel on
    startup; sessions stay valid for 7 days, then login is required again
  - Device audit: PC name / OS / Windows user is logged on the server for
    every login (visible in the admin panel)
  - Batch CCTV video analysis with YOLOv8 detection + tracking (GPU/CPU auto)
  - Smart filters: object type (Person / Vehicle / Animal) and dominant color
  - Unique-ID evidence capture (one photo per tracked object, per video)
  - Image enhancement (fast CLAHE + sharpening) and Night Vision mode
  - Live evidence gallery, timeline log, and live statistics
  - Case management: per-case evidence folders on the PC
  - Reports live ONLY on the web panel: after every scan (even aborted)
    the report (PDF + JSON, never the videos) is uploaded automatically —
    no local report copies are kept — and a WhatsApp message with the view
    link goes to the operator's registered mobile number; failed uploads
    stay queued and are re-sent when internet returns
  - Forgot Password from the login screen (WhatsApp OTP)
  - Pause / Resume / Abort controls, responsive video display
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image
import cv2
import os
import sys
import subprocess
import shutil
import threading
import time
import numpy as np
import queue
import json
import logging
import traceback
import platform
import getpass
import webbrowser
import requests
from datetime import datetime, timedelta
from collections import defaultdict
import warnings

warnings.filterwarnings('ignore')

APP_NAME = "Krishna Intelligence"
APP_VERSION = "v14.0 Pro Enterprise"

CLIENT_CONFIG_FILE = "client_config.json"
SESSION_DIR = os.path.join(os.path.expanduser("~"), ".krishna_intelligence")
SESSION_FILE = os.path.join(SESSION_DIR, "session.json")

# ---------------------------------------------------------------- appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

BG_DARK = "#0A0E1A"
PANEL_BG = "#111827"
HIGHLIGHT = "#F97316"
ACCENT = "#06B6D4"
DANGER = "#EF4444"
SUCCESS = "#10B981"
WARNING = "#F59E0B"
GOLD = "#FCD34D"
PURPLE = "#8B5CF6"

# ------------------------------------------------------------------- logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("krishna_intelligence.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(APP_NAME)


def open_path(path):
    """Open a file or folder with the OS default application (cross-platform)."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: attribute exists on Windows
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        log.warning("Could not open %s: %s", path, exc)


# ============================================================== auth client =
class AuthClient:
    """Talks to the Krishna web panel: login, session verify, report upload."""

    def __init__(self):
        self.server_url = ""
        self.token = ""
        self.expires_at = None          # datetime
        self.profile = {}               # name, username, police_station, mobile
        self._load_client_config()

    # ------------------------------------------------------------- config --
    def _load_client_config(self):
        try:
            with open(CLIENT_CONFIG_FILE, encoding="utf-8") as f:
                cfg = json.load(f)
            self.server_url = cfg.get("server_url", "").rstrip("/")
        except (OSError, ValueError):
            self.server_url = ""

    def save_client_config(self, server_url):
        self.server_url = server_url.rstrip("/")
        try:
            with open(CLIENT_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"server_url": self.server_url}, f, indent=2)
        except OSError as exc:
            log.warning("Could not save client config: %s", exc)

    # ------------------------------------------------------------ session --
    def load_saved_session(self):
        """Return True when a stored (unexpired) 7-day session exists."""
        try:
            with open(SESSION_FILE, encoding="utf-8") as f:
                data = json.load(f)
            expires = datetime.fromisoformat(data["expires_at"])
            if datetime.now() >= expires:
                return False
            if data.get("server_url") and not self.server_url:
                self.server_url = data["server_url"]
            self.token = data["token"]
            self.expires_at = expires
            self.profile = data.get("profile", {})
            return bool(self.token)
        except (OSError, KeyError, ValueError):
            return False

    def _save_session(self):
        try:
            os.makedirs(SESSION_DIR, exist_ok=True)
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "token": self.token,
                    "expires_at": self.expires_at.isoformat(timespec="seconds"),
                    "profile": self.profile,
                    "server_url": self.server_url,
                }, f, indent=2)
        except OSError as exc:
            log.warning("Could not save session: %s", exc)

    def clear_session(self):
        self.token = ""
        self.profile = {}
        self.expires_at = None
        try:
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
        except OSError:
            pass

    # ------------------------------------------------------------- device --
    @staticmethod
    def device_info():
        try:
            user = getpass.getuser()
        except Exception:
            user = "unknown"
        return {
            "device_name": platform.node() or "unknown",
            "device_os": f"{platform.system()} {platform.release()}",
            "device_user": user,
        }

    # ---------------------------------------------------------- API calls --
    def _post(self, action, data=None, files=None, timeout=20):
        url = f"{self.server_url}/api.php?action={action}"
        resp = requests.post(url, data=data or {}, files=files, timeout=timeout)
        resp.raise_for_status()
        return resp.json()

    def login(self, username, password):
        """Returns (ok, message)."""
        if not self.server_url:
            return False, "Server URL is not set."
        payload = {"username": username, "password": password}
        payload.update(self.device_info())
        try:
            out = self._post("login", payload)
        except requests.RequestException as exc:
            log.error("Login request failed: %s", exc)
            return False, "Cannot reach the server. Check internet / server URL."
        except ValueError:
            return False, "Invalid response from server."
        if not out.get("ok"):
            return False, out.get("error", "Login failed.")
        self.token = out["token"]
        self.expires_at = datetime.now() + timedelta(days=int(out.get("valid_days", 7)))
        self.profile = out.get("profile", {})
        self._save_session()
        return True, "Login successful."

    def verify(self):
        """Validate the saved token. Returns 'ok', 'invalid' or 'offline'."""
        if not self.token or not self.server_url:
            return "invalid"
        try:
            out = self._post("verify", {"token": self.token,
                                        **self.device_info()}, timeout=12)
        except requests.RequestException:
            return "offline"
        except ValueError:
            return "invalid"
        if out.get("ok"):
            self.profile = out.get("profile", self.profile)
            self._save_session()
            return "ok"
        return "invalid"

    def forgot_request(self, username):
        """Ask the server to send a password-reset OTP on WhatsApp."""
        if not self.server_url:
            return False, "Server URL is not set."
        try:
            out = self._post("forgot_request", {"username": username})
        except requests.RequestException:
            return False, "Cannot reach the server. Check internet."
        except ValueError:
            return False, "Invalid response from server."
        if out.get("ok"):
            return True, out.get("mobile_hint", "your WhatsApp number")
        return False, out.get("error", "Request failed.")

    def forgot_reset(self, username, otp, new_password):
        """Reset the password using the WhatsApp OTP."""
        try:
            out = self._post("forgot_reset", {
                "username": username, "otp": otp,
                "new_password": new_password})
        except requests.RequestException:
            return False, "Cannot reach the server. Check internet."
        except ValueError:
            return False, "Invalid response from server."
        if out.get("ok"):
            return True, "Password changed."
        return False, out.get("error", "Reset failed.")

    def upload_report(self, case_id, pdf_path, json_path, stats):
        """Upload the case report (PDF + JSON only). Returns (ok, link_or_error)."""
        if not self.token:
            return False, "Not logged in."
        try:
            files = {}
            handles = []
            for field, path in (("report_pdf", pdf_path),
                                ("report_json", json_path)):
                if path and os.path.exists(path):
                    fh = open(path, "rb")
                    handles.append(fh)
                    files[field] = (os.path.basename(path), fh)
            if not files:
                return False, "No report files to upload."
            try:
                out = self._post("upload_report", {
                    "token": self.token,
                    "case_id": case_id,
                    "persons": stats.get("persons", 0),
                    "vehicles": stats.get("vehicles", 0),
                    "total": stats.get("total", 0),
                }, files=files, timeout=120)
            finally:
                for fh in handles:
                    fh.close()
        except requests.RequestException as exc:
            log.error("Report upload failed: %s", exc)
            return False, "Upload failed — server not reachable."
        except ValueError:
            return False, "Invalid response from server."
        if out.get("ok"):
            return True, out.get("view_url", "")
        return False, out.get("error", "Upload rejected by server.")


# ====================================================== forgot password ====
class ForgotPasswordDialog(ctk.CTkToplevel):
    """Password reset via WhatsApp OTP: username -> OTP -> new password."""

    def __init__(self, parent, auth):
        super().__init__(parent)
        self.auth = auth
        self.title("Forgot Password")
        self.geometry("400x440")
        self.configure(fg_color=BG_DARK)
        self.resizable(False, False)
        self.grab_set()

        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 200
        y = (self.winfo_screenheight() // 2) - 220
        self.geometry(f"+{x}+{y}")

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=25, pady=15)
        ctk.CTkLabel(frame, text="🔑 Forgot Password",
                     font=("Arial Black", 18),
                     text_color=HIGHLIGHT).pack(pady=(5, 10))

        self.user_entry = ctk.CTkEntry(frame, height=36,
                                       placeholder_text="Username")
        self.user_entry.pack(fill="x", pady=4)
        self.btn_otp = ctk.CTkButton(frame, text="📲 Send OTP on WhatsApp",
                                     height=38, fg_color=ACCENT,
                                     hover_color="#0891B2",
                                     command=self._send_otp)
        self.btn_otp.pack(fill="x", pady=(4, 10))

        self.otp_entry = ctk.CTkEntry(frame, height=36,
                                      placeholder_text="6-digit OTP")
        self.otp_entry.pack(fill="x", pady=4)
        self.new_pass_entry = ctk.CTkEntry(frame, height=36, show="•",
                                           placeholder_text="New Password (min 6)")
        self.new_pass_entry.pack(fill="x", pady=4)
        self.btn_reset = ctk.CTkButton(frame, text="✅ Reset Password",
                                       height=40, fg_color=SUCCESS,
                                       hover_color="#059669",
                                       command=self._reset)
        self.btn_reset.pack(fill="x", pady=(8, 4))

        self.lbl_msg = ctk.CTkLabel(frame,
                                    text="Enter your username and press Send OTP.",
                                    font=("Arial", 11), wraplength=330,
                                    text_color="gray")
        self.lbl_msg.pack(pady=8)

    def _send_otp(self):
        username = self.user_entry.get().strip()
        if not username:
            self.lbl_msg.configure(text="Enter your username.", text_color=DANGER)
            return
        self.btn_otp.configure(state="disabled", text="Sending...")

        def worker():
            ok, result = self.auth.forgot_request(username)
            self.after(0, lambda: self._otp_sent(ok, result))

        threading.Thread(target=worker, daemon=True).start()

    def _otp_sent(self, ok, result):
        self.btn_otp.configure(state="normal", text="📲 Send OTP on WhatsApp")
        if ok:
            self.lbl_msg.configure(
                text=f"OTP sent on WhatsApp to {result}. Valid 5 minutes.",
                text_color=SUCCESS)
        else:
            self.lbl_msg.configure(text=result, text_color=DANGER)

    def _reset(self):
        username = self.user_entry.get().strip()
        otp = self.otp_entry.get().strip()
        new_pass = self.new_pass_entry.get()
        if not username or not otp or len(new_pass) < 6:
            self.lbl_msg.configure(
                text="Fill username, OTP and a new password (min 6 chars).",
                text_color=DANGER)
            return
        self.btn_reset.configure(state="disabled", text="Resetting...")

        def worker():
            ok, msgtext = self.auth.forgot_reset(username, otp, new_pass)
            self.after(0, lambda: self._reset_done(ok, msgtext))

        threading.Thread(target=worker, daemon=True).start()

    def _reset_done(self, ok, msgtext):
        self.btn_reset.configure(state="normal", text="✅ Reset Password")
        if ok:
            messagebox.showinfo(
                "Password Changed",
                "Password changed successfully!\nLogin with the new password.",
                parent=self)
            self.destroy()
        else:
            self.lbl_msg.configure(text=msgtext, text_color=DANGER)


# ============================================================= login window =
class LoginWindow(ctk.CTkToplevel):
    """Blocking login gate shown before the main application starts."""

    def __init__(self, parent, auth, on_success):
        super().__init__(parent)
        self.parent = parent
        self.auth = auth
        self.on_success = on_success
        self._busy = False

        self.title(f"{APP_NAME} — Login")
        self.geometry("460x560")
        self.configure(fg_color=BG_DARK)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._quit_app)

        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 230
        y = (self.winfo_screenheight() // 2) - 280
        self.geometry(f"+{x}+{y}")

        self._build_ui()
        # Try the saved 7-day session first.
        self.after(200, self._try_saved_session)

    def _build_ui(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(expand=True, fill="both", padx=30, pady=20)

        ctk.CTkLabel(frame, text="🦚", font=("Arial", 52)).pack(pady=(10, 0))
        ctk.CTkLabel(frame, text=APP_NAME, font=("Arial Black", 24, "bold"),
                     text_color=HIGHLIGHT).pack(pady=(0, 15))

        self.server_entry = ctk.CTkEntry(frame, height=38,
                                         placeholder_text="Server URL (https://...)")
        self.server_entry.pack(fill="x", pady=5)
        if self.auth.server_url:
            self.server_entry.insert(0, self.auth.server_url)

        self.user_entry = ctk.CTkEntry(frame, height=38,
                                       placeholder_text="Username")
        self.user_entry.pack(fill="x", pady=5)
        self.pass_entry = ctk.CTkEntry(frame, height=38, show="•",
                                       placeholder_text="Password")
        self.pass_entry.pack(fill="x", pady=5)
        self.pass_entry.bind("<Return>", lambda e: self._do_login())

        self.btn_login = ctk.CTkButton(frame, text="🔐 LOGIN", height=44,
                                       font=("Arial", 13, "bold"),
                                       fg_color=SUCCESS, hover_color="#059669",
                                       command=self._do_login)
        self.btn_login.pack(fill="x", pady=(15, 5))

        self.btn_forgot = ctk.CTkButton(frame, text="Forgot Password?",
                                        height=30, font=("Arial", 11),
                                        fg_color="transparent",
                                        hover_color=PANEL_BG,
                                        text_color=ACCENT,
                                        command=self._forgot_password)
        self.btn_forgot.pack(pady=(0, 2))

        self.lbl_msg = ctk.CTkLabel(frame, text="", font=("Arial", 11),
                                    wraplength=380, text_color="gray")
        self.lbl_msg.pack(pady=8)

        self.btn_register = ctk.CTkButton(
            frame, text="📝 New Registration (opens website)",
            height=34, font=("Arial", 11), fg_color="#1E3A5F",
            hover_color="#2563EB", command=self._open_registration)
        self.btn_register.pack(fill="x", pady=(5, 0))
        ctk.CTkLabel(frame,
                     text="Register with your details — confirmation\n"
                          "arrives on WhatsApp (password stays secret).",
                     font=("Arial", 10), text_color="gray").pack(pady=(5, 0))
        ctk.CTkLabel(frame, text=APP_VERSION, font=("Courier", 9),
                     text_color="gray").pack(side="bottom", pady=5)

    def _quit_app(self):
        self.parent.destroy()

    def _set_msg(self, text, color="gray"):
        self.lbl_msg.configure(text=text, text_color=color)

    def _try_saved_session(self):
        if not self.auth.load_saved_session():
            self._set_msg("Please login to continue.", "gray")
            return
        self._set_msg("Verifying saved login...", ACCENT)
        self._busy = True

        def worker():
            status = self.auth.verify()
            self.after(0, lambda: self._saved_session_result(status))

        threading.Thread(target=worker, daemon=True).start()

    def _forgot_password(self):
        server = self.server_entry.get().strip()
        if not server:
            self._set_msg("Enter the Server URL first.", DANGER)
            return
        self.auth.save_client_config(server)
        ForgotPasswordDialog(self, self.auth)

    def _open_registration(self):
        server = self.server_entry.get().strip()
        if not server:
            self._set_msg("Enter the Server URL first.", DANGER)
            return
        self.auth.save_client_config(server)
        webbrowser.open(self.auth.server_url + "/register.php")
        self._set_msg("Registration page opened in your browser.", ACCENT)

    def _saved_session_result(self, status):
        self._busy = False
        if status == "ok":
            self._finish()
        elif status == "offline":
            # Internet is mandatory — without the server nothing opens.
            self._set_msg("⚠ Internet is required. Could not reach the "
                          "server — connect internet and login again.",
                          DANGER)
        else:
            self.auth.clear_session()
            self._set_msg("Session expired — please login again.", WARNING)

    def _do_login(self):
        if self._busy:
            return
        server = self.server_entry.get().strip()
        username = self.user_entry.get().strip()
        password = self.pass_entry.get()
        if not server or not username or not password:
            self._set_msg("Enter server URL, username and password.", DANGER)
            return
        self.auth.save_client_config(server)
        self._busy = True
        self.btn_login.configure(state="disabled", text="Logging in...")
        self._set_msg("Contacting server...", ACCENT)

        def worker():
            ok, message = self.auth.login(username, password)
            self.after(0, lambda: self._login_result(ok, message))

        threading.Thread(target=worker, daemon=True).start()

    def _login_result(self, ok, message):
        self._busy = False
        self.btn_login.configure(state="normal", text="🔐 LOGIN")
        if ok:
            self._finish()
        else:
            self._set_msg(message, DANGER)

    def _finish(self):
        self.destroy()
        self.on_success()


# ================================================================== splash ==
class SplashScreen(ctk.CTkToplevel):
    """Animated splash screen shown while the AI model loads."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("")
        self.geometry("600x400")
        self.configure(fg_color=BG_DARK)
        self.overrideredirect(True)

        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 300
        y = (self.winfo_screenheight() // 2) - 200
        self.geometry(f"+{x}+{y}")

        self._closed = False
        self._min_time_done = False
        self.setup_ui()
        self.animate()

        self.after(3000, self._mark_min_time)
        self.after(300, self._poll_ready)

    def setup_ui(self):
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=20, pady=20)

        self.canvas = tk.Canvas(main_frame, width=400, height=150,
                                bg=BG_DARK, highlightthickness=0)
        self.canvas.pack(pady=10)
        self.canvas.create_text(200, 75, text="🦚", font=("Arial", 60),
                                fill=HIGHLIGHT, anchor="center", tags="logo")

        ctk.CTkLabel(main_frame, text=APP_NAME,
                     font=("Arial Black", 26, "bold"),
                     text_color=HIGHLIGHT).pack(pady=10)

        self.progress = ctk.CTkProgressBar(main_frame, width=400, height=8,
                                           progress_color=ACCENT)
        self.progress.set(0)
        self.progress.pack(pady=15)

        self.lbl_loading = ctk.CTkLabel(main_frame,
                                        text="Initializing Forensic Engine...",
                                        font=("Arial", 11), text_color="gray")
        self.lbl_loading.pack()
        ctk.CTkLabel(main_frame, text=APP_VERSION,
                     font=("Courier", 9), text_color="gray").pack(pady=5)

    def animate(self):
        texts = ["Initializing AI Models...", "Loading Neural Trackers...",
                 "Calibrating Visual Engine...", "Preparing Workspace..."]

        def tick(i=0):
            if self._closed:
                return
            self.progress.set((i % 100) / 100)
            self.lbl_loading.configure(text=texts[(i // 25) % len(texts)])
            self.canvas.delete("logo")
            self.canvas.create_text(200, 75,
                                    text="🦚" if i % 20 < 10 else "⚡",
                                    font=("Arial", 60), fill=HIGHLIGHT,
                                    anchor="center", tags="logo")
            self.after(60, tick, i + 1)

        tick(0)

    def _mark_min_time(self):
        self._min_time_done = True

    def _poll_ready(self):
        if self._min_time_done and self.parent.model_status != "loading":
            self.close_splash()
        else:
            self.after(300, self._poll_ready)

    def close_splash(self):
        if self._closed:
            return
        self._closed = True
        self.destroy()
        self.parent.deiconify()
        self.parent.on_splash_closed()


# ==================================================================== app ===
class KrishnaIntelligence(ctk.CTk):
    # COCO class-id -> display name
    CATEGORIES = {0: "Person", 2: "Car", 3: "Motorcycle", 5: "Bus",
                  7: "Truck", 15: "Cat", 16: "Dog", 19: "Cow"}
    VEHICLES = ("Car", "Motorcycle", "Bus", "Truck")
    ANIMALS = ("Cat", "Dog", "Cow")

    def __init__(self):
        super().__init__()
        self.withdraw()

        self.title(f"🦚 {APP_NAME}")
        self.geometry("1400x800")
        self._maximize_window()
        self.configure(fg_color=BG_DARK)

        # ---------------- engine state ----------------
        self.video_list = []
        self.current_video_idx = 0
        self.base_dir = "Krishna_Forensic_Data"
        self.current_case_dir = ""
        self.current_case_id = ""
        self.is_scanning = False
        self.is_stopped = False
        self.pause_event = threading.Event()      # set = paused
        self.tracked_ids = set()                  # {(video_name, track_id)}
        self.scan_config = {}                     # snapshot of UI settings
        self.display_size = (854, 480)            # updated on window resize

        self.gui_queue = queue.Queue()
        self.gallery_widgets = []
        self.max_gallery_items = 40
        self.evidence_database = []
        self.stats = defaultdict(int)
        self.scan_started_at = None

        # ---------------- AI config ----------------
        self.conf_threshold = 0.35
        self.frame_skip = 5
        self.model = None
        self.model_status = "loading"             # loading | ready | failed
        self.model_error = ""
        self.device = "cpu"

        # ---------------- auth ----------------
        self.auth = AuthClient()

        self.setup_directories()
        self.setup_ui()
        self.process_queue()

        # Login gate first; splash + model load start after login succeeds.
        self.login_window = LoginWindow(self, self.auth, self._on_logged_in)

    # ---------------------------------------------------------- login flow -
    def _on_logged_in(self):
        profile = self.auth.profile or {}
        station = profile.get("police_station", "")
        operator = profile.get("name", profile.get("username", ""))
        designation = profile.get("designation", "")
        valid_until = profile.get("valid_until") or ""
        if station:
            self.station_label.configure(text=f"🏢 {station}")
        if operator:
            who = f"👮 {operator}"
            if designation:
                who += f" ({designation})"
            self.operator_label.configure(text=who)
        if valid_until:
            self.validity_label.configure(
                text=f"⏳ Valid till: {valid_until[:10]}")
        else:
            self.validity_label.configure(text="⏳ Validity: Unlimited")
        log.info("Logged in as %s (%s)", profile.get("username"), station)

        self.splash = SplashScreen(self)
        threading.Thread(target=self._load_model, daemon=True).start()
        # Push any reports that could not be uploaded last time.
        self.after(4000, lambda: self.sync_reports(silent=True))

    def logout(self):
        if self.is_scanning:
            messagebox.showwarning("Busy", "Stop the scan before logging out.")
            return
        if not messagebox.askyesno("Logout", "Logout and close the software?"):
            return
        self.auth.clear_session()
        self.destroy()

    # ------------------------------------------------------------- window --
    def _maximize_window(self):
        try:
            self.state("zoomed")                  # Windows
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)  # some Linux WMs
            except tk.TclError:
                pass

    # -------------------------------------------------------- model loading
    def _load_model(self):
        """Load YOLO in a background thread so the UI never freezes."""
        try:
            import torch
            from ultralytics import YOLO
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            log.info("Loading YOLOv8 model on %s ...", self.device.upper())
            model = YOLO("yolov8s.pt")
            model.to(self.device)
            self.model = model
            self.model_status = "ready"
            log.info("Model ready on %s", self.device.upper())
            self.gui_queue.put(("model_ready", None))
        except Exception as exc:
            self.model_status = "failed"
            self.model_error = str(exc)
            log.error("Model load failed: %s\n%s", exc, traceback.format_exc())
            self.gui_queue.put(("model_failed", str(exc)))

    def _reset_tracker(self):
        """Reset tracker state so IDs from one video never leak into the next."""
        try:
            predictor = getattr(self.model, "predictor", None)
            if predictor is not None and getattr(predictor, "trackers", None):
                for tracker in predictor.trackers:
                    tracker.reset()
        except Exception as exc:
            log.warning("Tracker reset skipped: %s", exc)

    def on_splash_closed(self):
        if self.model_status == "ready":
            self.lbl_status.configure(text="✅ System Ready",
                                      text_color=SUCCESS)
        elif self.model_status == "failed":
            self.lbl_status.configure(text="❌ AI Model Failed", text_color=DANGER)
            messagebox.showerror(
                "AI Model Error",
                "The YOLOv8 model could not be loaded.\n\n"
                f"Reason: {self.model_error}\n\n"
                "First run needs internet access to download 'yolov8s.pt'.\n"
                "Check krishna_intelligence.log for details, then restart.")

    # --------------------------------------------------------------- dirs --
    def setup_directories(self):
        os.makedirs(os.path.join(self.base_dir, "Cases"), exist_ok=True)

    # ----------------------------------------------------------------- UI --
    def setup_ui(self):
        self.grid_columnconfigure(1, weight=5)
        self.grid_columnconfigure(2, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ================= LEFT SIDEBAR (scrollable) =================
        self.sidebar = ctk.CTkScrollableFrame(self, width=320, corner_radius=0,
                                              fg_color=PANEL_BG)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        header = ctk.CTkFrame(self.sidebar, fg_color=HIGHLIGHT, corner_radius=8)
        header.pack(fill="x", pady=(10, 10), padx=10)
        ctk.CTkLabel(header, text="🦚 Krishna", font=("Arial Black", 24),
                     text_color=BG_DARK).pack(pady=(15, 0))
        ctk.CTkLabel(header, text="INTELLIGENCE", font=("Arial Black", 14),
                     text_color=BG_DARK).pack(pady=(0, 15))

        # ---- operator / police-station strip ----
        who = ctk.CTkFrame(self.sidebar, fg_color=BG_DARK, corner_radius=8)
        who.pack(fill="x", padx=10, pady=(0, 10))
        self.station_label = ctk.CTkLabel(who, text="🏢 —",
                                          font=("Arial", 11, "bold"),
                                          text_color=GOLD)
        self.station_label.pack(pady=(8, 0))
        self.operator_label = ctk.CTkLabel(who, text="👮 —",
                                           font=("Arial", 10),
                                           text_color=ACCENT)
        self.operator_label.pack()
        self.validity_label = ctk.CTkLabel(who, text="⏳ —",
                                           font=("Arial", 9),
                                           text_color="gray")
        self.validity_label.pack(pady=(0, 8))

        # ---- batch control ----
        actions = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        actions.pack(pady=5, padx=10, fill="x")
        self.btn_import = ctk.CTkButton(
            actions, text="📂 LOAD BATCH VIDEOS", font=("Arial", 12, "bold"),
            fg_color="#2563EB", hover_color="#1D4ED8", height=45,
            command=self.import_videos)
        self.btn_import.pack(fill="x", pady=5)

        ctrl = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        ctrl.pack(pady=5, padx=10, fill="x")
        self.btn_start = ctk.CTkButton(
            ctrl, text="▶ START", font=("Arial", 12, "bold"),
            fg_color=SUCCESS, hover_color="#059669", height=40,
            command=self.start_analysis)
        self.btn_start.pack(side="left", expand=True, padx=(0, 5), fill="x")
        self.btn_stop = ctk.CTkButton(
            ctrl, text="⏹ ABORT", font=("Arial", 12, "bold"),
            fg_color=DANGER, hover_color="#DC2626", height=40,
            command=self.stop_analysis, state="disabled")
        self.btn_stop.pack(side="right", expand=True, padx=(5, 0), fill="x")

        self.btn_pause = ctk.CTkButton(
            self.sidebar, text="⏸ PAUSE", font=("Arial", 12, "bold"),
            fg_color=WARNING, hover_color="#D97706", height=36,
            command=self.toggle_pause, state="disabled")
        self.btn_pause.pack(pady=5, padx=10, fill="x")

        # ---- case info ----
        case_frame = ctk.CTkFrame(self.sidebar, fg_color=BG_DARK, corner_radius=8)
        case_frame.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(case_frame, text="📋 CASE DETAILS",
                     font=("Arial", 11, "bold"), text_color=ACCENT).pack(pady=(10, 5))
        self.case_entry = ctk.CTkEntry(case_frame,
                                       placeholder_text="FIR / Case ID...",
                                       height=35)
        self.case_entry.pack(padx=10, pady=(5, 10), fill="x")

        # ---- smart filters ----
        filter_frame = ctk.CTkFrame(self.sidebar, fg_color=BG_DARK, corner_radius=8)
        filter_frame.pack(padx=10, pady=5, fill="x")
        ctk.CTkLabel(filter_frame, text="🎯 SMART FILTERS",
                     font=("Arial", 11, "bold"), text_color=ACCENT).pack(pady=(10, 5))
        self.color_filter = ctk.CTkComboBox(
            filter_frame, height=32,
            values=["All Colors", "Red", "Blue", "Green", "White",
                    "Black", "Silver", "Yellow"])
        self.color_filter.pack(padx=10, pady=5, fill="x")
        self.object_filter = ctk.CTkComboBox(
            filter_frame, height=32,
            values=["All Objects", "Person", "Vehicle", "Animal"])
        self.object_filter.pack(padx=10, pady=(5, 10), fill="x")

        # ---- engine settings ----
        settings = ctk.CTkFrame(self.sidebar, fg_color=BG_DARK, corner_radius=8)
        settings.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(settings, text="⚡ ENGINE SETTINGS",
                     font=("Arial", 11, "bold"), text_color=ACCENT).pack(pady=(10, 5))

        self.speed_slider = ctk.CTkSlider(settings, from_=1, to=30,
                                          number_of_steps=29,
                                          command=self.update_speed,
                                          progress_color=ACCENT)
        self.speed_slider.set(self.frame_skip)
        self.speed_slider.pack(padx=15, pady=5, fill="x")
        self.speed_label = ctk.CTkLabel(settings,
                                        text=f"Speed: Every {self.frame_skip} frames",
                                        font=("Courier", 10))
        self.speed_label.pack(pady=(0, 5))

        self.enhance_switch = ctk.CTkSwitch(settings, text="🔬 Image Enhancement",
                                            font=("Arial", 11),
                                            progress_color=HIGHLIGHT)
        self.enhance_switch.pack(pady=5, padx=15, anchor="w")
        self.enhance_switch.select()

        self.night_switch = ctk.CTkSwitch(settings, text="🌙 Night Vision Mode",
                                          font=("Arial", 11),
                                          progress_color=PURPLE)
        self.night_switch.pack(pady=(5, 10), padx=15, anchor="w")

        # Reports always upload to the web panel; this only retries the
        # queue when an earlier upload failed (no internet at that time).
        ctk.CTkButton(self.sidebar, text="☁ SYNC PENDING REPORTS",
                      font=("Arial", 11, "bold"), fg_color=PURPLE,
                      hover_color="#7C3AED", height=40,
                      command=self.sync_reports).pack(pady=5, padx=10, fill="x")
        ctk.CTkButton(self.sidebar, text="📁 OPEN DATABASE",
                      font=("Arial", 11, "bold"), fg_color="#34495E",
                      hover_color=ACCENT, height=40,
                      command=self.open_folder).pack(pady=5, padx=10, fill="x")
        ctk.CTkButton(self.sidebar, text="🚪 LOGOUT",
                      font=("Arial", 11, "bold"), fg_color="#7F1D1D",
                      hover_color=DANGER, height=36,
                      command=self.logout).pack(pady=(5, 15), padx=10, fill="x")

        self.lbl_status = ctk.CTkLabel(self.sidebar, text="Please login...",
                                       font=("Courier", 10), text_color="gray")
        self.lbl_status.pack(side="bottom", pady=10)

        # ================= CENTER: VIDEO DISPLAY =================
        self.center_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.center_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")

        self.video_frame = ctk.CTkFrame(self.center_frame, fg_color="black",
                                        border_width=2, border_color=PANEL_BG,
                                        corner_radius=10)
        self.video_frame.pack(expand=True, fill="both")
        self.video_frame.bind("<Configure>", self._on_video_area_resize)

        self.video_label = ctk.CTkLabel(self.video_frame,
                                        text="[ NO SIGNAL ]\nLoad videos to start",
                                        font=("Courier", 22, "bold"),
                                        text_color="#555555")
        self.video_label.pack(expand=True, fill="both")

        status_bar = ctk.CTkFrame(self.center_frame, fg_color="transparent",
                                  height=30)
        status_bar.pack(fill="x", pady=(10, 0))
        self.batch_label = ctk.CTkLabel(status_bar, text="Queue: 0 Videos",
                                        font=("Arial", 12, "bold"),
                                        text_color=ACCENT)
        self.batch_label.pack(side="left")
        self.lbl_performance = ctk.CTkLabel(status_bar, text="Ready",
                                            font=("Courier", 11),
                                            text_color=GOLD)
        self.lbl_performance.pack(side="right")

        self.progress = ctk.CTkProgressBar(self.center_frame,
                                           progress_color=ACCENT, height=8)
        self.progress.pack(fill="x", pady=(5, 0))
        self.progress.set(0)

        # ================= RIGHT: EVIDENCE PANEL =================
        self.evidence_panel = ctk.CTkFrame(self, fg_color=PANEL_BG,
                                           corner_radius=10)
        self.evidence_panel.grid(row=0, column=2, padx=15, pady=15, sticky="nsew")

        stats_frame = ctk.CTkFrame(self.evidence_panel, fg_color=BG_DARK,
                                   corner_radius=8)
        stats_frame.pack(fill="x", padx=10, pady=10)
        self.hw_label = ctk.CTkLabel(stats_frame, text="HARDWARE: DETECTING...",
                                     font=("Courier", 11, "bold"),
                                     text_color=WARNING)
        self.hw_label.pack(pady=(10, 5))

        stat_grid = ctk.CTkFrame(stats_frame, fg_color="transparent")
        stat_grid.pack(pady=5)
        self.person_count = ctk.CTkLabel(stat_grid, text="👤 P: 0",
                                         font=("Arial", 15, "bold"))
        self.person_count.grid(row=0, column=0, padx=15, pady=3)
        self.vehicle_count = ctk.CTkLabel(stat_grid, text="🚗 V: 0",
                                          font=("Arial", 15, "bold"))
        self.vehicle_count.grid(row=0, column=1, padx=15, pady=3)
        self.evidence_count = ctk.CTkLabel(stats_frame,
                                           text="📸 Total Evidence: 0",
                                           font=("Arial", 13, "bold"),
                                           text_color=GOLD)
        self.evidence_count.pack(pady=(5, 10))

        ctk.CTkLabel(self.evidence_panel, text="🔍 LIVE EVIDENCE GALLERY",
                     font=("Arial", 12, "bold"),
                     text_color=HIGHLIGHT).pack(pady=(5, 0))
        self.gallery = ctk.CTkScrollableFrame(self.evidence_panel,
                                              fg_color="transparent")
        self.gallery.pack(expand=True, fill="both", padx=5, pady=5)

        ctk.CTkLabel(self.evidence_panel, text="📅 TIMELINE LOG",
                     font=("Arial", 11, "bold"), text_color=ACCENT
                     ).pack(anchor="w", padx=10, pady=(5, 0))
        self.timeline_text = ctk.CTkTextbox(self.evidence_panel, height=100,
                                            fg_color=BG_DARK,
                                            font=("Courier", 10))
        self.timeline_text.pack(fill="x", padx=10, pady=(0, 10))

    # -------------------------------------------------------- UI callbacks -
    def _on_video_area_resize(self, event):
        if event.width > 100 and event.height > 100:
            self.display_size = (event.width - 20, event.height - 20)

    def update_speed(self, val):
        self.frame_skip = max(1, int(val))
        self.speed_label.configure(text=f"Speed: Every {self.frame_skip} frames")

    def import_videos(self):
        files = filedialog.askopenfilenames(
            title="Select Videos",
            filetypes=[("Video Files", "*.mp4 *.avi *.mkv *.mov *.wmv *.dav *.h264")])
        if files:
            self.video_list = list(files)
            self.batch_label.configure(text=f"Queue: {len(files)} Videos Loaded")
            self.video_label.configure(
                text=f"✅ {len(files)} FILES LOADED\nReady for Analysis",
                text_color=SUCCESS)
            self.lbl_status.configure(text="Ready to Scan", text_color=SUCCESS)

    def toggle_pause(self):
        if not self.is_scanning:
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.btn_pause.configure(text="⏸ PAUSE")
            self.lbl_status.configure(text="Scanning...", text_color=ACCENT)
        else:
            self.pause_event.set()
            self.btn_pause.configure(text="▶ RESUME")
            self.lbl_status.configure(text="⏸ Paused", text_color=WARNING)

    # ------------------------------------------------------- scan control --
    def start_analysis(self):
        if self.model_status == "loading":
            messagebox.showinfo("Please Wait", "AI model is still loading...")
            return
        if self.model_status == "failed" or self.model is None:
            messagebox.showerror(
                "AI Model Error",
                "The AI model is not loaded, analysis cannot start.\n"
                f"Reason: {self.model_error}\n"
                "First run needs internet to download 'yolov8s.pt'.")
            return
        if not self.video_list:
            messagebox.showwarning("Warning", "Please load videos first!")
            return
        if self.is_scanning:
            return

        case_id = self.case_entry.get().strip() or \
            f"CASE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        case_id = "".join(c if c.isalnum() or c in "-_ " else "_" for c in case_id)
        self.current_case_id = case_id
        self.current_case_dir = os.path.join(self.base_dir, "Cases", case_id)
        os.makedirs(self.current_case_dir, exist_ok=True)

        # Snapshot every UI setting ONCE on the main thread — the worker
        # thread must never touch tkinter widgets directly.
        self.scan_config = {
            "object_filter": self.object_filter.get(),
            "color_filter": self.color_filter.get(),
            "night_mode": bool(self.night_switch.get()),
            "enhance": bool(self.enhance_switch.get()),
            "conf": self.conf_threshold,
        }

        self.is_scanning = True
        self.is_stopped = False
        self.pause_event.clear()
        self.current_video_idx = 0
        self.tracked_ids.clear()
        self.stats.clear()
        self.evidence_database.clear()
        self.scan_started_at = datetime.now()
        self.timeline_text.delete("1.0", tk.END)
        self.clear_gallery()

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_pause.configure(state="normal", text="⏸ PAUSE")
        self.btn_import.configure(state="disabled")
        self.lbl_status.configure(text="Scanning...", text_color=ACCENT)
        log.info("Scan started | case=%s videos=%d config=%s",
                 case_id, len(self.video_list), self.scan_config)

        self.process_next_video()

    def stop_analysis(self):
        self.is_stopped = True
        self.pause_event.clear()
        self.lbl_status.configure(text="Aborting...", text_color=WARNING)

    def process_next_video(self):
        if self.current_video_idx < len(self.video_list) and not self.is_stopped:
            video_path = self.video_list[self.current_video_idx]
            video_name = os.path.basename(video_path)
            self.batch_label.configure(
                text=f"🔍 Scanning {self.current_video_idx + 1}/"
                     f"{len(self.video_list)}: {video_name[:25]}...")
            threading.Thread(target=self.core_engine,
                             args=(video_path, dict(self.scan_config)),
                             daemon=True).start()
        else:
            self.finish_analysis()

    # ---------------------------------------------------------- core engine
    def core_engine(self, video_path, config):
        """Analyse one video in a background thread.

        Communicates with the UI exclusively through self.gui_queue;
        always signals 'video_done' so the batch can never get stuck.
        """
        try:
            self._run_video(video_path, config)
        except Exception as exc:
            log.error("Engine error on %s: %s\n%s",
                      video_path, exc, traceback.format_exc())
            self.gui_queue.put(
                ("video_error",
                 f"⚠ {os.path.basename(video_path)}: {exc}\n"))
        finally:
            self.gui_queue.put(("video_done", None))

    def _run_video(self, video_path, config):
        vid_name = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(self.current_case_dir, vid_name)
        os.makedirs(output_dir, exist_ok=True)

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.gui_queue.put(
                ("video_error",
                 f"⚠ Could not open video: {os.path.basename(video_path)}\n"))
            return

        # Fresh tracker per video so IDs never carry over between files.
        self._reset_tracker()

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0 or fps != fps:  # 0 / NaN safety
            fps = 30.0
        frame_idx = 0
        start_time = time.time()

        try:
            while not self.is_stopped:
                while self.pause_event.is_set() and not self.is_stopped:
                    time.sleep(0.1)

                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % self.frame_skip == 0:
                    self._process_frame(frame, frame_idx, fps, vid_name,
                                        output_dir, config)

                    elapsed = time.time() - start_time
                    speed = frame_idx / elapsed if elapsed > 0 else 0.0
                    self.gui_queue.put(("progress",
                                        frame_idx / total_frames
                                        if total_frames > 0 else 0))
                    self.gui_queue.put(("performance",
                                        f"⚡ Speed: {speed:.1f} FPS"))
                frame_idx += 1
        finally:
            cap.release()

    def _process_frame(self, frame, frame_idx, fps, vid_name, output_dir, config):
        results = self.model.track(frame, conf=config["conf"],
                                   persist=True, verbose=False)
        result = results[0]
        annotated = result.plot()

        if result.boxes.id is not None:
            ids = result.boxes.id.int().cpu().tolist()
            clss = result.boxes.cls.int().cpu().tolist()
            boxes = result.boxes.xyxy.cpu().numpy()
            for box, tid, cls in zip(boxes, ids, clss):
                self._capture_evidence(frame, box, tid, cls, frame_idx, fps,
                                       vid_name, output_dir, config)

        # Live preview, letter-boxed to the current display area size.
        disp_w, disp_h = self.display_size
        h, w = annotated.shape[:2]
        scale = min(disp_w / w, disp_h / h)
        new_size = (max(2, int(w * scale)), max(2, int(h * scale)))
        rgb = cv2.cvtColor(cv2.resize(annotated, new_size), cv2.COLOR_BGR2RGB)
        self.gui_queue.put(("frame", Image.fromarray(rgb), new_size))

    def _capture_evidence(self, frame, box, tid, cls, frame_idx, fps,
                          vid_name, output_dir, config):
        if cls not in self.CATEGORIES:
            return
        key = (vid_name, tid)
        if key in self.tracked_ids:
            return
        cat_name = self.CATEGORIES[cls]

        # Object filter
        target_obj = config["object_filter"]
        if target_obj != "All Objects":
            if target_obj == "Person" and cat_name != "Person":
                return
            if target_obj == "Vehicle" and cat_name not in self.VEHICLES:
                return
            if target_obj == "Animal" and cat_name not in self.ANIMALS:
                return

        fh, fw = frame.shape[:2]
        x1, y1, x2, y2 = map(int, box[:4])
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(fw, x2), min(fh, y2)
        if x2 <= x1 or y2 <= y1:
            return
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return

        color = self.detect_color(crop)

        # Color filter — object stays un-marked so later frames get a
        # fresh chance if the first crop's color was ambiguous.
        target_color = config["color_filter"]
        if target_color != "All Colors" and color != target_color:
            return

        self.tracked_ids.add(key)

        if config["night_mode"]:
            crop = self.enhance_night(crop)
        elif config["enhance"]:
            crop = self.enhance_basic(crop)

        seconds = int(frame_idx / fps)
        timestamp_str = f"{seconds // 60:02d}m_{seconds % 60:02d}s"
        filename = f"ID_{tid}_{color}_{cat_name}_{timestamp_str}_f{frame_idx}.jpg"
        filepath = os.path.join(output_dir, filename)
        cv2.imwrite(filepath, crop)

        if cat_name == "Person":
            self.stats["persons"] += 1
        elif cat_name in self.VEHICLES:
            self.stats["vehicles"] += 1

        self.evidence_database.append({
            "filename": filename, "type": cat_name, "track_id": tid,
            "color": color, "timestamp": timestamp_str, "video": vid_name,
            "filepath": os.path.abspath(filepath),
        })

        self.gui_queue.put(("timeline",
                            f"[{vid_name} {timestamp_str}] {cat_name} "
                            f"(ID:{tid}) | Color: {color}\n"))
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        self.gui_queue.put(("evidence", Image.fromarray(crop_rgb), cat_name,
                            color, timestamp_str, tid, filepath))
        self.gui_queue.put(("stats_update", None))

    # ------------------------------------------------------- image helpers -
    def detect_color(self, crop):
        """Dominant-color estimate from the center region of the crop."""
        try:
            h, w = crop.shape[:2]
            region = crop[h // 5: h - h // 5, w // 5: w - w // 5]
            if region.size == 0:
                region = crop
            hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
            colors = {
                "Red": [([0, 100, 100], [10, 255, 255]),
                        ([160, 100, 100], [180, 255, 255])],
                "Blue": [([90, 50, 50], [130, 255, 255])],
                "Green": [([35, 50, 50], [85, 255, 255])],
                "Yellow": [([15, 100, 100], [35, 255, 255])],
                "White": [([0, 0, 200], [180, 30, 255])],
                "Black": [([0, 0, 0], [180, 255, 50])],
                "Silver": [([0, 0, 50], [180, 40, 200])],
            }
            best, max_pct = "Unknown", 0.0
            total = hsv.shape[0] * hsv.shape[1]
            for name, ranges in colors.items():
                mask = np.zeros(hsv.shape[:2], dtype="uint8")
                for lo, hi in ranges:
                    mask = cv2.bitwise_or(
                        mask, cv2.inRange(hsv, np.array(lo), np.array(hi)))
                pct = cv2.countNonZero(mask) / total * 100
                if pct > max_pct and pct > 10:
                    max_pct, best = pct, name
            return best
        except Exception as exc:
            log.warning("Color detection failed: %s", exc)
            return "Unknown"

    def enhance_basic(self, image):
        """Fast enhancement: CLAHE contrast + unsharp mask + 2x upscale."""
        try:
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            lab = cv2.merge((clahe.apply(l), a, b))
            img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
            blur = cv2.GaussianBlur(img, (0, 0), 3)
            img = cv2.addWeighted(img, 1.5, blur, -0.5, 0)
            h, w = img.shape[:2]
            return cv2.resize(img, (w * 2, h * 2),
                              interpolation=cv2.INTER_CUBIC)
        except Exception as exc:
            log.warning("Enhancement failed: %s", exc)
            return image

    def enhance_night(self, image):
        """Night vision: brightness boost + CLAHE + fast denoise."""
        try:
            img = cv2.convertScaleAbs(image, alpha=1.5, beta=40)
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            lab = cv2.merge((clahe.apply(l), a, b))
            img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
            return cv2.bilateralFilter(img, 7, 60, 60)
        except Exception as exc:
            log.warning("Night enhancement failed: %s", exc)
            return image

    # ------------------------------------------------------------- finish --
    def finish_analysis(self):
        aborted = self.is_stopped
        self.is_scanning = False
        self.pause_event.clear()
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_pause.configure(state="disabled", text="⏸ PAUSE")
        self.btn_import.configure(state="normal")
        self.progress.set(1.0)

        if not self.current_case_dir:
            return

        # Reports are NEVER kept as local files — the report (PDF + JSON)
        # is built into the hidden upload queue and pushed to the web
        # panel. Without internet the operator gets no report; it stays
        # queued and uploads automatically when internet returns.
        queued = False
        if self.evidence_database:
            queued = self._queue_report(aborted) is not None

        if aborted:
            self.lbl_status.configure(text="⏹ Analysis Aborted",
                                      text_color=WARNING)
            self.batch_label.configure(text="⏹ Scan Aborted")
            messagebox.showwarning(
                "Aborted",
                f"Analysis was aborted.\n"
                f"📸 Evidence captured so far: {len(self.evidence_database)}\n"
                "☁ The report of captured evidence is being uploaded "
                "to the web panel.")
        else:
            self.lbl_status.configure(text="Analysis Complete",
                                      text_color=SUCCESS)
            self.batch_label.configure(text="✅ All Batches Compiled!")
            messagebox.showinfo(
                "Compiled",
                f"Case Analysis Successful!\n"
                f"📸 Evidence images: {len(self.evidence_database)}\n"
                "☁ The report is being uploaded to the web panel — the "
                "view link arrives on WhatsApp.")
        log.info("Scan finished | aborted=%s evidence=%d",
                 aborted, len(self.evidence_database))

        if queued:
            self.sync_reports(silent=True)

    # ------------------------------------------------------------- upload --
    def _queue_report(self, aborted):
        """Build the report (PDF + JSON + meta) into the hidden upload
        queue. Returns the queue folder, or None on failure."""
        profile = self.auth.profile or {}
        qdir = os.path.join(
            self.base_dir, ".upload_queue",
            f"{self.current_case_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}")
        try:
            os.makedirs(qdir, exist_ok=True)
            report = {
                "app": f"{APP_NAME} {APP_VERSION}",
                "case_id": self.current_case_id,
                "police_station": profile.get("police_station", ""),
                "operator": profile.get("name", profile.get("username", "")),
                "generated": datetime.now().isoformat(timespec="seconds"),
                "started": self.scan_started_at.isoformat(timespec="seconds")
                if self.scan_started_at else None,
                "status": "ABORTED" if aborted else "COMPLETED",
                "videos": [os.path.basename(v) for v in self.video_list],
                "stats": {"persons": self.stats.get("persons", 0),
                          "vehicles": self.stats.get("vehicles", 0),
                          "total_evidence": len(self.evidence_database)},
                "evidence": self.evidence_database,
            }
            with open(os.path.join(qdir, "report.json"), "w",
                      encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            pdf_ok, pdf_err = self._build_pdf(os.path.join(qdir, "report.pdf"))
            if not pdf_ok:
                log.warning("PDF build failed: %s", pdf_err)

            meta = {"case_id": self.current_case_id,
                    "persons": self.stats.get("persons", 0),
                    "vehicles": self.stats.get("vehicles", 0),
                    "total": len(self.evidence_database)}
            with open(os.path.join(qdir, "meta.json"), "w",
                      encoding="utf-8") as f:
                json.dump(meta, f)
            return qdir
        except OSError as exc:
            log.error("Could not queue report: %s", exc)
            return None

    def sync_reports(self, silent=False):
        """Upload every queued report in a background thread."""
        qroot = os.path.join(self.base_dir, ".upload_queue")
        dirs = []
        if os.path.isdir(qroot):
            dirs = sorted(os.path.join(qroot, d) for d in os.listdir(qroot)
                          if os.path.isdir(os.path.join(qroot, d)))
        if not dirs:
            if not silent:
                self.gui_queue.put(("timeline",
                                    "☁ No pending reports — all synced.\n"))
            return
        if not self.auth.token:
            self.gui_queue.put(("timeline", "☁ Not logged in — cannot sync.\n"))
            return
        self.lbl_status.configure(text="☁ Uploading report(s)...",
                                  text_color=ACCENT)

        def worker():
            for qdir in dirs:
                try:
                    with open(os.path.join(qdir, "meta.json"),
                              encoding="utf-8") as f:
                        meta = json.load(f)
                except (OSError, ValueError):
                    shutil.rmtree(qdir, ignore_errors=True)
                    continue
                ok, result = self.auth.upload_report(
                    meta.get("case_id", "CASE"),
                    os.path.join(qdir, "report.pdf"),
                    os.path.join(qdir, "report.json"), meta)
                if ok:
                    shutil.rmtree(qdir, ignore_errors=True)
                self.gui_queue.put(("upload_result", ok, result,
                                    meta.get("case_id", "")))
                if not ok:
                    break  # server unreachable — keep the rest queued

        threading.Thread(target=worker, daemon=True).start()

    # ---------------------------------------------------------- PDF build --
    def _build_pdf(self, path):
        """Write the case PDF report to `path`. Returns (ok, error)."""
        if not self.evidence_database:
            return False, "No evidence."
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm
            from reportlab.lib import colors as rl_colors
            from reportlab.lib.enums import TA_CENTER
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                            Spacer, Table, TableStyle,
                                            Image as RLImage)
        except ImportError:
            return False, "reportlab is not installed (pip install reportlab)."

        try:
            profile = self.auth.profile or {}
            station = profile.get("police_station", "")
            operator = profile.get("name", profile.get("username", ""))
            if profile.get("designation"):
                operator = f"{operator} ({profile['designation']})"

            styles = getSampleStyleSheet()
            station_style = ParagraphStyle(
                "Station", parent=styles["Title"], fontSize=16,
                alignment=TA_CENTER,
                textColor=rl_colors.HexColor("#7F1D1D"))
            title_style = ParagraphStyle(
                "TitleX", parent=styles["Title"], fontSize=14,
                alignment=TA_CENTER,
                textColor=rl_colors.HexColor("#111827"))
            small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=9)

            doc = SimpleDocTemplate(path, pagesize=A4,
                                    topMargin=1.5 * cm, bottomMargin=1.5 * cm)
            story = []
            # Police-station name always on top of the PDF.
            if station:
                story.append(Paragraph(station.upper(), station_style))
                story.append(Spacer(1, 4))
            story += [
                Paragraph(f"{APP_NAME} — Forensic Evidence Report", title_style),
                Spacer(1, 8),
                Paragraph(f"<b>Case ID:</b> {self.current_case_id or '-'}", small),
                Paragraph(f"<b>Operator:</b> {operator or '-'}", small),
                Paragraph(f"<b>Generated:</b> "
                          f"{datetime.now().strftime('%d-%m-%Y %H:%M:%S')}", small),
                Paragraph(f"<b>Videos analysed:</b> {len(self.video_list)}", small),
                Paragraph(f"<b>Persons:</b> {self.stats.get('persons', 0)} &nbsp;&nbsp;"
                          f"<b>Vehicles:</b> {self.stats.get('vehicles', 0)} &nbsp;&nbsp;"
                          f"<b>Total evidence:</b> {len(self.evidence_database)}",
                          small),
                Spacer(1, 14),
            ]

            rows = [["Photo", "Details"]]
            for item in self.evidence_database:
                details = Paragraph(
                    f"<b>{item['type']}</b> (Track ID {item['track_id']})<br/>"
                    f"Color: {item['color']}<br/>"
                    f"Time: {item['timestamp'].replace('_', ' ')}<br/>"
                    f"Video: {item['video']}<br/>"
                    f"File: {item['filename']}", small)
                img_path = item.get("filepath", "")
                if img_path and os.path.exists(img_path):
                    try:
                        img = RLImage(img_path)
                        ratio = img.imageHeight / float(img.imageWidth)
                        img.drawWidth = 4.5 * cm
                        img.drawHeight = min(4.5 * cm * ratio, 6 * cm)
                        rows.append([img, details])
                        continue
                    except Exception:
                        pass
                rows.append([Paragraph("(image missing)", small), details])

            table = Table(rows, colWidths=[5.5 * cm, 11 * cm], repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#111827")),
                ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(table)
            doc.build(story)
            return True, ""
        except Exception as exc:
            log.error("PDF build failed: %s\n%s", exc, traceback.format_exc())
            return False, str(exc)

    # --------------------------------------------------------------- misc --
    def open_folder(self):
        if os.path.exists(self.base_dir):
            open_path(os.path.abspath(self.base_dir))

    def clear_gallery(self):
        for w in self.gallery.winfo_children():
            w.destroy()
        self.gallery_widgets.clear()

    # ---------------------------------------------------------- GUI queue --
    def process_queue(self):
        try:
            while True:
                msg = self.gui_queue.get_nowait()
                kind = msg[0]

                if kind == "frame":
                    pil_img, size = msg[1], msg[2]
                    img_ctk = ctk.CTkImage(light_image=pil_img,
                                           dark_image=pil_img, size=size)
                    self.video_label.configure(image=img_ctk, text="")

                elif kind == "evidence":
                    pil_img, cat, color, ts, tid, path = msg[1:7]
                    thumb = pil_img.copy()
                    thumb.thumbnail((220, 130))
                    img_ctk = ctk.CTkImage(thumb, size=thumb.size)

                    card = ctk.CTkFrame(self.gallery, fg_color=BG_DARK,
                                        corner_radius=8)
                    card.pack(pady=5, padx=5, fill="x")
                    ctk.CTkButton(card, image=img_ctk, text="",
                                  fg_color="transparent",
                                  command=lambda p=path: open_path(p)
                                  ).pack(pady=5)
                    ctk.CTkLabel(card,
                                 text=f"ID:{tid} | {cat} | {color}\n{ts}",
                                 font=("Courier", 10, "bold"),
                                 text_color=HIGHLIGHT).pack(pady=(0, 5))
                    self.gallery_widgets.append(card)
                    if len(self.gallery_widgets) > self.max_gallery_items:
                        self.gallery_widgets.pop(0).destroy()

                elif kind == "stats_update":
                    self.person_count.configure(
                        text=f"👤 P: {self.stats.get('persons', 0)}")
                    self.vehicle_count.configure(
                        text=f"🚗 V: {self.stats.get('vehicles', 0)}")
                    self.evidence_count.configure(
                        text=f"📸 Total Evidence: {len(self.evidence_database)}")

                elif kind == "progress":
                    self.progress.set(msg[1])

                elif kind == "performance":
                    self.lbl_performance.configure(text=msg[1])

                elif kind == "timeline":
                    self.timeline_text.insert(tk.END, msg[1])
                    self.timeline_text.see(tk.END)

                elif kind == "video_error":
                    self.timeline_text.insert(tk.END, msg[1])
                    self.timeline_text.see(tk.END)

                elif kind == "video_done":
                    if self.is_scanning:
                        self.current_video_idx += 1
                        self.process_next_video()

                elif kind == "upload_result":
                    ok, result, case_id = msg[1], msg[2], msg[3]
                    if ok:
                        self.lbl_status.configure(text="☁ Report Uploaded ✅",
                                                  text_color=SUCCESS)
                        self.timeline_text.insert(
                            tk.END, f"☁ Report uploaded ({case_id}): "
                                    f"{result}\n📲 WhatsApp message sent.\n")
                        self.timeline_text.see(tk.END)
                        messagebox.showinfo(
                            "Uploaded",
                            f"Report uploaded to the web panel!\n"
                            f"📋 Case: {case_id}\n"
                            "📲 A WhatsApp message with the report link "
                            "was sent to your registered number.")
                    else:
                        self.lbl_status.configure(
                            text="☁ Upload Pending (no internet)",
                            text_color=WARNING)
                        self.timeline_text.insert(
                            tk.END,
                            f"☁ Upload pending ({case_id}): {result}\n"
                            "It will upload when internet returns — or "
                            "press SYNC PENDING REPORTS.\n")
                        self.timeline_text.see(tk.END)

                elif kind == "model_ready":
                    self.hw_label.configure(
                        text=f"HARDWARE: {self.device.upper()}",
                        text_color=ACCENT if self.device == "cuda" else WARNING)
                    if not self.is_scanning:
                        self.lbl_status.configure(text="✅ System Ready",
                                                  text_color=SUCCESS)

                elif kind == "model_failed":
                    self.hw_label.configure(text="HARDWARE: MODEL FAILED",
                                            text_color=DANGER)

        except queue.Empty:
            pass
        finally:
            self.after(50, self.process_queue)


if __name__ == "__main__":
    app = KrishnaIntelligence()
    app.mainloop()
