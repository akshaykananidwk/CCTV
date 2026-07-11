# 🦚 Krishna Intelligence

**Forensic CCTV Video Analysis Suite** — `v16.0 Pro Enterprise`

AI-powered desktop software + web panel. The software scans CCTV footage in
batches, detects and tracks persons / vehicles / animals with YOLOv8, captures
one evidence photo per unique object, and pushes the case report to the web
panel. Reports live **only on the website** — the operator receives the view
link on WhatsApp.

---

## ✨ Features

### 💻 Desktop Software (`krishna_intelligence.py`)
- 🔐 **Secure login on startup** — verifies against the web panel; session stays
  valid **7 days**, then login is asked again. **Internet is mandatory** — the
  software will not open without reaching the server.
- 🔑 **Forgot Password** on the login screen — enter username, OTP arrives on
  the registered WhatsApp number, set a new password.
- 🏢 **Police-station header** — comes from the user's web-panel account and is
  printed on top of every PDF report.
- 📂 **Batch analysis**, 🤖 **YOLOv8 detection + tracking** (GPU auto), 🎯 **smart
  filters** (object type + color), 📸 **unique evidence capture**, 🔬 enhancement,
  🌙 night vision, ⏸ pause/resume, live gallery + timeline + stats.
- ☁ **Report ALWAYS uploads** — after every scan (aborted પણ) the report
  (PDF + JSON, **videos never leave the PC**) uploads automatically and a
  **WhatsApp message with the view link** goes to the operator. **No local
  report files** — internet ન હોય તો report ક્યાંય ન મળે; એ hidden queue માં
  રહે અને internet આવે એટલે આપોઆપ (કે SYNC button થી) upload થાય.

### 🕵️ Investigation Tools (v16 — new)
- 👕 **Clothing color split** (upper/lower) for every Person evidence
- 🧭 **Direction of movement** + **approximate relative speed** (px/s,
  uncalibrated — not a real km/h reading)
- ⚠ **Loitering alerts** and **crowd alerts** (thresholds adjustable)
- 🔗 **Cross-video match suggestions** — flags same type+color seen in more
  than one video of the same case (heuristic lead, not identity proof)
- 🧑 **Face recognition** against a local `Known_Suspects/<name>/*.jpg`
  folder (needs `opencv-contrib-python`; train from the sidebar button)
- 🙈 **Blur faces** in saved evidence, 💧 **watermark** evidence photos
- 🔢 **Number-plate OCR** and 🕐 **CCTV overlay-timestamp OCR** (both need
  `pytesseract` + the separate Tesseract-OCR program)
- 🔒 **Encrypt evidence on disk** (needs `pip install cryptography`) — the
  live gallery still shows photos during the session; only the saved file
  is protected once the app closes
- ➕ **Manual evidence add**, ⭐ star, 📝 note, 🗑 delete, 🔍 search, 📦 ZIP
  export, 🎬 **±5s clip export** from the original video, 🔍 in-app zoom
  viewer (works for encrypted evidence too)
- 📋 **Case status/notes/templates**, 📁 **recent cases** (reload evidence
  photos for review), 🆚 **compare two cases** (heuristic)
- 📊 **Analytics dashboard**, 🖨 **print report** (temp file only — no
  report is ever left on the PC, matching the "reports only online" rule)
- 🎚 **Model size / GPU selector + reload**, ⚡ **auto hardware benchmark**,
  ▶ **resume an interrupted scan** after a crash or power cut
- 🔐 **Auto-lock** after N idle minutes (off by default) — unlock re-checks
  the password against the server
- ✅ **PDF verification code** (SHA-256-based, not a legal digital
  signature) + operator/designation stamp on every report; **SHA-256 hash**
  of every source video stored in the report for evidentiary integrity

**Not implemented / intentionally deferred** (so nothing is oversold):
weapon detection (no reliable free model exists), age/gender estimation
(needs pretrained model files not bundled), true multi-camera face re-ID
across separate cameras (only the same-case heuristic above exists), live
RTSP camera feed, multi-video split-screen scanning, true parallel
multi-video GPU processing (a single shared YOLO tracker isn't safe for
that), Excel export of the report (would create a local report copy,
against the "internet-only reports" rule), a QR code linking straight to
the live report URL (needs a small server change), and full Gujarati PDF
text (works only if you supply `fonts/NotoSansGujarati-Regular.ttf`
yourself — the code path is ready, the font file is not bundled). Full
light-theme colors and app-wide font scaling are partially wired (setting
+ toggle exist) but not yet applied to every existing widget.

### 🌐 Web Panel (`server/` — PHP + SQLite)
- 👥 **Admin panel** (`admin/`) — create users (name, office/police station,
  **designation (હોદ્દો)**, username, password, WhatsApp mobile); account
  details **auto-sent on WhatsApp — password is NEVER sent**. Approve /
  disable users, reset passwords.
- ⏳ **Validity control** — admin sets how many days each user can use the
  software (or unlimited); expired accounts cannot login or upload until the
  admin extends them; validity changes notified on WhatsApp.
- 📄 **Reports page** — every report with **copyable report link** and a
  **📲 Send Again** button that re-sends the WhatsApp message with the link.
- 🖥 **Login history** — PC name, operating system, PC user and IP of every
  software login.
- 📝 **Self-registration** (`register.php`, opens from the software's login
  screen too) — full details form (name, office, designation), WhatsApp OTP
  verification, admin approval; confirmation on WhatsApp with **server URL,
  username and all details — never the password**.
- 🔑 **Forgot-password API** — OTP on WhatsApp, old sessions killed on reset.
- 🔗 Reports open only via secret token links; data folder blocked by
  `.htaccess`; passwords hashed; login rate-limited.

---

## 🌐 Server Installation (one time)

Any normal PHP hosting (cPanel etc.), PHP 8.0+ with SQLite.

1. Upload the whole **`server/`** folder, e.g. to `public_html/krishna/`.
2. Edit **`server/config.php`**:
   - `base_url` → your URL, e.g. `https://yourdomain.in/krishna`
   - `admin_user` / `admin_password` → **change the password!**
   - `wa_session_id` / `wa_api_key` → **your bulk.akdwk.in API values**
     (⚠ keep them secret — never post publicly or commit to GitHub)
3. `server/data/` folder writable (755/775).
4. Open `https://yourdomain.in/krishna/admin/` → login → create users.
5. Self-registration: `https://yourdomain.in/krishna/register.php`.

## 🖥 Software Installation (Windows) — સ્થાપના

1. **Python 3.10+** install કરો (<https://www.python.org/downloads/> —
   "Add Python to PATH" ✅).
2. આ folder PC પર copy કરો → **`install_windows.bat`** double-click
   (5–15 મિનિટ, internet).
3. **`run_windows.bat`** double-click → Login window માં **Server URL**,
   username, password નાખો. પહેલી વાર AI model (~22 MB) download થાય.

### 📦 Standalone EXE
`build_exe_windows.bat` → `dist\Krishna-Intelligence\` folder કોઈ પણ PC પર
copy કરીને exe ચલાવો (Python વગર).

---

## 🚀 Workflow — આખો ફ્લો

1. Admin panel માં user બનાવો → WhatsApp પર username/password જાય.
2. Software ખોલો → login (7 દિવસ યાદ; દરેક login PC name/OS/IP સાથે
   admin panel માં દેખાય). Password ભૂલી ગયા? → **Forgot Password** → WhatsApp OTP.
3. Videos load → START → evidence capture.
4. Scan પૂરો (કે abort) → **report આપોઆપ website પર upload** → WhatsApp પર link.
5. Internet ન હોય → report ક્યાંય નહીં મળે; internet આવે એટલે આપોઆપ upload.
6. Admin panel → Reports → link copy કરો કે **Send Again** થી WhatsApp ફરી મોકલો.

### PC પર શું સેવ થાય (ફક્ત evidence photos — report નહીં)
```
Krishna_Forensic_Data/
└── Cases/<CASE_ID>/<video-name>/ID_1_Red_Car_00m_05s_f150.jpg ...
```

---

## ⚙️ Requirements

| Item | Minimum |
|---|---|
| OS (software) | Windows 10/11 |
| Python | 3.10+ |
| RAM | 8 GB (16 GB better) |
| GPU | Optional — NVIDIA હોય તો આપોઆપ વપરાય |
| Server | PHP 8.0+, SQLite (કોઈ પણ cPanel hosting) |
| Internet | ફરજિયાત (login + report upload) |

### 🔧 Optional features — વધારાનું install

| Feature | જરૂરી |
|---|---|
| Face Recognition, Blur Faces | `pip install opencv-contrib-python` (already in requirements.txt, replaces plain opencv-python) |
| Number Plate OCR, Overlay Timestamp OCR | `pip install pytesseract` **+** [Tesseract-OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed separately on Windows |
| Encrypt Evidence on Disk | `pip install cryptography` |
| Corrupt-video auto-repair | [ffmpeg](https://ffmpeg.org/download.html) installed and on PATH |
| Gujarati text in PDF | place a Unicode font at `fonts/NotoSansGujarati-Regular.ttf` |

જે feature નું package install ન હોય એનો switch app માં આપોઆપ disabled (ગ્રે) દેખાશે —
બાકીનું સોફ્ટવેર સામાન્ય રીતે જ ચાલશે.

## 🛠 Troubleshooting

**રિપોર્ટ website પર નથી જતો / WhatsApp નથી આવતો?**
Software ના sidebar માં **🔧 TEST SERVER & UPLOAD** button દબાવો — એ
step-by-step બતાવશે બરાબર ક્યાં અટકે છે (server સુધી પહોંચાય છે કે નહીં,
database, curl, WhatsApp keys, base_url, login session — દરેક ✅/❌ સાથે).
❌ જ્યાં દેખાય ત્યાંથી ઠીક કરો — ઉપરથી નીચે ક્રમમાં (પહેલો ❌ જ સાચું કારણ છે,
પછીના બધા એના પર આધારિત છે).

| સમસ્યા | ઉકેલ |
|---|---|
| "Internet is required" | Internet ચાલુ કરો — server વગર software નહીં ખૂલે |
| WhatsApp message નથી આવતો, પણ report website પર દેખાય છે | Admin panel ઉપર લાલ "Configuration Problem" banner જુઓ, અથવા `config.php` માં `wa_session_id`/`wa_api_key` ચેક કરો |
| Report પણ website પર નથી દેખાતો | **🔧 TEST SERVER & UPLOAD** ચલાવો — Server URL ખોટો છે, hosting પર `server/` update નથી થયું, કે login session expired હોઈ શકે |
| "Account awaiting admin approval" | Admin panel → Users → Approve |
| Report ની link ખોવાઈ ગઈ | Admin panel → Reports → **Send Again** |
| "AI Model Failed" | Internet સાથે ફરી ચલાવો (model download થશે) |
| વધુ માહિતી | `krishna_intelligence.log` જુઓ (server બાજુ error હોય તો hosting ના PHP error log માં પણ) |
