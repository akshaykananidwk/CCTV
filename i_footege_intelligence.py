"""
i-Footege Intelligence — Forensic CCTV Video Analysis Suite
LCB Technical Cell, Devbhoomi Dwarka
Version 12.0 Pro Enterprise

Features:
  - Batch CCTV video analysis with YOLOv8 detection + tracking (GPU/CPU auto)
  - Smart filters: object type (Person / Vehicle / Animal) and dominant color
  - Unique-ID evidence capture (one photo per tracked object, per video)
  - Image enhancement (fast CLAHE + sharpening) and Night Vision mode
  - Live evidence gallery, timeline log, and live statistics
  - Case management: per-case folders, JSON case report
  - Export: CSV database + PDF photo report (reportlab)
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
import threading
import time
import numpy as np
import queue
import json
import csv
import logging
import traceback
from datetime import datetime
from collections import defaultdict
import warnings

warnings.filterwarnings('ignore')

APP_NAME = "i-Footege Intelligence"
APP_VERSION = "v12.0 Pro Enterprise"
ORG_LINE_1 = "LCB Technical Cell"
ORG_LINE_2 = "DEVBHOOMI DWARKA"

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
        logging.FileHandler("i_footege.log", encoding="utf-8"),
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

        # Keep the splash up at least 3 seconds, then wait for the model.
        self.after(3000, self._mark_min_time)
        self.after(300, self._poll_ready)

    def setup_ui(self):
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=20, pady=20)

        self.canvas = tk.Canvas(main_frame, width=400, height=150,
                                bg=BG_DARK, highlightthickness=0)
        self.canvas.pack(pady=10)
        self.canvas.create_text(200, 75, text="🔍", font=("Arial", 60),
                                fill=HIGHLIGHT, anchor="center", tags="logo")

        ctk.CTkLabel(main_frame, text=APP_NAME,
                     font=("Arial Black", 26, "bold"),
                     text_color=HIGHLIGHT).pack(pady=5)
        ctk.CTkLabel(main_frame, text=ORG_LINE_1,
                     font=("Courier", 13, "bold"), text_color=ACCENT).pack()
        ctk.CTkLabel(main_frame, text=ORG_LINE_2,
                     font=("Courier", 11, "bold"), text_color=GOLD).pack(pady=5)

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
                                    text="🔍" if i % 20 < 10 else "⚡",
                                    font=("Arial", 60), fill=HIGHLIGHT,
                                    anchor="center", tags="logo")
            self.after(60, tick, i + 1)

        tick(0)

    def _mark_min_time(self):
        self._min_time_done = True

    def _poll_ready(self):
        """Close once the model finished loading (or failed) and 3s passed."""
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
class ForensicVideoIntelligence(ctk.CTk):
    # COCO class-id -> display name
    CATEGORIES = {0: "Person", 2: "Car", 3: "Motorcycle", 5: "Bus",
                  7: "Truck", 15: "Cat", 16: "Dog", 19: "Cow"}
    VEHICLES = ("Car", "Motorcycle", "Bus", "Truck")
    ANIMALS = ("Cat", "Dog", "Cow")

    def __init__(self):
        super().__init__()
        self.withdraw()

        self.title(f"🔍 {APP_NAME} | {ORG_LINE_1.upper()} {ORG_LINE_2}")
        self.geometry("1400x800")
        self._maximize_window()
        self.configure(fg_color=BG_DARK)

        # ---------------- engine state ----------------
        self.video_list = []
        self.current_video_idx = 0
        self.base_dir = "LCB_Forensic_Data"
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

        self.setup_directories()
        self.setup_ui()

        self.splash = SplashScreen(self)
        threading.Thread(target=self._load_model, daemon=True).start()
        self.process_queue()

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
            self.lbl_status.configure(text="✅ System Ready", text_color=SUCCESS)
            self.after(3000, lambda: self.lbl_status.configure(
                text="System Standby", text_color="gray"))
        elif self.model_status == "failed":
            self.lbl_status.configure(text="❌ AI Model Failed", text_color=DANGER)
            messagebox.showerror(
                "AI Model Error",
                "The YOLOv8 model could not be loaded.\n\n"
                f"Reason: {self.model_error}\n\n"
                "First run needs internet access to download 'yolov8s.pt'.\n"
                "Check i_footege.log for details, then restart the app.")

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
        header.pack(fill="x", pady=(10, 20), padx=10)
        ctk.CTkLabel(header, text="🔍 i-Footege", font=("Arial Black", 24),
                     text_color=BG_DARK).pack(pady=(15, 0))
        ctk.CTkLabel(header, text=ORG_LINE_1.upper(),
                     font=("Courier", 10, "bold"),
                     text_color=BG_DARK).pack(pady=(0, 15))

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

        # ---- export ----
        exp = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        exp.pack(pady=5, padx=10, fill="x")
        ctk.CTkButton(exp, text="📊 EXPORT CSV", font=("Arial", 11, "bold"),
                      fg_color=PURPLE, hover_color="#7C3AED", height=40,
                      command=self.export_csv).pack(side="left", expand=True,
                                                    padx=(0, 5), fill="x")
        ctk.CTkButton(exp, text="📄 EXPORT PDF", font=("Arial", 11, "bold"),
                      fg_color="#DB2777", hover_color="#BE185D", height=40,
                      command=self.export_pdf).pack(side="right", expand=True,
                                                    padx=(5, 0), fill="x")
        ctk.CTkButton(self.sidebar, text="📁 OPEN DATABASE",
                      font=("Arial", 11, "bold"), fg_color="#34495E",
                      hover_color=ACCENT, height=40,
                      command=self.open_folder).pack(pady=(5, 15), padx=10, fill="x")

        self.lbl_status = ctk.CTkLabel(self.sidebar, text="Loading AI Model...",
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
        # Keep the case id filesystem-safe.
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
            # Center region only — edges are mostly background.
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

        report = {
            "app": f"{APP_NAME} {APP_VERSION}",
            "case_id": self.current_case_id,
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
        try:
            with open(os.path.join(self.current_case_dir, "report.json"),
                      "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            log.error("Could not write report.json: %s", exc)

        if aborted:
            self.lbl_status.configure(text="⏹ Analysis Aborted",
                                      text_color=WARNING)
            self.batch_label.configure(text="⏹ Scan Aborted")
            messagebox.showwarning(
                "Aborted",
                f"Analysis was aborted.\n"
                f"📸 Evidence captured so far: {len(self.evidence_database)}\n"
                f"📁 Saved in: {self.current_case_dir}")
        else:
            self.lbl_status.configure(text="Analysis Complete",
                                      text_color=SUCCESS)
            self.batch_label.configure(text="✅ All Batches Compiled!")
            messagebox.showinfo(
                "Compiled",
                f"Case Analysis Successful!\n"
                f"📸 Evidence images: {len(self.evidence_database)}\n"
                f"📁 Saved in: {self.current_case_dir}")
        log.info("Scan finished | aborted=%s evidence=%d",
                 aborted, len(self.evidence_database))

    # ------------------------------------------------------------- exports -
    def export_csv(self):
        if not self.evidence_database:
            messagebox.showwarning("No Data", "No evidence to export!")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV File", "*.csv")],
            initialfile=f"{self.current_case_id or 'case'}_evidence.csv")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(
                    f, fieldnames=list(self.evidence_database[0].keys()))
                writer.writeheader()
                writer.writerows(self.evidence_database)
            messagebox.showinfo("Exported", "CSV Database Exported Successfully!")
        except OSError as exc:
            messagebox.showerror("Export Failed", f"Could not write CSV:\n{exc}")

    def export_pdf(self):
        if not self.evidence_database:
            messagebox.showwarning("No Data", "No evidence to export!")
            return
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm
            from reportlab.lib import colors as rl_colors
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                            Spacer, Table, TableStyle,
                                            Image as RLImage)
        except ImportError:
            messagebox.showerror(
                "Missing Package",
                "PDF export needs the 'reportlab' package.\n\n"
                "Install it with:  pip install reportlab")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF File", "*.pdf")],
            initialfile=f"{self.current_case_id or 'case'}_report.pdf")
        if not path:
            return

        try:
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle("TitleX", parent=styles["Title"],
                                         textColor=rl_colors.HexColor("#111827"))
            small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=9)

            doc = SimpleDocTemplate(path, pagesize=A4,
                                    topMargin=1.5 * cm, bottomMargin=1.5 * cm)
            story = [
                Paragraph(f"{APP_NAME} — Forensic Evidence Report", title_style),
                Paragraph(f"{ORG_LINE_1}, {ORG_LINE_2}", styles["Heading3"]),
                Spacer(1, 8),
                Paragraph(f"<b>Case ID:</b> {self.current_case_id or '-'}", small),
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
            messagebox.showinfo("Exported", "PDF Report Exported Successfully!")
            open_path(path)
        except Exception as exc:
            log.error("PDF export failed: %s\n%s", exc, traceback.format_exc())
            messagebox.showerror("Export Failed", f"Could not create PDF:\n{exc}")

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
    app = ForensicVideoIntelligence()
    app.mainloop()
