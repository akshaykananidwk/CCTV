"""
Krishna Intelligence — Forensic CCTV Video Analysis Suite
Version 16.0 Pro Enterprise

Core:
  - Secure login (7-day sessions, internet mandatory, Forgot Password via
    WhatsApp OTP, device/PC audit trail on the server)
  - Batch CCTV video analysis with YOLOv8 detection + tracking (GPU/CPU auto,
    selectable model size, multi-GPU aware, auto hardware benchmark)
  - Smart filters (object type / color), unique-ID evidence capture,
    enhancement + Night Vision, pause/resume/abort, resume an interrupted
    scan after a crash or power cut
  - Reports live ONLY on the web panel (PDF + JSON, never videos); queued
    locally and retried automatically when internet is unavailable

Investigation aids (v16):
  - Clothing color split (upper/lower), movement direction + approximate
    relative speed, loitering and crowd alerts, cross-video "possible same
    suspect" heuristic matches
  - Optional: face recognition against a local Known_Suspects folder, face
    blurring, number-plate OCR, CCTV overlay-timestamp OCR (each needs an
    extra package — the app tells you which, and disables the switch if
    missing rather than failing)
  - Evidence tools: manual evidence add, star/note/delete, in-app zoom
    viewer, search, ZIP export, ±5s clip export from the source video
  - Case tools: status/notes, templates, recent-cases review, two-case
    heuristic comparison
  - Security: optional at-rest encryption of saved evidence images, PDF
    verification code + operator/designation stamp, evidence photo
    watermark, auto-lock on inactivity, SHA-256 hash of every source video
  - Analytics dashboard, printer output (temp file only, never persisted)

See README.md for exactly which of these need an extra `pip install` or a
one-time setup step, and which advanced items are intentionally deferred.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
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
import hashlib
import io
import math
import re
import secrets
import zipfile
import tempfile
from datetime import datetime, timedelta
from collections import defaultdict
import warnings

warnings.filterwarnings('ignore')

try:
    import pytesseract
    HAS_TESSERACT = True
except BaseException:  # noqa: broad on purpose — a broken/mismatched
    # optional install (including native-extension panics that are not
    # plain ImportError/Exception, e.g. pyo3_runtime.PanicException) must
    # never stop the whole app from starting.
    HAS_TESSERACT = False

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except BaseException:  # noqa: broad — see reasoning above
    HAS_CRYPTO = False

try:
    import qrcode
    HAS_QRCODE = True
except BaseException:  # noqa: broad — see reasoning above
    HAS_QRCODE = False

APP_NAME = "Krishna Intelligence"
APP_VERSION = "v17.0 Pro Enterprise"

CLIENT_CONFIG_FILE = "client_config.json"
SETTINGS_FILE = "app_settings.json"
RESUME_FILE = "resume_state.json"
RECENT_CASES_FILE = "recent_cases.json"
GUJARATI_FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fonts",
    "NotoSansGujarati-Regular.ttf")
SESSION_DIR = os.path.join(os.path.expanduser("~"), ".krishna_intelligence")
SESSION_FILE = os.path.join(SESSION_DIR, "session.json")

DEFAULT_SETTINGS = {
    "theme": "dark",
    "model_size": "yolov8s.pt",
    "gpu_index": 0,
    "autolock_minutes": 0,
    "loiter_seconds": 30,
    "crowd_alert": 8,
}


def load_settings():
    """Local (per-PC) app preferences — separate from the server profile."""
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_SETTINGS)
        merged.update(data)
        return merged
    except (OSError, ValueError):
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError as exc:
        log.warning("Could not save settings: %s", exc)


# ---------------------------------------------------------------- appearance
# Full dark/light palette. Picked once at startup from the saved setting —
# toggling the theme takes effect after a restart (rebuilding ~150 already-
# created widgets live is not worth the risk of a half-migrated UI).
_PALETTES = {
    "dark": dict(BG_DARK="#0A0E1A", PANEL_BG="#111827", CARD_BG="#0A0E1A",
                TEXT_MAIN="#E5E7EB", TEXT_MUTED="gray"),
    "light": dict(BG_DARK="#F1F5F9", PANEL_BG="#FFFFFF", CARD_BG="#E2E8F0",
                 TEXT_MAIN="#0F172A", TEXT_MUTED="#475569"),
}
_initial_settings = load_settings()
_theme_name = _initial_settings.get("theme", "dark")
if _theme_name not in _PALETTES:
    _theme_name = "dark"
ctk.set_appearance_mode(_theme_name)
ctk.set_default_color_theme("blue")

_palette = _PALETTES[_theme_name]
BG_DARK = _palette["BG_DARK"]
PANEL_BG = _palette["PANEL_BG"]
CARD_BG = _palette["CARD_BG"]
TEXT_MAIN = _palette["TEXT_MAIN"]
TEXT_MUTED = _palette["TEXT_MUTED"]
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


def sha256_file(path, chunk_size=1024 * 1024):
    """SHA-256 of a file, for evidentiary integrity of source videos."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def get_or_create_encryption_key():
    """Local Fernet key used only to protect evidence files at rest on
    this PC. Not synced anywhere — losing it makes old encrypted evidence
    unreadable, so it lives next to the session data."""
    os.makedirs(SESSION_DIR, exist_ok=True)
    key_path = os.path.join(SESSION_DIR, "evidence.key")
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(key_path, "wb") as f:
        f.write(key)
    return key


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
        if resp.status_code >= 400:
            # Log the real body (often a PHP error page on bad hosting
            # config) so it ends up in krishna_intelligence.log instead of
            # a generic "server not reachable" that hides the real cause.
            log.error("%s -> HTTP %d: %s", action, resp.status_code,
                     resp.text[:500])
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            log.error("%s -> non-JSON response (HTTP %d): %s", action,
                     resp.status_code, resp.text[:500])
            raise

    def ping(self):
        """No-auth reachability + configuration check. Returns a dict:
        {'ok': bool, 'error': str, ...diagnostic fields from the server}."""
        if not self.server_url:
            return {"ok": False, "error": "Server URL is not set."}
        try:
            return self._post("ping", timeout=10)
        except requests.RequestException as exc:
            return {"ok": False, "error": f"Cannot reach the server: {exc}"}
        except ValueError:
            return {"ok": False,
                    "error": "Server responded but not with valid JSON "
                             "(check the Server URL is correct, and that "
                             "server/ was uploaded to that exact path)."}

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

    def upload_report(self, case_id, pdf_path, json_path, stats, client_token=""):
        """Upload the case report (PDF + JSON only).
        Returns (ok, link_or_error, whatsapp_sent).

        `client_token`, if given, becomes the report's view token on the
        server — this lets the PDF's own QR code (built before upload)
        point at the exact URL the report ends up living at."""
        if not self.token:
            return False, "Not logged in.", False
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
                return False, "No report files to upload.", False
            try:
                payload = {
                    "token": self.token,
                    "case_id": case_id,
                    "persons": stats.get("persons", 0),
                    "vehicles": stats.get("vehicles", 0),
                    "total": stats.get("total", 0),
                }
                if client_token:
                    payload["client_token"] = client_token
                out = self._post("upload_report", payload,
                                 files=files, timeout=120)
            finally:
                for fh in handles:
                    fh.close()
        except requests.RequestException as exc:
            log.error("Report upload failed: %s", exc)
            return False, f"Upload failed — server not reachable: {exc}", False
        except ValueError:
            return False, "Invalid response from server.", False
        if out.get("ok"):
            return True, out.get("view_url", ""), bool(out.get("whatsapp_sent", True))
        return False, out.get("error", "Upload rejected by server."), False

    def diagnose(self):
        """Step-by-step self-test used by the 'Test Server & Upload' button
        so the operator can see EXACTLY where the report pipeline breaks,
        instead of a single generic 'upload failed'. Returns a list of
        (label, ok, detail) tuples."""
        steps = []

        if not self.server_url:
            steps.append(("Server URL", False, "Not set."))
            return steps
        steps.append(("Server URL", True, self.server_url))

        info = self.ping()
        if not info.get("ok"):
            steps.append(("Reach server (ping)", False,
                         info.get("error", "Unknown error.")))
            return steps
        steps.append(("Reach server (ping)", True, "Server responded."))
        steps.append(("Server database", bool(info.get("db_ok")),
                     "OK" if info.get("db_ok") else
                     "Database error on server — check server/data/ "
                     "permissions and krishna.db."))
        steps.append(("PHP curl extension (needed for WhatsApp)",
                     bool(info.get("curl_available")),
                     "OK" if info.get("curl_available") else
                     "Missing — ask your host to enable ext-curl."))
        steps.append(("WhatsApp API configured", bool(info.get("whatsapp_configured")),
                     "OK" if info.get("whatsapp_configured") else
                     "server/config.php still has placeholder "
                     "wa_session_id / wa_api_key."))
        steps.append(("base_url configured", bool(info.get("base_url_set")),
                     "OK" if info.get("base_url_set") else
                     "server/config.php base_url is still the example "
                     "placeholder — report links will be broken."))

        if not self.token:
            steps.append(("Login session", False,
                         "Not logged in in this session."))
            return steps
        status = self.verify()
        steps.append(("Login session valid", status == "ok",
                     {"ok": "Valid.", "offline": "Server unreachable.",
                      "invalid": "Expired or account disabled — login "
                                "again."}.get(status, status)))
        return steps


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


# ======================================================= case compare UI ===
class CaseCompareDialog(ctk.CTkToplevel):
    """Pick two saved cases to run a heuristic cross-case comparison."""

    def __init__(self, parent, cases, on_compare):
        super().__init__(parent)
        self.on_compare = on_compare
        self.title("Compare Cases")
        self.configure(fg_color=BG_DARK)
        self.geometry("360x240")
        self.resizable(False, False)
        self.grab_set()

        ctk.CTkLabel(self, text="🆚 Compare Two Cases",
                     font=("Arial Black", 15),
                     text_color=HIGHLIGHT).pack(pady=(18, 10))
        ctk.CTkLabel(self, text="Case A", font=("Arial", 10),
                     text_color="gray").pack()
        self.combo_a = ctk.CTkComboBox(self, values=cases, width=280)
        self.combo_a.pack(padx=20, pady=(0, 10))
        ctk.CTkLabel(self, text="Case B", font=("Arial", 10),
                     text_color="gray").pack()
        self.combo_b = ctk.CTkComboBox(self, values=cases, width=280)
        self.combo_b.pack(padx=20, pady=(0, 5))
        ctk.CTkButton(self, text="Compare", fg_color=SUCCESS,
                      hover_color="#059669",
                      command=self._go).pack(pady=15, padx=20, fill="x")

    def _go(self):
        a, b = self.combo_a.get(), self.combo_b.get()
        if not a or not b or a == b:
            messagebox.showwarning("Pick Two", "Select two different cases.",
                                   parent=self)
            return
        self.destroy()
        self.on_compare(a, b)


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
    CASE_TEMPLATES = {
        "Custom": None,
        "Theft / Robbery": {"object": "All Objects", "color": "All Colors"},
        "Vehicle Related": {"object": "Vehicle", "color": "All Colors"},
        "Missing Person": {"object": "Person", "color": "All Colors"},
        "Accident": {"object": "Vehicle", "color": "All Colors"},
        "Crowd / Riot": {"object": "Person", "color": "All Colors"},
    }

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

        # ---------------- tracking / analytics state ----------------
        self.track_positions = {}                 # (video, id) -> [(f,cx,cy)]
        self.track_first_seen = {}                 # (video, id) -> frame_idx
        self.track_flagged_loiter = set()
        self.evidence_by_track = {}                # (video, id) -> entry dict
        self.video_hashes = {}
        self._current_video_path = ""

        # ---------------- AI config ----------------
        self.conf_threshold = 0.35
        self.frame_skip = 5
        self.model = None
        self.model_status = "loading"             # loading | ready | failed
        self.model_error = ""
        self.device = "cpu"
        self.gpu_count = 0

        # ---------------- face recognition (optional) ----------------
        self.face_cascade = None
        try:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(cascade_path)
            if not cascade.empty():
                self.face_cascade = cascade
        except Exception as exc:
            log.warning("Face cascade unavailable: %s", exc)
        self.face_recognizer = None
        self.face_labels = {}
        self._fernet_obj = None

        # ---------------- local preferences ----------------
        self.settings = load_settings()

        # ---------------- auth ----------------
        self.auth = AuthClient()

        self.setup_directories()
        self.setup_ui()
        self.process_queue()

        for seq in ("<Motion>", "<KeyPress>", "<Button>"):
            self.bind_all(seq, self._register_activity, add="+")

        # Login gate first; splash + model load start after login succeeds.
        self.login_window = LoginWindow(self, self.auth, self._on_logged_in)

    # ------------------------------------------------------- auto-lock -----
    def _register_activity(self, event=None):
        self._last_activity = time.time()

    def _check_autolock(self):
        minutes = self.settings.get("autolock_minutes", 0)
        if (minutes and not self.is_scanning and not getattr(self, "_locked", False)
                and time.time() - getattr(self, "_last_activity", time.time())
                > minutes * 60):
            self._show_lock_screen()
        self.after(30000, self._check_autolock)

    def _show_lock_screen(self):
        self._locked = True
        lock_win = ctk.CTkToplevel(self)
        lock_win.title("Locked")
        try:
            lock_win.attributes("-fullscreen", True)
        except tk.TclError:
            lock_win.geometry("500x300")
        lock_win.configure(fg_color=BG_DARK)
        lock_win.protocol("WM_DELETE_WINDOW", lambda: None)
        lock_win.grab_set()

        frame = ctk.CTkFrame(lock_win, fg_color="transparent")
        frame.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(frame, text="🔒 Locked (inactive)",
                     font=("Arial Black", 22),
                     text_color=HIGHLIGHT).pack(pady=10)
        pass_entry = ctk.CTkEntry(frame, show="•", placeholder_text="Password",
                                  width=250)
        pass_entry.pack(pady=10)
        msg = ctk.CTkLabel(frame, text="", text_color=DANGER)
        msg.pack()
        btn_unlock = ctk.CTkButton(frame, text="Unlock", fg_color=SUCCESS,
                                   hover_color="#059669")
        btn_unlock.pack(pady=10)

        def unlock_result(ok):
            btn_unlock.configure(state="normal", text="Unlock")
            if ok:
                self._locked = False
                self._register_activity()
                lock_win.destroy()
            else:
                msg.configure(text="Wrong password.")

        def try_unlock():
            pw = pass_entry.get()
            username = self.auth.profile.get("username", "")
            btn_unlock.configure(state="disabled", text="Checking...")

            def worker():
                ok, _ = self.auth.login(username, pw)
                self.after(0, lambda: unlock_result(ok))

            threading.Thread(target=worker, daemon=True).start()

        btn_unlock.configure(command=try_unlock)
        pass_entry.bind("<Return>", lambda e: try_unlock())

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
            gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
            self.gpu_count = gpu_count
            self.gui_queue.put(("gpu_info", gpu_count))
            if gpu_count > 1:
                idx = min(max(0, int(self.settings.get("gpu_index", 0))),
                         gpu_count - 1)
                self.device = f"cuda:{idx}"
            elif gpu_count == 1:
                self.device = "cuda:0"
            else:
                self.device = "cpu"
            model_file = self.settings.get("model_size", "yolov8s.pt")
            log.info("Loading YOLO model %s on %s ...", model_file,
                     self.device.upper())
            model = YOLO(model_file)
            model.to(self.device)
            self.model = model
            self.model_status = "ready"
            log.info("Model ready: %s on %s", model_file, self.device.upper())
            self.gui_queue.put(("model_ready", None))
            self._run_benchmark()
        except Exception as exc:
            self.model_status = "failed"
            self.model_error = str(exc)
            log.error("Model load failed: %s\n%s", exc, traceback.format_exc())
            self.gui_queue.put(("model_failed", str(exc)))

    def _run_benchmark(self):
        """Quick hardware benchmark right after the model loads."""
        try:
            dummy = np.zeros((480, 640, 3), dtype=np.uint8)
            times = []
            for _ in range(5):
                t0 = time.time()
                self.model.predict(dummy, verbose=False)
                times.append(time.time() - t0)
            avg = sum(times) / len(times)
            fps = 1.0 / avg if avg > 0 else 0
            self.gui_queue.put(("benchmark_done",
                                f"~{fps:.1f} FPS on {self.device.upper()}"))
        except Exception as exc:
            log.warning("Benchmark failed: %s", exc)

    def reload_model(self):
        """Reload the AI model after changing model size / GPU in settings."""
        if self.is_scanning:
            messagebox.showwarning("Busy",
                                   "Stop the scan before reloading the model.")
            return
        self.settings["model_size"] = self.model_size_combo.get()
        try:
            gpu_val = self.gpu_combo.get()
            self.settings["gpu_index"] = int(gpu_val) if gpu_val.isdigit() else 0
        except (ValueError, AttributeError):
            pass
        save_settings(self.settings)
        self.model_status = "loading"
        self.model = None
        self.lbl_status.configure(text="Reloading AI model...", text_color=WARNING)
        threading.Thread(target=self._load_model, daemon=True).start()

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
        self.after(500, self._check_resume_state)
        self._last_activity = time.time()
        self._locked = False
        self.after(30000, self._check_autolock)

    # --------------------------------------------------------------- dirs --
    def setup_directories(self):
        os.makedirs(os.path.join(self.base_dir, "Cases"), exist_ok=True)
        try:
            os.makedirs("Known_Suspects", exist_ok=True)
            readme = os.path.join("Known_Suspects", "README.txt")
            if not os.path.exists(readme):
                with open(readme, "w", encoding="utf-8") as f:
                    f.write(
                        "Krishna Intelligence - Known Suspects Folder\n"
                        "=============================================\n"
                        "To enable face-recognition matching, create one\n"
                        "sub-folder per person here, named after them, and\n"
                        "put 2-5 clear face photos (.jpg) inside it, e.g.\n\n"
                        "  Known_Suspects/\n"
                        "    Ramesh Patel/\n"
                        "      photo1.jpg\n"
                        "      photo2.jpg\n\n"
                        "Then press 'Train Face Recognizer' in the software.\n"
                        "Accuracy is basic (LBPH algorithm) - always verify\n"
                        "matches manually before relying on them.\n")
        except OSError as exc:
            log.warning("Could not prepare Known_Suspects folder: %s", exc)

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

        live_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        live_row.pack(pady=(0, 5), padx=10, fill="x")
        ctk.CTkButton(live_row, text="📡 Add Live Camera (RTSP/HTTP)",
                     font=("Arial", 10), height=32, fg_color="#374151",
                     command=self.add_live_camera
                     ).pack(side="left", expand=True, fill="x", padx=(0, 2))
        ctk.CTkButton(live_row, text="👁 Preview 2x/4x", font=("Arial", 10),
                     height=32, fg_color="#374151",
                     command=self.preview_video
                     ).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(live_row, text="🗑 Clear Queue", font=("Arial", 10),
                     height=32, fg_color="#7F1D1D", hover_color=DANGER,
                     command=self.clear_video_queue
                     ).pack(side="left", expand=True, fill="x", padx=(2, 0))

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
        self.case_entry.pack(padx=10, pady=(5, 5), fill="x")

        tmpl_row = ctk.CTkFrame(case_frame, fg_color="transparent")
        tmpl_row.pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkLabel(tmpl_row, text="Template:", font=("Arial", 9)).pack(side="left")
        self.template_combo = ctk.CTkComboBox(
            tmpl_row, values=list(self.CASE_TEMPLATES.keys()),
            width=150, height=26, command=self.apply_case_template)
        self.template_combo.set("Custom")
        self.template_combo.pack(side="left", padx=(6, 0))

        self.status_combo = ctk.CTkComboBox(
            case_frame, values=["Open", "Under Review", "Closed"], height=28)
        self.status_combo.set("Open")
        self.status_combo.pack(padx=10, pady=(0, 5), fill="x")

        self.notes_text = ctk.CTkTextbox(case_frame, height=55,
                                         fg_color=BG_DARK, font=("Arial", 10))
        self.notes_text.pack(padx=10, pady=(0, 10), fill="x")

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

        # ---- advanced AI & security ----
        adv = ctk.CTkFrame(self.sidebar, fg_color=BG_DARK, corner_radius=8)
        adv.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(adv, text="🧪 ADVANCED AI & SECURITY",
                     font=("Arial", 11, "bold"), text_color=ACCENT).pack(pady=(10, 5))

        self.face_rec_switch = ctk.CTkSwitch(
            adv, text="🧑 Face Recognition (known suspects)", font=("Arial", 10))
        self.face_rec_switch.pack(pady=(4, 0), padx=15, anchor="w")
        if not hasattr(cv2, "face"):
            self.face_rec_switch.configure(state="disabled")
            ctk.CTkLabel(adv, text="   (needs opencv-contrib-python)",
                        font=("Arial", 8), text_color="gray").pack(anchor="w", padx=15)

        self.plate_ocr_switch = ctk.CTkSwitch(
            adv, text="🔢 Number Plate OCR (approx)", font=("Arial", 10))
        self.plate_ocr_switch.pack(pady=(4, 0), padx=15, anchor="w")
        if not HAS_TESSERACT:
            self.plate_ocr_switch.configure(state="disabled")
            ctk.CTkLabel(adv, text="   (needs pytesseract + Tesseract-OCR)",
                        font=("Arial", 8), text_color="gray").pack(anchor="w", padx=15)

        self.blur_switch = ctk.CTkSwitch(
            adv, text="🙈 Blur Faces in Evidence", font=("Arial", 10))
        self.blur_switch.pack(pady=(4, 0), padx=15, anchor="w")

        self.watermark_switch = ctk.CTkSwitch(
            adv, text="💧 Watermark Evidence Photos", font=("Arial", 10))
        self.watermark_switch.pack(pady=(4, 0), padx=15, anchor="w")

        self.encrypt_switch = ctk.CTkSwitch(
            adv, text="🔒 Encrypt Evidence on Disk", font=("Arial", 10))
        self.encrypt_switch.pack(pady=(4, 0), padx=15, anchor="w")
        if not HAS_CRYPTO:
            self.encrypt_switch.configure(state="disabled")
            ctk.CTkLabel(adv, text="   (needs: pip install cryptography)",
                        font=("Arial", 8), text_color="gray").pack(anchor="w", padx=15)

        self.overlay_ts_switch = ctk.CTkSwitch(
            adv, text="🕐 Read CCTV Overlay Timestamp (approx)", font=("Arial", 10))
        self.overlay_ts_switch.pack(pady=(4, 10), padx=15, anchor="w")
        if not HAS_TESSERACT:
            self.overlay_ts_switch.configure(state="disabled")

        thresh_row = ctk.CTkFrame(adv, fg_color="transparent")
        thresh_row.pack(fill="x", padx=15, pady=(0, 10))
        ctk.CTkLabel(thresh_row, text="Loiter(s):", font=("Arial", 9)
                     ).grid(row=0, column=0, sticky="w")
        self.loiter_entry = ctk.CTkEntry(thresh_row, width=45, height=24)
        self.loiter_entry.insert(0, str(self.settings.get("loiter_seconds", 30)))
        self.loiter_entry.grid(row=0, column=1, padx=(4, 12))
        ctk.CTkLabel(thresh_row, text="Crowd:", font=("Arial", 9)
                     ).grid(row=0, column=2, sticky="w")
        self.crowd_entry = ctk.CTkEntry(thresh_row, width=45, height=24)
        self.crowd_entry.insert(0, str(self.settings.get("crowd_alert", 8)))
        self.crowd_entry.grid(row=0, column=3, padx=(4, 0))

        model_row = ctk.CTkFrame(adv, fg_color="transparent")
        model_row.pack(fill="x", padx=15, pady=(0, 5))
        ctk.CTkLabel(model_row, text="AI Model:", font=("Arial", 9)).pack(side="left")
        self.model_size_combo = ctk.CTkComboBox(
            model_row, width=110, height=26,
            values=["yolov8n.pt", "yolov8s.pt", "yolov8m.pt",
                    "yolov8l.pt", "yolov8x.pt"])
        self.model_size_combo.set(self.settings.get("model_size", "yolov8s.pt"))
        self.model_size_combo.pack(side="left", padx=(6, 0))

        gpu_row = ctk.CTkFrame(adv, fg_color="transparent")
        gpu_row.pack(fill="x", padx=15, pady=(0, 8))
        ctk.CTkLabel(gpu_row, text="GPU:", font=("Arial", 9)).pack(side="left")
        self.gpu_combo = ctk.CTkComboBox(gpu_row, width=110, height=26,
                                         values=["CPU/GPU0"], state="disabled")
        self.gpu_combo.set("CPU/GPU0")
        self.gpu_combo.pack(side="left", padx=(6, 0))

        ctk.CTkButton(adv, text="🔄 Reload AI Model (apply above)",
                     font=("Arial", 9), height=28, fg_color="#374151",
                     command=self.reload_model).pack(fill="x", padx=15, pady=(0, 8))
        ctk.CTkButton(adv, text="🎯 Train Face Recognizer",
                     font=("Arial", 9), height=28, fg_color="#374151",
                     command=self.train_face_recognizer_ui
                     ).pack(fill="x", padx=15, pady=(0, 8))

        lock_row = ctk.CTkFrame(adv, fg_color="transparent")
        lock_row.pack(fill="x", padx=15, pady=(0, 10))
        ctk.CTkLabel(lock_row, text="Auto-lock (min, 0=off):",
                     font=("Arial", 9)).pack(side="left")
        self.autolock_entry = ctk.CTkEntry(lock_row, width=45, height=24)
        self.autolock_entry.insert(0, str(self.settings.get("autolock_minutes", 0)))
        self.autolock_entry.pack(side="left", padx=(6, 0))
        ctk.CTkButton(lock_row, text="Save", width=45, height=24,
                     command=self._save_autolock).pack(side="left", padx=(6, 0))

        ctk.CTkButton(self.sidebar, text="🌓 Toggle Dark/Light Theme",
                     font=("Arial", 10), fg_color="#374151", height=32,
                     command=self.toggle_theme).pack(pady=(0, 5), padx=10, fill="x")

        # Reports always upload to the web panel; this only retries the
        # queue when an earlier upload failed (no internet at that time).
        ctk.CTkButton(self.sidebar, text="☁ SYNC PENDING REPORTS",
                      font=("Arial", 11, "bold"), fg_color=PURPLE,
                      hover_color="#7C3AED", height=40,
                      command=self.sync_reports).pack(pady=5, padx=10, fill="x")
        ctk.CTkButton(self.sidebar, text="🔧 TEST SERVER & UPLOAD",
                      font=("Arial", 11, "bold"), fg_color="#374151",
                      hover_color="#4B5563", height=36,
                      command=self.run_diagnostics).pack(pady=(0, 5), padx=10, fill="x")
        ctk.CTkButton(self.sidebar, text="📁 OPEN DATABASE",
                      font=("Arial", 11, "bold"), fg_color="#34495E",
                      hover_color=ACCENT, height=40,
                      command=self.open_folder).pack(pady=5, padx=10, fill="x")
        ctk.CTkButton(self.sidebar, text="❓ HELP / ABOUT",
                      font=("Arial", 11, "bold"), fg_color="#34495E",
                      hover_color=ACCENT, height=36,
                      command=self.show_help).pack(pady=(0, 5), padx=10, fill="x")
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
        self.search_entry = ctk.CTkEntry(self.evidence_panel,
                                         placeholder_text="🔍 Search evidence...")
        self.search_entry.pack(fill="x", padx=10, pady=(3, 3))
        self.search_entry.bind("<KeyRelease>", self._filter_gallery)
        self.gallery = ctk.CTkScrollableFrame(self.evidence_panel,
                                              fg_color="transparent")
        self.gallery.pack(expand=True, fill="both", padx=5, pady=5)

        ctk.CTkLabel(self.evidence_panel, text="📅 TIMELINE LOG",
                     font=("Arial", 11, "bold"), text_color=ACCENT
                     ).pack(anchor="w", padx=10, pady=(5, 0))
        self.timeline_text = ctk.CTkTextbox(self.evidence_panel, height=90,
                                            fg_color=BG_DARK,
                                            font=("Courier", 10))
        self.timeline_text.pack(fill="x", padx=10, pady=(0, 5))

        tools1 = ctk.CTkFrame(self.evidence_panel, fg_color="transparent")
        tools1.pack(fill="x", padx=10, pady=(0, 3))
        ctk.CTkButton(tools1, text="➕ Manual", height=28, font=("Arial", 9),
                     fg_color="#374151", command=self.add_manual_evidence
                     ).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(tools1, text="📦 ZIP", height=28, font=("Arial", 9),
                     fg_color="#374151", command=self.bulk_export_zip
                     ).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(tools1, text="📊 Stats", height=28, font=("Arial", 9),
                     fg_color="#374151", command=self.show_analytics
                     ).pack(side="left", expand=True, fill="x", padx=2)

        tools2 = ctk.CTkFrame(self.evidence_panel, fg_color="transparent")
        tools2.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(tools2, text="📁 Recent", height=28, font=("Arial", 9),
                     fg_color="#374151", command=self.show_recent_cases
                     ).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(tools2, text="🆚 Compare", height=28, font=("Arial", 9),
                     fg_color="#374151", command=self.compare_cases
                     ).pack(side="left", expand=True, fill="x", padx=2)
        ctk.CTkButton(tools2, text="🖨 Print", height=28, font=("Arial", 9),
                     fg_color="#374151", command=self.print_last_report
                     ).pack(side="left", expand=True, fill="x", padx=2)

    # -------------------------------------------------------- UI callbacks -
    def _on_video_area_resize(self, event):
        if event.width > 100 and event.height > 100:
            self.display_size = (event.width - 20, event.height - 20)

    def update_speed(self, val):
        self.frame_skip = max(1, int(val))
        self.speed_label.configure(text=f"Speed: Every {self.frame_skip} frames")

    @staticmethod
    def _safe_int(text, default=0):
        try:
            return max(0, int(text))
        except (TypeError, ValueError):
            return default

    def apply_case_template(self, choice):
        tmpl = self.CASE_TEMPLATES.get(choice)
        if not tmpl:
            return
        self.object_filter.set(tmpl["object"])
        self.color_filter.set(tmpl["color"])

    def toggle_theme(self):
        if self.is_scanning:
            messagebox.showwarning(
                "Busy", "Stop the current scan before changing theme — "
                        "restarting would abandon it mid-video.")
            return
        new_theme = "light" if self.settings.get("theme", "dark") == "dark" else "dark"
        self.settings["theme"] = new_theme
        save_settings(self.settings)
        if messagebox.askyesno(
                "Theme Changed",
                f"Switched to {new_theme.upper()} theme.\n"
                "Krishna Intelligence needs to restart to apply the full "
                "color palette.\n\nRestart now?"):
            self.destroy()
            python = sys.executable
            os.execl(python, python, os.path.abspath(__file__))

    def _save_autolock(self):
        self.settings["autolock_minutes"] = self._safe_int(
            self.autolock_entry.get(), 0)
        save_settings(self.settings)
        messagebox.showinfo("Saved", "Auto-lock setting saved.")

    def train_face_recognizer_ui(self):
        if not hasattr(cv2, "face"):
            messagebox.showerror(
                "Unavailable",
                "Face recognition needs 'opencv-contrib-python'.\n"
                "Install it with:\npip install opencv-contrib-python")
            return
        self.lbl_status.configure(text="Training face recognizer...",
                                  text_color=ACCENT)

        def worker():
            ok, msg_text = self._train_face_recognizer()
            self.after(0, lambda: self._train_done(ok, msg_text))

        threading.Thread(target=worker, daemon=True).start()

    def _train_done(self, ok, msg_text):
        self.lbl_status.configure(
            text="✅ System Ready" if self.model_status == "ready"
            else "Please login...", text_color=SUCCESS)
        if ok:
            messagebox.showinfo("Training Complete", msg_text)
        else:
            messagebox.showwarning("Training Failed", msg_text)

    def _train_face_recognizer(self):
        """Train an LBPH recognizer from Known_Suspects/<name>/*.jpg."""
        if not hasattr(cv2, "face"):
            return False, "opencv-contrib-python not installed."
        if self.face_cascade is None:
            return False, "Face detector unavailable on this install."
        base = "Known_Suspects"
        if not os.path.isdir(base):
            return False, "No 'Known_Suspects' folder found."
        people = sorted(d for d in os.listdir(base)
                        if os.path.isdir(os.path.join(base, d)))
        if not people:
            return False, "No suspect sub-folders found in Known_Suspects."
        faces, labels = [], []
        for idx, person in enumerate(people):
            pdir = os.path.join(base, person)
            for fname in os.listdir(pdir):
                img = cv2.imread(os.path.join(pdir, fname), cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                dets = self.face_cascade.detectMultiScale(img, 1.1, 5)
                for (x, y, w, h) in dets:
                    faces.append(cv2.resize(img[y:y + h, x:x + w], (200, 200)))
                    labels.append(idx)
        if not faces:
            return False, "No faces detected in Known_Suspects photos."
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.train(faces, np.array(labels))
        self.face_recognizer = recognizer
        self.face_labels = dict(enumerate(people))
        return True, (f"Trained on {len(people)} known suspect folder(s), "
                      f"{len(faces)} face sample(s).")

    def import_videos(self):
        if self.is_scanning:
            messagebox.showwarning("Busy", "Stop the current scan first.")
            return
        files = filedialog.askopenfilenames(
            title="Select Videos",
            filetypes=[("Video Files",
                       "*.mp4 *.avi *.mkv *.mov *.wmv *.dav *.h264 "
                       "*.ts *.mts *.m4v *.flv *.3gp *.asf")])
        if files:
            # Adds to the queue rather than replacing it, so loading more
            # files never silently discards a live camera (or files)
            # already queued — use 🗑 Clear Queue for a fresh start.
            self.video_list.extend(files)
            self._refresh_queue_label()

    def _refresh_queue_label(self):
        n = len(self.video_list)
        if n == 0:
            self.batch_label.configure(text="Queue: 0 Videos")
            self.video_label.configure(
                text="[ NO SIGNAL ]\nLoad videos to start", text_color="#555555")
            return
        n_live = sum(1 for v in self.video_list if self._is_stream_url(v))
        suffix = f" (incl. {n_live} live)" if n_live else ""
        self.batch_label.configure(text=f"Queue: {n} source(s){suffix}")
        self.video_label.configure(
            text=f"✅ {n} SOURCE(S) LOADED\nReady for Analysis",
            text_color=SUCCESS)
        self.lbl_status.configure(text="Ready to Scan", text_color=SUCCESS)

    def clear_video_queue(self):
        if self.is_scanning:
            messagebox.showwarning("Busy", "Stop the current scan first.")
            return
        if not self.video_list:
            return
        if messagebox.askyesno("Clear Queue",
                               f"Remove all {len(self.video_list)} queued "
                               "source(s)?"):
            self.video_list = []
            self._refresh_queue_label()

    @staticmethod
    def _is_stream_url(source):
        return isinstance(source, str) and source.lower().startswith(
            ("rtsp://", "rtsps://", "http://", "https://"))

    def add_live_camera(self):
        if self.is_scanning:
            messagebox.showwarning("Busy", "Stop the current scan first.")
            return
        url = simpledialog.askstring(
            "Add Live Camera",
            "Enter the RTSP/HTTP camera URL\n"
            "e.g. rtsp://user:pass@192.168.1.10:554/stream1\n\n"
            "Not tested against real camera hardware in development — "
            "please verify with your own CCTV/IP camera and report any "
            "issue.", parent=self)
        if not url:
            return
        url = url.strip()
        if not self._is_stream_url(url):
            messagebox.showwarning(
                "Invalid URL", "URL must start with rtsp://, rtsps://, "
                               "http:// or https://")
            return
        self.video_list.append(url)
        self._refresh_queue_label()
        messagebox.showinfo(
            "Live Camera Added",
            "Live camera added to the queue.\n"
            "⚠ A live feed has no natural end — press ⏹ ABORT when you "
            "want to stop scanning it.")

    def preview_video(self):
        """Quick 2x/4x skim of a video BEFORE running the full AI scan —
        no detection, just a fast visual look at the footage."""
        path = filedialog.askopenfilename(
            title="Select a Video to Preview",
            filetypes=[("Video Files", "*.mp4 *.avi *.mkv *.mov *.wmv "
                                       "*.dav *.h264 *.ts *.mts *.m4v "
                                       "*.flv *.3gp *.asf")])
        if not path:
            return
        speed = simpledialog.askstring(
            "Preview Speed", "Playback speed multiplier (2 or 4):",
            initialvalue="2", parent=self)
        try:
            speed = max(1, int(speed))
        except (TypeError, ValueError):
            speed = 2
        self._preview_stop = False
        win = ctk.CTkToplevel(self)
        win.title(f"Preview ({speed}x) — {os.path.basename(path)}")
        win.configure(fg_color=BG_DARK)
        lbl = ctk.CTkLabel(win, text="Loading...", font=("Courier", 14))
        lbl.pack(padx=10, pady=10)
        ctk.CTkButton(win, text="⏹ Close Preview", fg_color=DANGER,
                     command=lambda: setattr(self, "_preview_stop", True)
                     ).pack(pady=(0, 10))
        win.protocol("WM_DELETE_WINDOW",
                    lambda: (setattr(self, "_preview_stop", True), win.destroy()))

        def worker():
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                self.after(0, lambda: messagebox.showerror(
                    "Error", "Could not open video for preview."))
                self.after(0, win.destroy)
                return
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            frame_delay = 1.0 / (fps if fps > 0 else 25.0)
            frame_idx = 0
            while not self._preview_stop:
                t0 = time.time()
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx % speed == 0:
                    disp_w, disp_h = self.display_size
                    h, w = frame.shape[:2]
                    scale = min(disp_w / w, disp_h / h, 1.0)
                    new_size = (max(2, int(w * scale)), max(2, int(h * scale)))
                    rgb = cv2.cvtColor(cv2.resize(frame, new_size),
                                       cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(rgb)

                    def update(img=pil_img, size=new_size):
                        if self._preview_stop or not win.winfo_exists():
                            return
                        img_ctk = ctk.CTkImage(img, size=size)
                        lbl.configure(image=img_ctk, text="")
                        lbl.image = img_ctk

                    self.after(0, update)
                    # Show playback at roughly `speed`x real time (only the
                    # displayed frames incur the sleep, skipped ones don't).
                    elapsed = time.time() - t0
                    remaining = frame_delay - elapsed
                    if remaining > 0:
                        time.sleep(remaining)
                frame_idx += 1
            cap.release()
            self.after(0, lambda: win.winfo_exists() and win.destroy())

        threading.Thread(target=worker, daemon=True).start()

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
        self._add_recent_case(case_id)

        # Snapshot every UI setting ONCE on the main thread — the worker
        # thread must never touch tkinter widgets directly.
        loiter_seconds = self._safe_int(self.loiter_entry.get(), 30)
        crowd_alert = self._safe_int(self.crowd_entry.get(), 8)
        self.scan_config = {
            "object_filter": self.object_filter.get(),
            "color_filter": self.color_filter.get(),
            "night_mode": bool(self.night_switch.get()),
            "enhance": bool(self.enhance_switch.get()),
            "conf": self.conf_threshold,
            "face_recognition": bool(self.face_rec_switch.get()),
            "plate_ocr": bool(self.plate_ocr_switch.get()),
            "blur_faces": bool(self.blur_switch.get()),
            "watermark": bool(self.watermark_switch.get()),
            "encrypt_evidence": bool(self.encrypt_switch.get()),
            "read_overlay_ts": bool(self.overlay_ts_switch.get()),
            "loiter_seconds": loiter_seconds,
            "crowd_alert": crowd_alert,
        }
        self.settings["loiter_seconds"] = loiter_seconds
        self.settings["crowd_alert"] = crowd_alert
        save_settings(self.settings)

        self.is_scanning = True
        self.is_stopped = False
        self.pause_event.clear()
        self.current_video_idx = 0
        self.tracked_ids.clear()
        self.track_positions.clear()
        self.track_first_seen.clear()
        self.track_flagged_loiter.clear()
        self.evidence_by_track.clear()
        self.video_hashes.clear()
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

        self._save_resume_state()
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

    # ------------------------------------------------------- resume state --
    def _save_resume_state(self):
        try:
            with open(RESUME_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "case_id": self.current_case_id,
                    "video_list": self.video_list,
                    "video_idx": self.current_video_idx,
                    "scan_config": self.scan_config,
                    "saved_at": datetime.now().isoformat(timespec="seconds"),
                }, f)
        except OSError as exc:
            log.warning("Could not save resume state: %s", exc)

    def _clear_resume_state(self):
        try:
            if os.path.exists(RESUME_FILE):
                os.remove(RESUME_FILE)
        except OSError:
            pass

    def _check_resume_state(self):
        try:
            with open(RESUME_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        video_list = data.get("video_list", [])
        idx = data.get("video_idx", 0)
        remaining = len(video_list) - idx
        if remaining <= 0 or not all(os.path.exists(v) for v in video_list[idx:]):
            self._clear_resume_state()
            return
        if not messagebox.askyesno(
                "Resume Scan?",
                f"An interrupted scan was found for case "
                f"'{data.get('case_id')}'.\n{remaining} video(s) remain.\n\n"
                "Resume this scan now?"):
            self._clear_resume_state()
            return

        self._load_case_for_review(data["case_id"])
        self.video_list = video_list
        self.current_video_idx = idx
        self.scan_config = data.get("scan_config", {})
        self.is_scanning = True
        self.is_stopped = False
        self.pause_event.clear()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_pause.configure(state="normal", text="⏸ PAUSE")
        self.btn_import.configure(state="disabled")
        self.batch_label.configure(
            text=f"🔍 Resuming case '{data['case_id']}' — "
                 f"{idx}/{len(video_list)} already done")
        self.process_next_video()

    # -------------------------------------------------------- recent cases
    def _load_recent_cases(self):
        try:
            with open(RECENT_CASES_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def _add_recent_case(self, case_id):
        recents = self._load_recent_cases()
        recents = [c for c in recents if c.get("case_id") != case_id]
        recents.insert(0, {"case_id": case_id,
                           "opened_at": datetime.now().isoformat(timespec="seconds")})
        recents = recents[:20]
        try:
            with open(RECENT_CASES_FILE, "w", encoding="utf-8") as f:
                json.dump(recents, f, indent=2)
        except OSError as exc:
            log.warning("Could not save recent cases: %s", exc)

    def _list_case_ids(self):
        d = os.path.join(self.base_dir, "Cases")
        if not os.path.isdir(d):
            return []
        return sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)))

    def show_recent_cases(self):
        recents = self._load_recent_cases()
        if not recents:
            messagebox.showinfo("Recent Cases", "No recent cases yet.")
            return
        win = ctk.CTkToplevel(self)
        win.title("📁 Recent Cases")
        win.geometry("380x420")
        win.configure(fg_color=BG_DARK)
        ctk.CTkLabel(win, text="📁 Recent Cases (click to review)",
                     font=("Arial", 13, "bold"),
                     text_color=HIGHLIGHT).pack(pady=10)
        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(expand=True, fill="both", padx=10, pady=10)
        for c in recents:
            row = ctk.CTkFrame(scroll, fg_color=PANEL_BG, corner_radius=6)
            row.pack(fill="x", pady=3)
            ctk.CTkButton(
                row, text=f"📂 {c['case_id']}", anchor="w",
                fg_color="transparent", hover_color="#1F2937",
                command=lambda cid=c["case_id"], w=win: (
                    w.destroy(), self._load_case_for_review(cid))
            ).pack(fill="x", padx=5, pady=5)

    def _load_case_for_review(self, case_id):
        """Rebuild the gallery from evidence photos already saved on disk
        for a past case (best-effort filename parsing; read-only)."""
        case_dir = os.path.join(self.base_dir, "Cases", case_id)
        if not os.path.isdir(case_dir):
            messagebox.showwarning("Not Found",
                                   f"Case folder not found:\n{case_dir}")
            return
        self.clear_gallery()
        self.evidence_database.clear()
        self.timeline_text.delete("1.0", tk.END)
        count = 0
        for root, _, files in os.walk(case_dir):
            for fname in sorted(files):
                low = fname.lower()
                if not (low.endswith(".jpg") or low.endswith(".jpeg")
                       or low.endswith(".png") or low.endswith(".jpg.enc")):
                    continue
                fpath = os.path.join(root, fname)
                m = re.match(r"ID_(\S+?)_(\w+)_(\w+)_(\d+m_\d+s)", fname)
                encrypted = fname.endswith(".enc")
                entry = {
                    "filename": fname,
                    "type": m.group(3) if m else "Unknown",
                    "track_id": m.group(1) if m else "-",
                    "color": m.group(2) if m else "-",
                    "timestamp": m.group(4) if m else "-",
                    "video": os.path.basename(root), "filepath": fpath,
                    "source_path": "", "frame_idx": 0,
                    "note": "", "starred": False, "encrypted": encrypted,
                    "upper_color": "", "lower_color": "", "direction": "",
                    "speed_px_s": 0, "face_match": "", "plate_text": "",
                }
                try:
                    if encrypted:
                        thumb_img = Image.new("RGB", (100, 60), "#333333")
                    else:
                        thumb_img = Image.open(fpath)
                except Exception:
                    continue
                self.evidence_database.append(entry)
                self.gui_queue.put(("evidence", thumb_img, entry))
                count += 1
        self.current_case_id = case_id
        self.current_case_dir = case_dir
        self.case_entry.delete(0, tk.END)
        self.case_entry.insert(0, case_id)
        self.timeline_text.insert(
            tk.END, f"📂 Loaded {count} evidence item(s) from case "
                    f"'{case_id}' for review.\n")
        self.lbl_status.configure(text=f"Reviewing case: {case_id}",
                                  text_color=ACCENT)

    def compare_cases(self):
        cases = self._list_case_ids()
        if len(cases) < 2:
            messagebox.showinfo("Compare Cases",
                                "Need at least 2 saved cases to compare.")
            return
        CaseCompareDialog(self, cases, self._do_compare)

    def _do_compare(self, case_a, case_b):
        def sig(case_id):
            d = os.path.join(self.base_dir, "Cases", case_id)
            sigs = set()
            for root, _, files in os.walk(d):
                for fname in files:
                    m = re.match(r"ID_(\S+?)_(\w+)_(\w+)_", fname)
                    if m:
                        sigs.add((m.group(3), m.group(2)))  # (type, color)
            return sigs

        common = sig(case_a) & sig(case_b)
        msg = (f"Possible common type+color combinations between\n"
               f"'{case_a}' and '{case_b}':\n\n" +
               ("\n".join(f"- {t} ({c})" for t, c in sorted(common))
                if common else "None found.") +
               "\n\n⚠ This is a rough heuristic (type + color only) — "
               "NOT identity confirmation. Verify manually.")
        messagebox.showinfo("Comparison Result", msg)

    def _cross_video_matches(self):
        groups = defaultdict(set)
        for e in self.evidence_database:
            groups[(e["type"], e["color"])].add(e["video"])
        matches = []
        for (t, c), vids in groups.items():
            if len(vids) > 1:
                matches.append(f"{t} ({c}) seen across: {', '.join(sorted(vids))}")
        return matches

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

    def _try_ffmpeg_repair(self, video_path):
        """Best-effort remux of a video ffmpeg/OpenCV refuses to open."""
        if not shutil.which("ffmpeg"):
            return None
        try:
            tmp = os.path.join(
                tempfile.gettempdir(),
                f"krishna_repair_{os.getpid()}_{int(time.time())}.mp4")
            subprocess.run(
                ["ffmpeg", "-y", "-err_detect", "ignore_err", "-i", video_path,
                 "-c", "copy", tmp],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=120, check=False)
            if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
                return tmp
        except Exception as exc:
            log.warning("ffmpeg repair failed: %s", exc)
        return None

    def _read_overlay_timestamp(self, frame):
        """Best-effort OCR of a CCTV date/time burned into the top-left
        corner of the frame. Accuracy depends entirely on the camera's
        overlay style/font — treat as approximate."""
        if not HAS_TESSERACT:
            return ""
        try:
            h, w = frame.shape[:2]
            roi = frame[0:int(h * 0.08), 0:int(w * 0.35)]
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=2, fy=2)
            text = pytesseract.image_to_string(gray, config="--psm 7")
            return text.strip()
        except Exception:
            return ""

    def _run_video(self, video_path, config):
        is_stream = self._is_stream_url(video_path)
        if is_stream:
            vid_name = "LIVE_" + re.sub(r"[^A-Za-z0-9]+", "_",
                                        video_path)[:40].strip("_")
        else:
            vid_name = os.path.splitext(os.path.basename(video_path))[0]
        vid_name = "".join(c if c.isalnum() or c in "-_ " else "_"
                           for c in vid_name) or "video"
        output_dir = os.path.join(self.current_case_dir, vid_name)
        os.makedirs(output_dir, exist_ok=True)
        self._current_video_path = video_path

        repaired_tmp = None
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened() and not is_stream:
            repaired_tmp = self._try_ffmpeg_repair(video_path)
            if repaired_tmp:
                cap = cv2.VideoCapture(repaired_tmp)
                self.gui_queue.put(
                    ("video_error",
                     f"🔧 Repaired and reopened corrupt video: "
                     f"{os.path.basename(video_path)}\n"))
        if not cap.isOpened():
            self.gui_queue.put(
                ("video_error",
                 f"⚠ Could not open "
                 f"{'live camera' if is_stream else 'video'}: "
                 f"{video_path if is_stream else os.path.basename(video_path)}\n"))
            if repaired_tmp and os.path.exists(repaired_tmp):
                try:
                    os.remove(repaired_tmp)
                except OSError:
                    pass
            return

        if is_stream:
            self.video_hashes[vid_name] = "N/A (live camera stream)"
        else:
            try:
                self.video_hashes[vid_name] = sha256_file(video_path)
            except OSError as exc:
                log.warning("Could not hash video %s: %s", video_path, exc)
                self.video_hashes[vid_name] = ""

        # Fresh tracker per video so IDs never carry over between files.
        self._reset_tracker()

        rotate_code = None
        try:
            meta = int(cap.get(cv2.CAP_PROP_ORIENTATION_META))
            rotate_code = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                           270: cv2.ROTATE_90_COUNTERCLOCKWISE}.get(meta)
        except Exception:
            rotate_code = None

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 0 or fps != fps:  # 0 / NaN safety
            fps = 30.0
        frame_idx = 0
        start_time = time.time()
        overlay_read = False

        try:
            while not self.is_stopped:
                while self.pause_event.is_set() and not self.is_stopped:
                    time.sleep(0.1)

                ret, frame = cap.read()
                if not ret:
                    break
                if rotate_code is not None:
                    frame = cv2.rotate(frame, rotate_code)

                if not overlay_read and config.get("read_overlay_ts"):
                    overlay_read = True
                    ts_text = self._read_overlay_timestamp(frame)
                    if ts_text:
                        self.gui_queue.put(
                            ("timeline",
                             f"🕐 Overlay timestamp (OCR, approx) for "
                             f"{vid_name}: {ts_text}\n"))

                if frame_idx % self.frame_skip == 0:
                    self._process_frame(frame, frame_idx, fps, vid_name,
                                        output_dir, config)

                    elapsed = time.time() - start_time
                    speed = frame_idx / elapsed if elapsed > 0 else 0.0
                    self.gui_queue.put(("progress",
                                        frame_idx / total_frames
                                        if total_frames > 0 else 0))
                    perf_text = (f"🔴 LIVE | ⚡ {speed:.1f} FPS" if is_stream
                                else f"⚡ Speed: {speed:.1f} FPS")
                    self.gui_queue.put(("performance", perf_text))
                frame_idx += 1
        finally:
            cap.release()
            if repaired_tmp and os.path.exists(repaired_tmp):
                try:
                    os.remove(repaired_tmp)
                except OSError:
                    pass

    def _process_frame(self, frame, frame_idx, fps, vid_name, output_dir, config):
        results = self.model.track(frame, conf=config["conf"],
                                   persist=True, verbose=False)
        result = results[0]
        annotated = result.plot()

        if result.boxes.id is not None:
            ids = result.boxes.id.int().cpu().tolist()
            clss = result.boxes.cls.int().cpu().tolist()
            boxes = result.boxes.xyxy.cpu().numpy()

            # Track history (all detected ids) feeds direction/speed and
            # loitering/crowd alerts — independent of evidence dedupe.
            person_count = 0
            for box, tid, cls in zip(boxes, ids, clss):
                if cls == 0:
                    person_count += 1
                key = (vid_name, tid)
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                hist = self.track_positions.setdefault(key, [])
                hist.append((frame_idx, cx, cy))
                if len(hist) > 40:
                    hist.pop(0)
                # Evidence is captured on first sighting (no history yet),
                # so keep its direction/speed fresh as the track moves.
                tracked_entry = self.evidence_by_track.get(key)
                if tracked_entry is not None:
                    tracked_entry["direction"] = self._movement_direction(
                        vid_name, tid)
                    tracked_entry["speed_px_s"] = round(
                        self._movement_speed(vid_name, tid, fps), 1)
                if key not in self.track_first_seen:
                    self.track_first_seen[key] = frame_idx
                elapsed_sec = (frame_idx - self.track_first_seen[key]) / fps
                loiter_limit = config.get("loiter_seconds", 0)
                if (loiter_limit and elapsed_sec >= loiter_limit
                        and key not in self.track_flagged_loiter):
                    self.track_flagged_loiter.add(key)
                    self.gui_queue.put(
                        ("timeline",
                         f"⚠ Loitering Alert: ID {tid} present "
                         f"{int(elapsed_sec)}s in {vid_name}\n"))

            if person_count > self.stats.get("max_crowd", 0):
                self.stats["max_crowd"] = person_count
            crowd_limit = config.get("crowd_alert", 0)
            if (crowd_limit and person_count >= crowd_limit
                    and frame_idx % max(1, self.frame_skip * 20) == 0):
                self.gui_queue.put(
                    ("timeline",
                     f"👥 Crowd Alert: {person_count} persons visible in "
                     f"{vid_name} (frame {frame_idx})\n"))

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

        # ---- extra AI analysis (best-effort, never blocks capture) ----
        upper_color, lower_color = "", ""
        face_match_name = ""
        plate_text = ""
        try:
            if cat_name == "Person":
                upper_color, lower_color = self._clothing_colors(crop)
                if config.get("face_recognition") and self.face_recognizer is not None:
                    match = self._try_face_match(crop)
                    if match:
                        face_match_name = match[0]
            elif cat_name in self.VEHICLES and config.get("plate_ocr"):
                plate_text = self._read_plate(crop)
        except Exception as exc:
            log.warning("Extra analysis failed for ID %s: %s", tid, exc)

        if (cat_name == "Person" and config.get("blur_faces")
                and self.face_cascade is not None):
            try:
                crop = self._blur_faces(crop)
            except Exception as exc:
                log.warning("Face blur failed: %s", exc)

        if config["night_mode"]:
            crop = self.enhance_night(crop)
        elif config["enhance"]:
            crop = self.enhance_basic(crop)

        if config.get("watermark"):
            crop = self._apply_watermark(crop)

        direction = self._movement_direction(vid_name, tid)
        speed_px_s = self._movement_speed(vid_name, tid, fps)

        seconds = int(frame_idx / fps)
        timestamp_str = f"{seconds // 60:02d}m_{seconds % 60:02d}s"
        base_filename = f"ID_{tid}_{color}_{cat_name}_{timestamp_str}_f{frame_idx}.jpg"

        ok, buf = cv2.imencode(".jpg", crop)
        if not ok:
            return
        raw_bytes = buf.tobytes()

        encrypted = bool(config.get("encrypt_evidence")) and HAS_CRYPTO
        filename = base_filename + (".enc" if encrypted else "")
        filepath = os.path.join(output_dir, filename)
        try:
            if encrypted:
                token = self._fernet().encrypt(raw_bytes)
                with open(filepath, "wb") as f:
                    f.write(token)
            else:
                with open(filepath, "wb") as f:
                    f.write(raw_bytes)
        except OSError as exc:
            log.error("Could not save evidence file: %s", exc)
            return

        if cat_name == "Person":
            self.stats["persons"] += 1
        elif cat_name in self.VEHICLES:
            self.stats["vehicles"] += 1

        entry = {
            "filename": filename, "type": cat_name, "track_id": tid,
            "color": color, "timestamp": timestamp_str, "video": vid_name,
            "filepath": os.path.abspath(filepath),
            "source_path": self._current_video_path, "frame_idx": frame_idx,
            "note": "", "starred": False, "encrypted": encrypted,
            "upper_color": upper_color, "lower_color": lower_color,
            "direction": direction, "speed_px_s": round(speed_px_s, 1),
            "face_match": face_match_name, "plate_text": plate_text,
        }
        self.evidence_database.append(entry)
        self.evidence_by_track[key] = entry

        tl = (f"[{vid_name} {timestamp_str}] {cat_name} (ID:{tid}) | "
              f"Color: {color}")
        if face_match_name:
            tl += f" | ⚠ POSSIBLE MATCH: {face_match_name}"
        if plate_text:
            tl += f" | Plate(OCR): {plate_text}"
        if direction:
            tl += f" | Dir: {direction}"
        tl += "\n"
        self.gui_queue.put(("timeline", tl))

        decoded = cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
        crop_rgb = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
        self.gui_queue.put(("evidence", Image.fromarray(crop_rgb), entry))
        self.gui_queue.put(("stats_update", None))

    # -------------------------------------------------- extra AI helpers --
    def _clothing_colors(self, crop):
        h, w = crop.shape[:2]
        upper = crop[int(h * 0.15):int(h * 0.5), int(w * 0.15):int(w * 0.85)]
        lower = crop[int(h * 0.5):int(h * 0.9), int(w * 0.15):int(w * 0.85)]
        up = self.detect_color(upper) if upper.size else "Unknown"
        lo = self.detect_color(lower) if lower.size else "Unknown"
        return up, lo

    def _movement_direction(self, vid_name, tid):
        hist = self.track_positions.get((vid_name, tid))
        if not hist or len(hist) < 2:
            return ""
        _, x0, y0 = hist[0]
        _, x1, y1 = hist[-1]
        dx, dy = x1 - x0, y1 - y0
        if abs(dx) < 15 and abs(dy) < 15:
            return "Stationary"
        angle = math.degrees(math.atan2(-dy, dx))
        dirs = ["East", "NE", "North", "NW", "West", "SW", "South", "SE"]
        idx = int((angle + 22.5) % 360 // 45)
        return dirs[idx]

    def _movement_speed(self, vid_name, tid, fps):
        """Approximate, uncalibrated speed in pixels/second (relative
        only — there is no real-world distance reference from a single
        camera, so this is NOT a calibrated km/h speed)."""
        hist = self.track_positions.get((vid_name, tid))
        if not hist or len(hist) < 2:
            return 0.0
        f0, x0, y0 = hist[0]
        f1, x1, y1 = hist[-1]
        dist_px = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        seconds = (f1 - f0) / fps
        return dist_px / seconds if seconds > 0 else 0.0

    def _fernet(self):
        if not HAS_CRYPTO:
            return None
        if self._fernet_obj is None:
            self._fernet_obj = Fernet(get_or_create_encryption_key())
        return self._fernet_obj

    def _blur_faces(self, crop_bgr):
        if self.face_cascade is None:
            return crop_bgr
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        dets = self.face_cascade.detectMultiScale(gray, 1.1, 5)
        out = crop_bgr.copy()
        for (x, y, w, h) in dets:
            roi = out[y:y + h, x:x + w]
            out[y:y + h, x:x + w] = cv2.GaussianBlur(roi, (23, 23), 30)
        return out

    def _try_face_match(self, crop_bgr):
        if self.face_recognizer is None or self.face_cascade is None:
            return None
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        dets = self.face_cascade.detectMultiScale(gray, 1.1, 5)
        if len(dets) == 0:
            return None
        x, y, w, h = max(dets, key=lambda d: d[2] * d[3])
        face = cv2.resize(gray[y:y + h, x:x + w], (200, 200))
        label, confidence = self.face_recognizer.predict(face)
        if confidence < 80:  # LBPH: lower = better match
            return self.face_labels.get(label, "Unknown"), confidence
        return None

    def _read_plate(self, crop_bgr):
        """Best-effort number-plate OCR on the whole vehicle crop (no
        dedicated plate detector) — works best on close, sharp plates."""
        if not HAS_TESSERACT:
            return ""
        try:
            gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, None, fx=2, fy=2,
                              interpolation=cv2.INTER_CUBIC)
            _, thresh = cv2.threshold(gray, 0, 255,
                                      cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            text = pytesseract.image_to_string(
                thresh,
                config="--psm 7 -c tessedit_char_whitelist="
                       "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
            text = re.sub(r"[^A-Z0-9]", "", text.upper())
            return text[:15]
        except Exception as exc:
            log.warning("Plate OCR failed: %s", exc)
            return ""

    def _apply_watermark(self, image):
        try:
            h, _ = image.shape[:2]
            text = f"{APP_NAME} - EVIDENCE"
            out = image.copy()
            cv2.putText(out, text, (5, h - 6), cv2.FONT_HERSHEY_SIMPLEX,
                       0.35, (0, 0, 0), 2, cv2.LINE_AA)
            cv2.putText(out, text, (5, h - 6), cv2.FONT_HERSHEY_SIMPLEX,
                       0.35, (255, 255, 255), 1, cv2.LINE_AA)
            return out
        except Exception as exc:
            log.warning("Watermark failed: %s", exc)
            return image

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
        self._clear_resume_state()

        if not self.current_case_dir:
            return

        for match in self._cross_video_matches():
            self.gui_queue.put(("timeline", f"🔗 {match}\n"))

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
        # Pre-generate the report's view token client-side so the PDF's QR
        # code (built next) can point at the exact final URL.
        client_token = secrets.token_hex(24)
        view_url = (f"{self.auth.server_url}/view.php?t={client_token}"
                   if self.auth.server_url else "")
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
                "case_status": self.status_combo.get(),
                "case_notes": self.notes_text.get("1.0", tk.END).strip(),
                "videos": [os.path.basename(v) for v in self.video_list],
                "video_hashes": dict(self.video_hashes),
                "stats": {"persons": self.stats.get("persons", 0),
                          "vehicles": self.stats.get("vehicles", 0),
                          "max_crowd": self.stats.get("max_crowd", 0),
                          "total_evidence": len(self.evidence_database)},
                "possible_cross_video_matches": self._cross_video_matches(),
                "verification_code": self._report_verification_code(),
                "evidence": self.evidence_database,
            }
            with open(os.path.join(qdir, "report.json"), "w",
                      encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            pdf_ok, pdf_err = self._build_pdf(os.path.join(qdir, "report.pdf"),
                                              qr_url=view_url)
            if not pdf_ok:
                log.warning("PDF build failed: %s", pdf_err)

            meta = {"case_id": self.current_case_id,
                    "persons": self.stats.get("persons", 0),
                    "vehicles": self.stats.get("vehicles", 0),
                    "total": len(self.evidence_database),
                    "client_token": client_token}
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
                ok, result, wa_sent = self.auth.upload_report(
                    meta.get("case_id", "CASE"),
                    os.path.join(qdir, "report.pdf"),
                    os.path.join(qdir, "report.json"), meta,
                    client_token=meta.get("client_token", ""))
                if ok:
                    shutil.rmtree(qdir, ignore_errors=True)
                self.gui_queue.put(("upload_result", ok, result,
                                    meta.get("case_id", ""), wa_sent))
                if not ok:
                    break  # server unreachable — keep the rest queued

        threading.Thread(target=worker, daemon=True).start()

    def run_diagnostics(self):
        """Step through the whole report pipeline (reachability, server
        config, login session) and show exactly where it breaks — for
        diagnosing 'report / WhatsApp not arriving' without needing to
        read server logs."""
        self.lbl_status.configure(text="🔧 Testing server connection...",
                                  text_color=ACCENT)

        def worker():
            steps = self.auth.diagnose()
            self.after(0, lambda: self._show_diagnostics(steps))

        threading.Thread(target=worker, daemon=True).start()

    def _show_diagnostics(self, steps):
        self.lbl_status.configure(text="✅ System Ready" if self.model_status == "ready"
                                  else "Please login...", text_color=SUCCESS)
        win = ctk.CTkToplevel(self)
        win.title("🔧 Server & Upload Diagnostics")
        win.geometry("520x420")
        win.configure(fg_color=BG_DARK)
        ctk.CTkLabel(win, text="🔧 Server & Upload Diagnostics",
                     font=("Arial Black", 15),
                     text_color=HIGHLIGHT).pack(pady=(15, 10))
        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(expand=True, fill="both", padx=15, pady=(0, 10))
        for label, ok, detail in steps:
            row = ctk.CTkFrame(scroll, fg_color=PANEL_BG, corner_radius=6)
            row.pack(fill="x", pady=3)
            icon = "✅" if ok else "❌"
            color = SUCCESS if ok else DANGER
            ctk.CTkLabel(row, text=f"{icon} {label}", font=("Arial", 12, "bold"),
                        text_color=color, anchor="w").pack(fill="x", padx=10,
                                                            pady=(8, 0))
            ctk.CTkLabel(row, text=str(detail), font=("Courier", 10),
                        text_color="gray", anchor="w", wraplength=450,
                        justify="left").pack(fill="x", padx=10, pady=(0, 8))
        all_ok = all(ok for _, ok, _ in steps)
        ctk.CTkLabel(win,
                    text="✅ Everything checks out." if all_ok else
                    "⚠ Fix the ❌ item(s) above, starting from the top — "
                    "later steps depend on earlier ones.",
                    font=("Arial", 11, "bold"),
                    text_color=SUCCESS if all_ok else WARNING,
                    wraplength=470).pack(pady=(0, 15), padx=15)

    def _report_verification_code(self):
        """A lightweight authenticity marker (SHA-256 short code), not a
        legal PKI digital signature — useful to spot-check that a report's
        headline numbers were not altered after generation."""
        raw = (f"{self.current_case_id}|{self.stats.get('persons', 0)}|"
               f"{self.stats.get('vehicles', 0)}|{len(self.evidence_database)}|"
               f"{self.auth.profile.get('username', '')}")
        return hashlib.sha256(raw.encode()).hexdigest()[:10].upper()

    # ---------------------------------------------------------- PDF build --
    def _build_pdf(self, path, qr_url=""):
        """Write the case PDF report to `path`. Returns (ok, error).

        `qr_url`, if given, embeds a QR code linking to the report's own
        online view URL — pre-generated client-side so the code in the
        PDF matches the address the report ends up living at."""
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
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except ImportError:
            return False, "reportlab is not installed (pip install reportlab)."

        # Optional Gujarati Unicode font for case notes — only active if the
        # operator has placed a font file at fonts/NotoSansGujarati-Regular.ttf
        # (not bundled here). Falls back to the default Latin font otherwise,
        # in which case Gujarati text in notes will not render correctly.
        gujarati_font = None
        try:
            if os.path.exists(GUJARATI_FONT_PATH):
                pdfmetrics.registerFont(TTFont("NotoGujarati", GUJARATI_FONT_PATH))
                gujarati_font = "NotoGujarati"
        except Exception as exc:
            log.warning("Gujarati font registration failed: %s", exc)

        qr_flowable = None
        if qr_url and HAS_QRCODE:
            try:
                qr_img = qrcode.make(qr_url)
                qr_buf = io.BytesIO()
                qr_img.save(qr_buf, format="PNG")
                qr_buf.seek(0)
                qr_flowable = RLImage(qr_buf, width=2.8 * cm, height=2.8 * cm)
            except Exception as exc:
                log.warning("QR code generation failed: %s", exc)

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
                Paragraph(f"<b>Case Status:</b> {self.status_combo.get()}", small),
            ]
            case_notes = self.notes_text.get("1.0", tk.END).strip()
            if case_notes:
                note_style = small
                if gujarati_font:
                    note_style = ParagraphStyle(
                        "Notes", parent=small, fontName=gujarati_font)
                story.append(Paragraph(
                    f"<b>Case Notes:</b> {case_notes}", note_style))
            story.append(Spacer(1, 14))

            rows = [["Photo", "Details"]]
            for item in self.evidence_database:
                extra = ""
                if item.get("upper_color") or item.get("lower_color"):
                    extra += (f"Clothing: {item.get('upper_color', '-')} (top) / "
                             f"{item.get('lower_color', '-')} (bottom)<br/>")
                if item.get("direction"):
                    extra += (f"Direction: {item['direction']} | "
                             f"Speed(approx): {item.get('speed_px_s', 0)} px/s<br/>")
                if item.get("face_match"):
                    extra += f"⚠ Possible Match: {item['face_match']}<br/>"
                if item.get("plate_text"):
                    extra += f"Plate (OCR, approx): {item['plate_text']}<br/>"
                if item.get("note"):
                    extra += f"Note: {item['note']}<br/>"
                details = Paragraph(
                    f"<b>{item['type']}</b> (Track ID {item['track_id']})"
                    f"{' ★' if item.get('starred') else ''}<br/>"
                    f"Color: {item['color']}<br/>"
                    f"Time: {item['timestamp'].replace('_', ' ')}<br/>"
                    f"Video: {item['video']}<br/>"
                    f"File: {item['filename']}<br/>" + extra, small)

                img_source = None
                img_path = item.get("filepath", "")
                if item.get("encrypted") and HAS_CRYPTO and img_path \
                        and os.path.exists(img_path):
                    try:
                        with open(img_path, "rb") as f:
                            token = f.read()
                        raw = self._fernet().decrypt(token)
                        img_source = io.BytesIO(raw)
                    except Exception:
                        img_source = None
                elif img_path and os.path.exists(img_path):
                    img_source = img_path

                if img_source is not None:
                    try:
                        img = RLImage(img_source)
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

            matches = self._cross_video_matches()
            if matches:
                story.append(Spacer(1, 10))
                story.append(Paragraph("<b>Possible cross-video matches "
                                       "(heuristic, verify manually):</b>", small))
                for m in matches:
                    story.append(Paragraph(f"- {m}", small))

            story.append(Spacer(1, 12))
            story.append(Paragraph(
                f"<b>Digitally verified by:</b> {operator} &nbsp;&nbsp; "
                f"<b>Verification Code:</b> {self._report_verification_code()}",
                small))
            if qr_flowable is not None:
                story.append(Spacer(1, 8))
                story.append(qr_flowable)
                story.append(Paragraph(
                    "📱 Scan to open/verify this report online", small))

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

    def _safe_remove(self, path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def print_last_report(self):
        """Print the current in-memory report via a temp PDF that is
        deleted right after handoff — no persistent local report copy,
        consistent with the 'reports live only on the web panel' rule."""
        if not self.evidence_database:
            messagebox.showwarning("No Report", "No evidence captured yet to print.")
            return
        tmp_path = os.path.join(tempfile.gettempdir(),
                                f"krishna_print_{int(time.time())}.pdf")
        ok, err = self._build_pdf(tmp_path)
        if not ok:
            messagebox.showerror("Print Failed", f"Could not build report:\n{err}")
            return
        try:
            if sys.platform == "win32":
                os.startfile(tmp_path, "print")
            else:
                subprocess.Popen(["lp", tmp_path])
            messagebox.showinfo("Printing", "Report sent to the printer.")
        except Exception as exc:
            messagebox.showerror("Print Failed", f"Could not print:\n{exc}")
        finally:
            self.after(15000, lambda: self._safe_remove(tmp_path))

    def _ensure_case(self):
        """Make sure a case folder exists, prompting for a Case ID if the
        operator wants to add evidence before starting a video scan."""
        if self.current_case_dir:
            return True
        case_id = simpledialog.askstring("Case ID", "Enter Case ID:", parent=self)
        if not case_id:
            return False
        case_id = "".join(c if c.isalnum() or c in "-_ " else "_"
                          for c in case_id.strip())
        self.current_case_id = case_id
        self.current_case_dir = os.path.join(self.base_dir, "Cases", case_id)
        os.makedirs(self.current_case_dir, exist_ok=True)
        self._add_recent_case(case_id)
        self.case_entry.delete(0, tk.END)
        self.case_entry.insert(0, case_id)
        return True

    def add_manual_evidence(self):
        if not self._ensure_case():
            return
        path = filedialog.askopenfilename(
            title="Select Evidence Photo",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png")])
        if not path:
            return
        try:
            img = Image.open(path).convert("RGB")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not open image:\n{exc}")
            return
        cat = simpledialog.askstring(
            "Evidence Type",
            "Type (Person/Car/Motorcycle/Bus/Truck/Other):",
            initialvalue="Person", parent=self)
        if not cat:
            return
        manual_dir = os.path.join(self.current_case_dir, "Manual")
        os.makedirs(manual_dir, exist_ok=True)
        ts = datetime.now().strftime("%H%M%S")
        filename = f"MANUAL_{cat}_{ts}.jpg"
        filepath = os.path.join(manual_dir, filename)
        img.save(filepath, "JPEG")
        crop_bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        color = self.detect_color(crop_bgr)
        entry = {
            "filename": filename, "type": cat, "track_id": "MANUAL",
            "color": color, "timestamp": ts, "video": "Manual Entry",
            "filepath": os.path.abspath(filepath),
            "source_path": "", "frame_idx": 0,
            "note": "", "starred": False, "encrypted": False,
            "upper_color": "", "lower_color": "", "direction": "",
            "speed_px_s": 0, "face_match": "", "plate_text": "",
        }
        self.evidence_database.append(entry)
        self.gui_queue.put(("evidence", img, entry))
        self.gui_queue.put(("stats_update", None))
        self.gui_queue.put(("timeline",
                            f"➕ Manual evidence added: {cat} ({filename})\n"))

    def bulk_export_zip(self):
        if not self.current_case_dir or not os.path.isdir(self.current_case_dir):
            messagebox.showwarning("No Case", "No case evidence to export yet.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".zip", filetypes=[("ZIP Archive", "*.zip")],
            initialfile=f"{self.current_case_id or 'case'}_evidence.zip")
        if not path:
            return
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(self.current_case_dir):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        arcname = os.path.relpath(fpath, self.current_case_dir)
                        zf.write(fpath, arcname)
            messagebox.showinfo("Exported", f"Evidence photos zipped to:\n{path}")
        except OSError as exc:
            messagebox.showerror("Export Failed", f"Could not create ZIP:\n{exc}")

    def _view_evidence(self, entry):
        path = entry.get("filepath", "")
        try:
            if entry.get("encrypted"):
                if not HAS_CRYPTO:
                    messagebox.showerror(
                        "Unavailable",
                        "This evidence is encrypted but the 'cryptography' "
                        "package is not installed on this PC.")
                    return
                with open(path, "rb") as f:
                    token = f.read()
                raw = self._fernet().decrypt(token)
                img = Image.open(io.BytesIO(raw))
            else:
                img = Image.open(path)
            self._show_zoom_viewer(img, entry)
        except Exception as exc:
            messagebox.showerror("View Failed", f"Could not open evidence:\n{exc}")

    def _show_zoom_viewer(self, pil_img, entry):
        win = ctk.CTkToplevel(self)
        win.title(f"Evidence — ID {entry.get('track_id', '-')}")
        win.configure(fg_color=BG_DARK)
        w, h = pil_img.size
        scale = min(900 / w, 700 / h, 3.0)
        disp = pil_img.resize((max(1, int(w * scale)), max(1, int(h * scale))))
        img_ctk = ctk.CTkImage(disp, size=disp.size)
        ctk.CTkLabel(win, image=img_ctk, text="").pack(padx=10, pady=10)

        info = (f"ID {entry.get('track_id', '-')} | {entry.get('type', '-')} | "
               f"{entry.get('color', '-')}\n"
               f"{str(entry.get('timestamp', '')).replace('_', ' ')} | "
               f"{entry.get('video', '-')}")
        if entry.get("upper_color") or entry.get("lower_color"):
            info += (f"\nClothing: {entry.get('upper_color', '-')} (top) / "
                     f"{entry.get('lower_color', '-')} (bottom)")
        if entry.get("direction"):
            info += (f"\nDirection: {entry['direction']} | Speed(approx): "
                     f"{entry.get('speed_px_s', 0)} px/s")
        if entry.get("face_match"):
            info += f"\n⚠ Possible Match: {entry['face_match']}"
        if entry.get("plate_text"):
            info += f"\nPlate (OCR, approx): {entry['plate_text']}"
        if entry.get("note"):
            info += f"\nNote: {entry['note']}"
        ctk.CTkLabel(win, text=info, font=("Courier", 11), justify="left",
                     text_color=ACCENT).pack(padx=10, pady=(0, 10))

        if entry.get("source_path") and not self._is_stream_url(entry["source_path"]):
            ctk.CTkButton(win, text="🎬 Export ±5s Clip", height=32,
                         fg_color=PURPLE, hover_color="#7C3AED",
                         command=lambda e=entry: self._export_clip(e)
                         ).pack(padx=10, pady=(0, 10), fill="x")

    def _toggle_star(self, entry, card):
        entry["starred"] = not entry.get("starred", False)
        card._star_btn.configure(
            text="★" if entry["starred"] else "☆",
            fg_color=GOLD if entry["starred"] else PANEL_BG,
            text_color=BG_DARK if entry["starred"] else "white")

    def _edit_note(self, entry):
        note = simpledialog.askstring(
            "Evidence Note", "Add/edit note for this evidence:",
            initialvalue=entry.get("note", ""), parent=self)
        if note is not None:
            entry["note"] = note.strip()

    def _delete_evidence(self, entry, card):
        if not messagebox.askyesno(
                "Delete Evidence",
                f"Remove ID {entry.get('track_id')} ({entry.get('type')}) "
                "from this case's evidence list?\n"
                "(The saved photo file will also be deleted.)"):
            return
        try:
            fp = entry.get("filepath")
            if fp and os.path.exists(fp):
                os.remove(fp)
        except OSError as exc:
            log.warning("Could not delete evidence file: %s", exc)
        if entry in self.evidence_database:
            self.evidence_database.remove(entry)
        if entry.get("type") == "Person":
            self.stats["persons"] = max(0, self.stats.get("persons", 0) - 1)
        elif entry.get("type") in self.VEHICLES:
            self.stats["vehicles"] = max(0, self.stats.get("vehicles", 0) - 1)
        card.destroy()
        if card in self.gallery_widgets:
            self.gallery_widgets.remove(card)
        self.evidence_count.configure(
            text=f"📸 Total Evidence: {len(self.evidence_database)}")
        self.person_count.configure(text=f"👤 P: {self.stats.get('persons', 0)}")
        self.vehicle_count.configure(text=f"🚗 V: {self.stats.get('vehicles', 0)}")

    def _filter_gallery(self, event=None):
        q = self.search_entry.get().strip().lower()
        for card in self.gallery_widgets:
            entry = getattr(card, "_entry", {})
            haystack = " ".join(str(v) for v in entry.values()).lower()
            if not q or q in haystack:
                card.pack(pady=5, padx=5, fill="x")
            else:
                card.pack_forget()

    def _export_clip(self, entry):
        src = entry.get("source_path")
        if not src or not os.path.exists(src):
            messagebox.showwarning(
                "Unavailable",
                "Original video file not found (moved or deleted?).")
            return
        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp4", filetypes=[("MP4 Video", "*.mp4")],
            initialfile=f"clip_ID{entry['track_id']}_{entry['timestamp']}.mp4")
        if not save_path:
            return
        try:
            cap = cv2.VideoCapture(src)
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            center_frame = entry.get("frame_idx", 0)
            start_f = max(0, center_frame - int(fps * 5))
            end_f = center_frame + int(fps * 5)
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(save_path, fourcc, fps, (w, h))
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
            f = start_f
            while f <= end_f:
                ret, frame = cap.read()
                if not ret:
                    break
                out.write(frame)
                f += 1
            cap.release()
            out.release()
            messagebox.showinfo("Clip Saved", f"Clip saved:\n{save_path}")
        except Exception as exc:
            messagebox.showerror("Clip Failed", f"Could not create clip:\n{exc}")

    def show_help(self):
        win = ctk.CTkToplevel(self)
        win.title("❓ Help / About")
        win.geometry("560x600")
        win.configure(fg_color=BG_DARK)

        ctk.CTkLabel(win, text=f"🦚 {APP_NAME}", font=("Arial Black", 20),
                     text_color=HIGHLIGHT).pack(pady=(15, 0))
        ctk.CTkLabel(win, text=APP_VERSION, font=("Courier", 10),
                     text_color="gray").pack(pady=(0, 10))

        box = ctk.CTkTextbox(win, font=("Arial", 11), fg_color=PANEL_BG)
        box.pack(expand=True, fill="both", padx=15, pady=(0, 10))
        box.insert("1.0", (
            "QUICK WORKFLOW\n"
            "1. Load Batch Videos (or Add Live Camera) → choose filters →\n"
            "   press START.\n"
            "2. Evidence photos appear live in the gallery on the right;\n"
            "   click a photo to zoom, use ⭐/📝/🗑/🎬 on each card.\n"
            "3. When the scan ends, the report uploads to the web panel\n"
            "   automatically and a WhatsApp message with the report link\n"
            "   is sent to you. No report is ever left on this PC.\n\n"
            "SIDEBAR TOOLS\n"
            "- SYNC PENDING REPORTS: retry any report that failed to\n"
            "  upload earlier (no internet at the time).\n"
            "- Advanced AI & Security: face recognition, plate OCR, face\n"
            "  blur, watermark, encryption, loiter/crowd thresholds, AI\n"
            "  model size, GPU choice, auto-lock — switches that need an\n"
            "  extra package show as disabled with a hint underneath.\n\n"
            "EVIDENCE PANEL TOOLS\n"
            "➕ Manual: add a photo evidence not captured by AI.\n"
            "📦 ZIP: export all photos of the current case.\n"
            "📊 Stats: quick chart for the current case.\n"
            "📁 Recent: reopen a past case's photos for review.\n"
            "🆚 Compare: heuristic match between two saved cases.\n"
            "🖨 Print: prints the current report directly (not saved).\n\n"
            "FOR MORE DETAIL\n"
            "Open the web panel's own Help page for the full guide,\n"
            "including how registration, validity and reports work."))
        box.configure(state="disabled")

        server = self.auth.server_url
        if server:
            ctk.CTkButton(
                win, text="🌐 Open Full Guide on the Website", height=38,
                fg_color=ACCENT, hover_color="#0891B2",
                command=lambda: webbrowser.open(f"{server}/help.php")
            ).pack(padx=15, pady=(0, 15), fill="x")

    def show_analytics(self):
        win = ctk.CTkToplevel(self)
        win.title("📊 Analytics Dashboard")
        win.geometry("520x420")
        win.configure(fg_color=BG_DARK)
        counts = defaultdict(int)
        for e in self.evidence_database:
            counts[e["type"]] += 1
        canvas = tk.Canvas(win, width=480, height=260, bg=BG_DARK,
                           highlightthickness=0)
        canvas.pack(pady=15)
        if not counts:
            canvas.create_text(240, 130, text="No evidence yet in this case.",
                               fill="gray", font=("Arial", 13))
        else:
            max_v = max(counts.values())
            bar_w = 480 // max(1, len(counts))
            colors_cycle = [HIGHLIGHT, ACCENT, SUCCESS, PURPLE, GOLD, WARNING]
            for i, (k, v) in enumerate(sorted(counts.items())):
                bh = int((v / max_v) * 200)
                x0 = i * bar_w + 15
                canvas.create_rectangle(x0, 230 - bh, x0 + bar_w - 25, 230,
                                        fill=colors_cycle[i % len(colors_cycle)])
                canvas.create_text(x0 + (bar_w - 25) // 2, 245, text=k,
                                   fill="white", font=("Arial", 10))
                canvas.create_text(x0 + (bar_w - 25) // 2, 220 - bh, text=str(v),
                                   fill="white", font=("Arial", 11, "bold"))
        ctk.CTkLabel(win,
                    text=f"Total Evidence: {len(self.evidence_database)}  |  "
                         f"Max Crowd Seen: {self.stats.get('max_crowd', 0)}",
                    font=("Arial", 12, "bold"), text_color=GOLD).pack(pady=5)

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
                    pil_img, entry = msg[1], msg[2]
                    thumb = pil_img.copy()
                    thumb.thumbnail((220, 130))
                    img_ctk = ctk.CTkImage(thumb, size=thumb.size)

                    card = ctk.CTkFrame(self.gallery, fg_color=BG_DARK,
                                        corner_radius=8)
                    card.pack(pady=5, padx=5, fill="x")
                    card._entry = entry
                    ctk.CTkButton(card, image=img_ctk, text="",
                                  fg_color="transparent",
                                  command=lambda e=entry: self._view_evidence(e)
                                  ).pack(pady=5)
                    label_text = (f"ID:{entry['track_id']} | {entry['type']} | "
                                 f"{entry['color']}\n{entry['timestamp']}")
                    if entry.get("face_match"):
                        label_text += f"\n⚠ {entry['face_match']}"
                    if entry.get("encrypted"):
                        label_text += "  🔒"
                    ctk.CTkLabel(card, text=label_text,
                                font=("Courier", 10, "bold"),
                                text_color=HIGHLIGHT).pack(pady=(0, 3))

                    btn_row = ctk.CTkFrame(card, fg_color="transparent")
                    btn_row.pack(pady=(0, 5))
                    star_btn = ctk.CTkButton(
                        btn_row, text="★" if entry.get("starred") else "☆",
                        width=28, height=24,
                        fg_color=GOLD if entry.get("starred") else PANEL_BG,
                        command=lambda e=entry, c=card: self._toggle_star(e, c))
                    star_btn.pack(side="left", padx=2)
                    card._star_btn = star_btn
                    ctk.CTkButton(btn_row, text="📝", width=28, height=24,
                                 fg_color=PANEL_BG,
                                 command=lambda e=entry: self._edit_note(e)
                                 ).pack(side="left", padx=2)
                    if entry.get("source_path") and not self._is_stream_url(
                            entry["source_path"]):
                        ctk.CTkButton(btn_row, text="🎬", width=28, height=24,
                                     fg_color=PANEL_BG,
                                     command=lambda e=entry: self._export_clip(e)
                                     ).pack(side="left", padx=2)
                    ctk.CTkButton(btn_row, text="🗑", width=28, height=24,
                                 fg_color="#7F1D1D",
                                 command=lambda e=entry, c=card:
                                 self._delete_evidence(e, c)
                                 ).pack(side="left", padx=2)

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
                        self._save_resume_state()
                        self.process_next_video()

                elif kind == "upload_result":
                    ok, result, case_id = msg[1], msg[2], msg[3]
                    wa_sent = msg[4] if len(msg) > 4 else True
                    if ok:
                        self.lbl_status.configure(text="☁ Report Uploaded ✅",
                                                  text_color=SUCCESS)
                        wa_line = ("📲 WhatsApp message sent." if wa_sent else
                                  "⚠ WhatsApp message FAILED to send — the "
                                  "report is saved, use 📲 Send Again in "
                                  "the admin panel, or check server "
                                  "config.php's WhatsApp API keys.")
                        self.timeline_text.insert(
                            tk.END, f"☁ Report uploaded ({case_id}): "
                                    f"{result}\n{wa_line}\n")
                        self.timeline_text.see(tk.END)
                        messagebox.showinfo(
                            "Uploaded",
                            f"Report uploaded to the web panel!\n"
                            f"📋 Case: {case_id}\n" + wa_line)
                    else:
                        self.lbl_status.configure(
                            text="☁ Upload Failed", text_color=DANGER)
                        self.timeline_text.insert(
                            tk.END,
                            f"☁ Upload FAILED ({case_id}): {result}\n"
                            "The report stays saved on this PC and will "
                            "retry — or press 🔧 TEST SERVER & UPLOAD to "
                            "see exactly why.\n")
                        self.timeline_text.see(tk.END)

                elif kind == "model_ready":
                    self.hw_label.configure(
                        text=f"HARDWARE: {self.device.upper()}",
                        text_color=ACCENT if self.device.startswith("cuda")
                        else WARNING)
                    if not self.is_scanning:
                        self.lbl_status.configure(text="✅ System Ready",
                                                  text_color=SUCCESS)

                elif kind == "model_failed":
                    self.hw_label.configure(text="HARDWARE: MODEL FAILED",
                                            text_color=DANGER)

                elif kind == "gpu_info":
                    count = msg[1]
                    if count > 1:
                        values = [str(i) for i in range(count)]
                        self.gpu_combo.configure(values=values, state="normal")
                        self.gpu_combo.set(str(self.settings.get("gpu_index", 0)))
                    else:
                        self.gpu_combo.configure(values=["CPU/GPU0"],
                                                 state="disabled")
                        self.gpu_combo.set("CPU/GPU0")

                elif kind == "benchmark_done":
                    self.lbl_performance.configure(text=f"⚡ Benchmark: {msg[1]}")
                    self.timeline_text.insert(
                        tk.END, f"⚡ Hardware benchmark: {msg[1]}\n")
                    self.timeline_text.see(tk.END)

        except queue.Empty:
            pass
        finally:
            self.after(50, self.process_queue)


if __name__ == "__main__":
    app = KrishnaIntelligence()
    app.mainloop()
