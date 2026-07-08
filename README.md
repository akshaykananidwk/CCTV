# 🔍 i-Footege Intelligence

**Forensic CCTV Video Analysis Suite — LCB Technical Cell, Devbhoomi Dwarka**
`v12.0 Pro Enterprise`

AI-powered desktop software that scans CCTV footage in batches, detects and tracks
persons / vehicles / animals with YOLOv8, captures one evidence photo per unique
object, and produces case-wise CSV + PDF reports.

---

## ✨ Features

- 📂 **Batch analysis** — load multiple CCTV videos and scan them one after another
- 🤖 **YOLOv8 detection + tracking** — GPU (CUDA) used automatically when available
- 🎯 **Smart filters** — search only Persons / Vehicles / Animals, and by dominant color
  (Red, Blue, Green, White, Black, Silver, Yellow)
- 📸 **Unique evidence capture** — one photo per tracked object per video (no duplicates)
- 🔬 **Image enhancement** — fast CLAHE contrast + sharpening + 2× upscale
- 🌙 **Night Vision mode** — brightness boost + contrast + denoise for dark footage
- ⏸ **Pause / Resume / Abort** controls during a scan
- 🖼 **Live evidence gallery** + 📅 timeline log + live statistics
- 🗂 **Case management** — every scan saved under `LCB_Forensic_Data/Cases/<CASE_ID>/`
  with a `report.json` case file
- 📊 **Export CSV** (Excel-compatible) and 📄 **Export PDF** photo report
- 🪵 Full activity log in `i_footege.log`

---

## 🖥 Installation (Windows) — સ્થાપના

1. **Python install કરો** (એક જ વાર): <https://www.python.org/downloads/> પરથી
   Python 3.10 કે નવું download કરો. Setup વખતે **"Add Python to PATH"** ✅ જરૂર ટીક કરો.
2. આ આખું folder તમારા PC પર copy કરો (દા.ત. `D:\i-Footege\`).
3. **`install_windows.bat`** પર double-click કરો — packages install થશે (5–15 મિનિટ, internet જોઈએ).
4. **`run_windows.bat`** પર double-click કરો — સોફ્ટવેર ચાલુ થશે.
   - પહેલી વાર ચલાવો ત્યારે AI model (~22 MB) download થાય છે, એટલે પહેલી વાર internet જોઈએ.
   - પછી internet વગર પણ ચાલશે.

### 📦 Standalone EXE બનાવવો હોય તો (બીજા PC પર Python વગર ચલાવવા)

`build_exe_windows.bat` double-click કરો. Build પૂરું થાય પછી
`dist\i-Footege\` આખું folder કોઈ પણ PC પર copy કરીને `i-Footege.exe` ચલાવો.

---

## 🚀 How to Use — વાપરવાની રીત

1. **📂 LOAD BATCH VIDEOS** — CCTV ના video files પસંદ કરો (mp4/avi/mkv/mov/wmv/dav)
2. **📋 CASE DETAILS** — FIR / Case ID લખો (ખાલી રાખો તો auto બનશે)
3. **🎯 SMART FILTERS** — જોઈએ તો object type અને color filter પસંદ કરો
4. **▶ START** — scan શરૂ; ⏸ PAUSE / ⏹ ABORT ગમે ત્યારે
5. જમણી બાજુ **evidence gallery** માં ફોટા આવતા જશે — ફોટા પર click કરો એટલે full size ખૂલશે
6. Scan પત્યા પછી **📊 EXPORT CSV** કે **📄 EXPORT PDF** થી report બનાવો
7. **📁 OPEN DATABASE** — બધા saved evidence folders ખોલે છે

### Output structure

```
LCB_Forensic_Data/
└── Cases/
    └── <CASE_ID>/
        ├── <video-1-name>/
        │   ├── ID_1_Red_Car_00m_05s_f150.jpg
        │   └── ...
        ├── <video-2-name>/...
        └── report.json
```

---

## ⚙️ Requirements

| Item | Minimum |
|---|---|
| OS | Windows 10/11 (Linux/macOS પણ ચાલે) |
| Python | 3.10+ |
| RAM | 8 GB (16 GB better) |
| GPU | Optional — NVIDIA GPU હોય તો આપોઆપ વપરાય છે |

> GPU speed માટે: NVIDIA card હોય તો CUDA-enabled PyTorch install કરો —
> `pip install torch --index-url https://download.pytorch.org/whl/cu121`

---

## 🛠 Troubleshooting

| સમસ્યા | ઉકેલ |
|---|---|
| "Python not found" | Python ફરી install કરો, "Add Python to PATH" ટીક કરીને |
| "AI Model Failed" પહેલી વાર | Internet ચાલુ કરીને app ફરી ચલાવો (model download થશે) |
| Scan બહુ ધીમો | Speed slider વધારો (વધુ frames skip), અથવા Enhancement બંધ કરો |
| PDF export error | `venv` activate કરીને `pip install reportlab` ચલાવો |
| વધુ માહિતી | `i_footege.log` file જુઓ |
