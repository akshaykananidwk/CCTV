import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk
from PIL import Image, ImageTk, ImageEnhance, ImageFilter
import cv2
from ultralytics import YOLO
import os
import threading
import time
import numpy as np
import queue
import json
from datetime import datetime
import csv
from collections import defaultdict
import warnings
import torch  # Required for Hardware Acceleration

warnings.filterwarnings('ignore')

# Configure CustomTkinter for lightweight performance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Premium Color Palette - Professional & Sleek
BG_DARK = "#0A0E1A"
PANEL_BG = "#111827"
HIGHLIGHT = "#F97316"
ACCENT = "#06B6D4"
DANGER = "#EF4444"
SUCCESS = "#10B981"
WARNING = "#F59E0B"
GOLD = "#FCD34D"
PURPLE = "#8B5CF6"

class SplashScreen(ctk.CTkToplevel):
    """Animated Splash Screen with LCB Branding"""
    def __init__(self, parent):
        super().__init__(parent)

        self.parent = parent
        self.title("")
        self.geometry("600x400")
        self.configure(fg_color=BG_DARK)
        self.overrideredirect(True)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - 300
        y = (self.winfo_screenheight() // 2) - 200
        self.geometry(f"+{x}+{y}")

        self.setup_ui()
        self.animate()

        # Auto close after 3.5 seconds
        self.after(3500, self.close_splash)

    def setup_ui(self):
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(expand=True, fill="both", padx=20, pady=20)

        self.canvas = tk.Canvas(main_frame, width=400, height=180, bg=BG_DARK, highlightthickness=0)
        self.canvas.pack(pady=10)

        self.logo_text = self.canvas.create_text(200, 90, text="🔍", font=("Arial", 65), fill=HIGHLIGHT, anchor="center")

        self.lbl_title = ctk.CTkLabel(main_frame, text="i-Footege Intelligence", font=("Arial Black", 26, "bold"), text_color=HIGHLIGHT)
        self.lbl_title.pack(pady=5)

        self.lbl_subtitle = ctk.CTkLabel(main_frame, text="LCB Technical Cell", font=("Courier", 13, "bold"), text_color=ACCENT)
        self.lbl_subtitle.pack()

        self.lbl_dept = ctk.CTkLabel(main_frame, text="DEVBHOOMI DWARKA", font=("Courier", 11, "bold"), text_color=GOLD)
        self.lbl_dept.pack(pady=5)

        self.progress = ctk.CTkProgressBar(main_frame, width=400, height=8, progress_color=ACCENT)
        self.progress.set(0)
        self.progress.pack(pady=15)

        self.lbl_loading = ctk.CTkLabel(main_frame, text="Initializing Forensic Engine...", font=("Arial", 11), text_color="gray")
        self.lbl_loading.pack()

        ctk.CTkLabel(main_frame, text="v11.0 Pro Enterprise", font=("Courier", 9), text_color="gray").pack(pady=5)

    def animate(self):
        self.progress.set(0)
        texts = ["Initializing AI Models...", "Loading Neural Trackers...", "Calibrating Visual Engine...", "Ready for Analysis!"]

        def update_progress(i=0):
            if i <= 100:
                self.progress.set(i/100)
                if i % 25 == 0 and i // 25 < len(texts):
                    self.lbl_loading.configure(text=texts[i//25])

                self.canvas.delete("arc")
                self.canvas.create_text(200, 90, text="🔍" if i % 20 < 10 else "⚡", font=("Arial", 65), fill=HIGHLIGHT, anchor="center", tags="arc")
                self.after(35, update_progress, i + 1)

        update_progress(0)

    def close_splash(self):
        self.destroy()
        self.parent.deiconify()
        self.parent.show_ready()

class ForensicVideoIntelligence(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.withdraw()

        self.title("🔍 i-Footege Intelligence | LCB DEVBHOOMI DWARKA")
        self.geometry("1400x800")
        self.state('zoomed')
        self.configure(fg_color=BG_DARK)

        self.splash = SplashScreen(self)

        # Engine Variables
        self.video_list = []
        self.current_video_idx = 0
        self.base_dir = "LCB_Forensic_Data"
        self.current_case_dir = ""
        self.is_scanning = False
        self.is_stopped = False
        self.tracked_ids = set()

        self.gui_queue = queue.Queue()
        self.gallery_widgets = []
        self.max_gallery_items = 40
        self.evidence_database = []

        # AI Config
        self.conf_threshold = 0.35
        self.frame_skip = 10
        self.enable_enhance = True
        self.target_color = "All"
        self.target_object = "All"
        self.night_mode = False

        # Hardware setup
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"🚀 Loading AI Models on {self.device.upper()}...")

        try:
            self.model = YOLO("yolov8s.pt")  # Fast & Accurate
            self.model.to(self.device)
        except:
            self.model = None

        self.categories = {
            0: "Person", 2: "Car", 3: "Motorcycle", 5: "Bus", 7: "Truck",
            15: "Cat", 16: "Dog", 19: "Cow"
        }

        self.stats = defaultdict(int)

        self.setup_directories()
        self.after(0, self.initialize_ui)

    def initialize_ui(self):
        self.setup_ui()
        self.process_queue()

    def show_ready(self):
        self.lbl_status.configure(text="✅ System Ready", text_color=SUCCESS)
        self.after(3000, lambda: self.lbl_status.configure(text="System Standby", text_color="gray"))

    def setup_directories(self):
        for d in [self.base_dir, f"{self.base_dir}/Cases"]:
            os.makedirs(d, exist_ok=True)

    def setup_ui(self):
        self.grid_columnconfigure(1, weight=5)
        self.grid_columnconfigure(2, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ========== LEFT SIDEBAR (SCROLLABLE TO PREVENT CUTTING) ==========
        self.sidebar = ctk.CTkScrollableFrame(self, width=320, corner_radius=0, fg_color=PANEL_BG)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        header = ctk.CTkFrame(self.sidebar, fg_color=HIGHLIGHT, corner_radius=8)
        header.pack(fill="x", pady=(10, 20), padx=10)
        ctk.CTkLabel(header, text="🔍 i-Footege", font=("Arial Black", 24), text_color=BG_DARK).pack(pady=(15, 0))
        ctk.CTkLabel(header, text="LCB TECHNICAL CELL", font=("Courier", 10, "bold"), text_color=BG_DARK).pack(pady=(0, 15))

        # Batch Control
        actions = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        actions.pack(pady=5, padx=10, fill="x")
        self.btn_import = ctk.CTkButton(actions, text="📂 LOAD BATCH VIDEOS", font=("Arial", 12, "bold"), fg_color="#2563EB", hover_color="#1D4ED8", height=45, command=self.import_videos)
        self.btn_import.pack(fill="x", pady=5)

        ctrl_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        ctrl_frame.pack(pady=5, padx=10, fill="x")
        self.btn_start = ctk.CTkButton(ctrl_frame, text="▶ START", font=("Arial", 12, "bold"), fg_color=SUCCESS, hover_color="#059669", height=40, command=self.start_analysis)
        self.btn_start.pack(side="left", expand=True, padx=(0,5), fill="x")
        self.btn_stop = ctk.CTkButton(ctrl_frame, text="⏹ ABORT", font=("Arial", 12, "bold"), fg_color=DANGER, hover_color="#DC2626", height=40, command=self.stop_analysis, state="disabled")
        self.btn_stop.pack(side="right", expand=True, padx=(5,0), fill="x")

        # Case Info
        case_frame = ctk.CTkFrame(self.sidebar, fg_color=BG_DARK, corner_radius=8)
        case_frame.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(case_frame, text="📋 CASE DETAILS", font=("Arial", 11, "bold"), text_color=ACCENT).pack(pady=(10, 5))
        self.case_entry = ctk.CTkEntry(case_frame, placeholder_text="FIR / Case ID...", height=35)
        self.case_entry.pack(padx=10, pady=(5, 10), fill="x")

        # Smart Filters
        filter_frame = ctk.CTkFrame(self.sidebar, fg_color=BG_DARK, corner_radius=8)
        filter_frame.pack(padx=10, pady=5, fill="x")
        ctk.CTkLabel(filter_frame, text="🎯 SMART FILTERS", font=("Arial", 11, "bold"), text_color=ACCENT).pack(pady=(10, 5))
        self.color_filter = ctk.CTkComboBox(filter_frame, values=["All Colors", "Red", "Blue", "Green", "White", "Black", "Silver", "Yellow"], height=32)
        self.color_filter.pack(padx=10, pady=5, fill="x")
        self.object_filter = ctk.CTkComboBox(filter_frame, values=["All Objects", "Person", "Vehicle", "Animal"], height=32)
        self.object_filter.pack(padx=10, pady=(5, 10), fill="x")

        # Settings
        settings_frame = ctk.CTkFrame(self.sidebar, fg_color=BG_DARK, corner_radius=8)
        settings_frame.pack(padx=10, pady=10, fill="x")
        ctk.CTkLabel(settings_frame, text="⚡ ENGINE SETTINGS", font=("Arial", 11, "bold"), text_color=ACCENT).pack(pady=(10, 5))

        self.speed_slider = ctk.CTkSlider(settings_frame, from_=1, to=30, number_of_steps=29, command=self.update_speed, progress_color=ACCENT)
        self.speed_slider.set(self.frame_skip)
        self.speed_slider.pack(padx=15, pady=5, fill="x")
        self.speed_label = ctk.CTkLabel(settings_frame, text=f"Speed: Every {self.frame_skip} frames", font=("Courier", 10))
        self.speed_label.pack(pady=(0, 5))

        self.enhance_switch = ctk.CTkSwitch(settings_frame, text="🔬 Image Enhancement", font=("Arial", 11), progress_color=HIGHLIGHT)
        self.enhance_switch.pack(pady=5, padx=15, anchor="w")
        self.enhance_switch.select()

        self.night_switch = ctk.CTkSwitch(settings_frame, text="🌙 Night Vision Mode", font=("Arial", 11), progress_color=PURPLE)
        self.night_switch.pack(pady=(5, 10), padx=15, anchor="w")

        # Export
        ctk.CTkButton(self.sidebar, text="📊 EXPORT PDF/CSV", font=("Arial", 11, "bold"), fg_color=PURPLE, hover_color="#7C3AED", height=40, command=self.export_report).pack(pady=5, padx=10, fill="x")
        ctk.CTkButton(self.sidebar, text="📁 OPEN DATABASE", font=("Arial", 11, "bold"), fg_color="#34495E", hover_color=ACCENT, height=40, command=self.open_folder).pack(pady=(5, 15), padx=10, fill="x")

        self.lbl_status = ctk.CTkLabel(self.sidebar, text="System Standby", font=("Courier", 10), text_color="gray")
        self.lbl_status.pack(side="bottom", pady=10)

        # ========== MAIN VIDEO DISPLAY ==========
        self.center_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.center_frame.grid(row=0, column=1, padx=15, pady=15, sticky="nsew")

        self.video_frame = ctk.CTkFrame(self.center_frame, fg_color="black", border_width=2, border_color=PANEL_BG, corner_radius=10)
        self.video_frame.pack(expand=True, fill="both")

        self.video_label = ctk.CTkLabel(self.video_frame, text="[ NO SIGNAL ]\nLoad videos to start", font=("Courier", 22, "bold"), text_color="#555555")
        self.video_label.pack(expand=True, fill="both")

        status_frame = ctk.CTkFrame(self.center_frame, fg_color="transparent", height=30)
        status_frame.pack(fill="x", pady=(10, 0))
        self.batch_label = ctk.CTkLabel(status_frame, text="Queue: 0 Videos", font=("Arial", 12, "bold"), text_color=ACCENT)
        self.batch_label.pack(side="left")
        self.lbl_performance = ctk.CTkLabel(status_frame, text="Ready", font=("Courier", 11), text_color=GOLD)
        self.lbl_performance.pack(side="right")

        self.progress = ctk.CTkProgressBar(self.center_frame, progress_color=ACCENT, height=8)
        self.progress.pack(fill="x", pady=(5, 0))
        self.progress.set(0)

        # ========== EVIDENCE PANEL (SCROLLABLE) ==========
        self.evidence_panel = ctk.CTkFrame(self, fg_color=PANEL_BG, corner_radius=10)
        self.evidence_panel.grid(row=0, column=2, padx=15, pady=15, sticky="nsew")

        stats_frame = ctk.CTkFrame(self.evidence_panel, fg_color=BG_DARK, corner_radius=8)
        stats_frame.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(stats_frame, text=f"HARDWARE: {self.device.upper()}", font=("Courier", 11, "bold"), text_color=ACCENT if self.device == 'cuda' else WARNING).pack(pady=(10, 5))

        stat_grid = ctk.CTkFrame(stats_frame, fg_color="transparent")
        stat_grid.pack(pady=5)
        self.person_count = ctk.CTkLabel(stat_grid, text="👤 P: 0", font=("Arial", 15, "bold"))
        self.person_count.grid(row=0, column=0, padx=15, pady=3)
        self.vehicle_count = ctk.CTkLabel(stat_grid, text="🚗 V: 0", font=("Arial", 15, "bold"))
        self.vehicle_count.grid(row=0, column=1, padx=15, pady=3)
        self.evidence_count = ctk.CTkLabel(stats_frame, text="📸 Total Evidence: 0", font=("Arial", 13, "bold"), text_color=GOLD)
        self.evidence_count.pack(pady=(5, 10))

        ctk.CTkLabel(self.evidence_panel, text="🔍 LIVE EVIDENCE GALLERY", font=("Arial", 12, "bold"), text_color=HIGHLIGHT).pack(pady=(5, 0))

        self.gallery = ctk.CTkScrollableFrame(self.evidence_panel, fg_color="transparent")
        self.gallery.pack(expand=True, fill="both", padx=5, pady=5)

        ctk.CTkLabel(self.evidence_panel, text="📅 TIMELINE LOG", font=("Arial", 11, "bold"), text_color=ACCENT).pack(anchor="w", padx=10, pady=(5, 0))
        self.timeline_text = ctk.CTkTextbox(self.evidence_panel, height=100, fg_color=BG_DARK, font=("Courier", 10))
        self.timeline_text.pack(fill="x", padx=10, pady=(0, 10))

    def update_speed(self, val):
        self.frame_skip = int(val)
        self.speed_label.configure(text=f"Speed: Every {self.frame_skip} frames")

    def import_videos(self):
        files = filedialog.askopenfilenames(title="Select Videos", filetypes=[("Video Files", "*.mp4 *.avi *.mkv *.mov *.wmv")])
        if files:
            self.video_list = list(files)
            self.batch_label.configure(text=f"Queue: {len(files)} Videos Loaded")
            self.video_label.configure(text=f"✅ {len(files)} FILES LOADED\nReady for Analysis", text_color=SUCCESS)
            self.lbl_status.configure(text="Ready to Scan", text_color=SUCCESS)

    def start_analysis(self):
        if not self.video_list:
            messagebox.showwarning("Warning", "Please load videos first!")
            return
        if self.is_scanning: return

        case_id = self.case_entry.get().strip() or f"CASE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.current_case_dir = os.path.join(self.base_dir, "Cases", case_id)
        os.makedirs(self.current_case_dir, exist_ok=True)

        self.is_scanning = True
        self.is_stopped = False
        self.current_video_idx = 0
        self.tracked_ids.clear()
        self.stats.clear()
        self.evidence_database.clear()
        self.timeline_text.delete("1.0", tk.END)
        for w in self.gallery.winfo_children(): w.destroy()
        self.gallery_widgets.clear()

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_import.configure(state="disabled")
        self.lbl_status.configure(text="Processing Core Engine...", text_color=ACCENT)

        self.process_next_video()

    def stop_analysis(self):
        self.is_stopped = True
        self.lbl_status.configure(text="Aborting...", text_color=WARNING)

    def process_next_video(self):
        if self.current_video_idx < len(self.video_list) and not self.is_stopped:
            video_path = self.video_list[self.current_video_idx]
            video_name = os.path.basename(video_path)
            self.batch_label.configure(text=f"🔍 Scanning {self.current_video_idx+1}/{len(self.video_list)}: {video_name[:25]}...")
            threading.Thread(target=self.core_engine, args=(video_path,), daemon=True).start()
        else:
            self.finish_analysis()

    def core_engine(self, video_path):
        if self.model is None:
            self.gui_queue.put(("error", "AI Model completely failed to load!"))
            return

        vid_name = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(self.current_case_dir, vid_name)
        os.makedirs(output_dir, exist_ok=True)

        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_idx = 0

        start_time = time.time()

        while cap.isOpened() and not self.is_stopped:
            ret, frame = cap.read()
            if not ret: break

            if frame_idx % self.frame_skip == 0:
                # YOLOv8 Tracking Engine
                results = self.model.track(frame, conf=self.conf_threshold, persist=True, verbose=False)
                annotated_frame = results[0].plot()

                if results[0].boxes.id is not None:
                    ids = results[0].boxes.id.int().cpu().tolist()
                    clss = results[0].boxes.cls.int().cpu().tolist()
                    boxes = results[0].boxes.xyxy.cpu().numpy()

                    for box, tid, cls in zip(boxes, ids, clss):
                        if cls in self.categories and tid not in self.tracked_ids:
                            cat_name = self.categories[cls]

                            # Object Filter
                            target_obj = self.object_filter.get()
                            if target_obj != "All Objects":
                                if target_obj == "Person" and cat_name != "Person": continue
                                elif target_obj == "Vehicle" and cat_name not in ["Car", "Motorcycle", "Bus", "Truck"]: continue
                                elif target_obj == "Animal" and cat_name not in ["Cat", "Dog", "Cow"]: continue

                            x1, y1, x2, y2 = map(int, box[:4])
                            crop = frame[max(0,y1):y2, max(0,x1):x2]

                            if crop.size > 0:
                                color = self.detect_color(crop)

                                # Color Filter
                                target_color = self.color_filter.get()
                                if target_color != "All Colors" and color != target_color: continue

                                # Mark ID tracked
                                self.tracked_ids.add(tid)

                                # Enhancement & Night Mode
                                if self.night_switch.get(): crop = self.enhance_night(crop)
                                elif self.enhance_switch.get(): crop = self.enhance_basic(crop)

                                timestamp_str = f"{int(frame_idx/fps)//60:02d}m_{int(frame_idx/fps)%60:02d}s"

                                # HARDCODED .jpg extension
                                filename = f"ID_{tid}_{color}_{cat_name}_{timestamp_str}.jpg"
                                filepath = os.path.join(output_dir, filename)
                                cv2.imwrite(filepath, crop)

                                # Stats Update
                                if cat_name == "Person": self.stats["persons"] += 1
                                elif cat_name in ["Car", "Motorcycle", "Bus", "Truck"]: self.stats["vehicles"] += 1

                                self.evidence_database.append({
                                    "filename": filename, "type": cat_name, "track_id": tid, "color": color,
                                    "timestamp": timestamp_str, "video": vid_name
                                })

                                # UI Updates
                                self.gui_queue.put(("timeline", f"[{timestamp_str}] {cat_name} (ID:{tid}) | Color: {color}\n"))
                                self.gui_queue.put(("evidence", crop, cat_name, color, timestamp_str, tid, filepath))
                                self.gui_queue.put(("stats_update", None))

                # Main Screen Resizing (Responsive without cutting)
                rgb = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
                img_pil = Image.fromarray(cv2.resize(rgb, (854, 480)))
                img_ctk = ctk.CTkImage(light_image=img_pil, dark_image=img_pil, size=(850, 478))

                elapsed = time.time() - start_time
                fps_processing = frame_idx / elapsed if elapsed > 0 else 0

                self.gui_queue.put(("frame", img_ctk))
                self.gui_queue.put(("progress", frame_idx / total_frames if total_frames > 0 else 0))
                self.gui_queue.put(("performance", f"⚡ Speed: {fps_processing:.1f} FPS"))

            frame_idx += 1

        cap.release()
        self.gui_queue.put(("video_done", None))

    def detect_color(self, crop):
        try:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            colors = {
                "Red": [([0, 100, 100], [10, 255, 255]), ([160, 100, 100], [180, 255, 255])],
                "Blue": [([90, 50, 50], [130, 255, 255])],
                "Green": [([35, 50, 50], [85, 255, 255])],
                "Yellow": [([15, 100, 100], [35, 255, 255])],
                "White": [([0, 0, 200], [180, 30, 255])],
                "Black": [([0, 0, 0], [180, 255, 50])],
                "Silver": [([0, 0, 50], [180, 40, 200])]
            }
            best, max_pct = "Unknown", 0
            for name, ranges in colors.items():
                mask = np.zeros(hsv.shape[:2], dtype="uint8")
                for (l, u) in ranges: mask = cv2.bitwise_or(mask, cv2.inRange(hsv, np.array(l), np.array(u)))
                pct = (cv2.countNonZero(mask) / (hsv.shape[0] * hsv.shape[1])) * 100
                if pct > max_pct and pct > 10: max_pct, best = pct, name
            return best
        except: return "Unknown"

    def enhance_basic(self, image):
        try:
            denoised = cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)
            kernel = np.array([[-1,-1,-1], [-1, 9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(denoised, -1, kernel)
            h, w = sharpened.shape[:2]
            return cv2.resize(sharpened, (w*2, h*2), interpolation=cv2.INTER_CUBIC)
        except: return image

    def enhance_night(self, image):
        try:
            enhanced = cv2.convertScaleAbs(image, alpha=1.5, beta=40)
            enhanced = cv2.fastNlMeansDenoisingColored(enhanced, None, 10, 10, 7, 21)
            return enhanced
        except: return image

    def finish_analysis(self):
        self.is_scanning = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_import.configure(state="normal")
        self.progress.set(1.0)
        self.lbl_status.configure(text="Analysis Complete", text_color=SUCCESS)
        self.batch_label.configure(text="✅ All Batches Compiled!")

        report_path = os.path.join(self.current_case_dir, "report.json")
        with open(report_path, 'w') as f: json.dump(self.evidence_database, f, indent=2)

        messagebox.showinfo("Compiled", f"Case Analysis Successful!\n📸 Images saved as .jpg\n📁 Saved in: {self.current_case_dir}")

    def export_report(self):
        if not self.evidence_database:
            messagebox.showwarning("No Data", "No evidence to export!")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV File", "*.csv")])
        if path:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=self.evidence_database[0].keys())
                writer.writeheader()
                writer.writerows(self.evidence_database)
            messagebox.showinfo("Exported", "Database Exported Successfully!")

    def open_folder(self):
        if os.path.exists(self.base_dir): os.startfile(self.base_dir)

    def clear_gallery(self):
        for w in self.gallery.winfo_children(): w.destroy()
        self.gallery_widgets.clear()

    def process_queue(self):
        try:
            while True:
                msg = self.gui_queue.get_nowait()

                if msg[0] == "frame":
                    self.video_label.configure(image=msg[1], text="")

                elif msg[0] == "evidence":
                    crop, cat, color, ts, tid, path = msg[1], msg[2], msg[3], msg[4], msg[5], msg[6]
                    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(crop_rgb)
                    img.thumbnail((220, 130))
                    img_ctk = ctk.CTkImage(img, size=(210, 120))

                    card = ctk.CTkFrame(self.gallery, fg_color=BG_DARK, corner_radius=8)
                    card.pack(pady=5, padx=5, fill="x")
                    ctk.CTkButton(card, image=img_ctk, text="", fg_color="transparent", command=lambda p=path: os.startfile(p)).pack(pady=5)
                    ctk.CTkLabel(card, text=f"ID:{tid} | {cat} | {color}\n{ts}", font=("Courier", 10, "bold"), text_color=HIGHLIGHT).pack(pady=(0,5))

                    self.gallery_widgets.append(card)
                    if len(self.gallery_widgets) > self.max_gallery_items: self.gallery_widgets.pop(0).destroy()

                elif msg[0] == "stats_update":
                    self.person_count.configure(text=f"👤 P: {self.stats.get('persons', 0)}")
                    self.vehicle_count.configure(text=f"🚗 V: {self.stats.get('vehicles', 0)}")
                    self.evidence_count.configure(text=f"📸 Total Evidence: {len(self.evidence_database)}")

                elif msg[0] == "progress": self.progress.set(msg[1])
                elif msg[0] == "performance": self.lbl_performance.configure(text=msg[1])
                elif msg[0] == "timeline":
                    self.timeline_text.insert(tk.END, msg[1])
                    self.timeline_text.see(tk.END)
                elif msg[0] == "video_done":
                    self.current_video_idx += 1
                    self.process_next_video()
                elif msg[0] == "error":
                    messagebox.showerror("System Error", msg[1])
                    self.finish_analysis()

        except queue.Empty: pass
        finally: self.after(50, self.process_queue)

if __name__ == "__main__":
    app = ForensicVideoIntelligence()
    app.mainloop()
