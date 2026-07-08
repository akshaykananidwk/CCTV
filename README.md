# 🦚 Krishna Intelligence

**Forensic CCTV Video Analysis Suite — LCB Technical Cell, Devbhoomi Dwarka**
`v13.0 Pro Enterprise`

AI-powered desktop software + web panel. The software scans CCTV footage in
batches, detects and tracks persons / vehicles / animals with YOLOv8, captures
one evidence photo per unique object, and produces case-wise CSV + PDF reports.
The web panel manages users, logs every software login (with PC details), stores
uploaded reports, and sends WhatsApp messages with report links.

---

## ✨ Features

### 💻 Desktop Software (`krishna_intelligence.py`)
- 🔐 **Secure login on startup** — verifies against the web panel; session stays
  valid **7 days**, then login is asked again. Offline grace inside the 7-day window.
- 🏢 **Police-station header** — comes from the user's web-panel account and is
  printed on top of every PDF report.
- 📂 **Batch analysis**, 🤖 **YOLOv8 detection + tracking** (GPU auto), 🎯 **smart
  filters** (object type + color), 📸 **unique evidence capture**, 🔬 enhancement,
  🌙 night vision, ⏸ pause/resume, live gallery + timeline + stats.
- ☁ **Auto-upload report** — after a scan, only the **PDF + JSON report** is
  uploaded (videos never leave the PC) and a **WhatsApp message with the view
  link** goes to the operator's registered number.
- 📊 Export CSV / 📄 Export PDF anytime.

### 🌐 Web Panel (`server/` — PHP + SQLite)
- 👥 **Admin panel** (`admin/`) — create users (name, police station, username,
  password, WhatsApp mobile). Credentials are **sent automatically on WhatsApp**.
  Approve / disable users, reset passwords (new password sent on WhatsApp).
- 📝 **Self-registration** (`register.php`) — with **WhatsApp OTP** verification;
  account activates after admin approval; success message sent on WhatsApp.
- 🖥 **Login history** — every software login shows **PC name, operating system,
  PC user and IP** in the admin panel.
- 📄 **Reports page** — all uploaded case reports with secure view links.
- 🔗 **view.php** — reports open via secret token links only (the link WhatsApp
  delivers); the data folder itself is blocked by `.htaccess`.

---

## 🌐 Server Installation (one time)

Works on any normal PHP hosting (cPanel etc.), PHP 8.0+ with SQLite (default).

1. Upload the whole **`server/`** folder to your hosting, e.g. to
   `public_html/krishna/`.
2. Edit **`server/config.php`**:
   - `base_url` → your URL, e.g. `https://yourdomain.in/krishna`
   - `admin_user` / `admin_password` → **change the password!**
   - `wa_session_id` / `wa_api_key` → **your bulk.akdwk.in API values**
     (⚠ keep these secret — never post them publicly or commit them to GitHub)
3. Make sure the `server/data/` folder is writable (permission 755/775).
4. Open `https://yourdomain.in/krishna/admin/` → login → create users.
5. Users can also self-register at `https://yourdomain.in/krishna/register.php`
   (WhatsApp OTP → admin approval).

## 🖥 Software Installation (Windows) — સ્થાપના

1. **Python install કરો** (એક જ વાર): <https://www.python.org/downloads/> —
   Python 3.10+, setup વખતે **"Add Python to PATH"** ✅ ટીક કરો.
2. આ આખું folder PC પર copy કરો (દા.ત. `D:\Krishna\`).
3. **`install_windows.bat`** double-click — packages install થશે (5–15 મિનિટ, internet).
4. **`run_windows.bat`** double-click — સોફ્ટવેર ચાલુ.
   - Login window માં **Server URL** (દા.ત. `https://yourdomain.in/krishna`),
     username અને password નાખો.
   - પહેલી વાર AI model (~22 MB) download થાય છે.

### 📦 Standalone EXE (બીજા PC પર Python વગર)
`build_exe_windows.bat` double-click કરો →
`dist\Krishna-Intelligence\` આખું folder કોઈ પણ PC પર copy કરીને exe ચલાવો.

---

## 🚀 Workflow — આખો ફ્લો

1. Admin panel માં user બનાવો (police station + WhatsApp number સાથે)
   → user ને WhatsApp પર username/password મળે.
2. Software ખોલો → login (7 દિવસ યાદ રહે; દરેક login admin panel માં
   PC name/OS/IP સાથે દેખાય).
3. Videos load કરો → START → evidence આપોઆપ capture.
4. Scan પૂરો થાય એટલે **report PDF + JSON આપોઆપ website પર upload** થાય
   (video upload થતો જ નથી) અને operator ના WhatsApp પર report ની link આવે.
5. Link ખોલો → report browser માં ખૂલે; admin panel માં પણ બધા reports દેખાય.
6. PDF માં સૌથી ઉપર police station નું નામ printed હોય.

### Output structure (PC પર)
```
Krishna_Forensic_Data/
└── Cases/
    └── <CASE_ID>/
        ├── <video-name>/ID_1_Red_Car_00m_05s_f150.jpg ...
        ├── report.json
        └── report.pdf
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

> GPU speed: `pip install torch --index-url https://download.pytorch.org/whl/cu121`

## 🛠 Troubleshooting

| સમસ્યા | ઉકેલ |
|---|---|
| "Cannot reach the server" | Server URL ચેક કરો; hosting પર `server/` બરાબર upload થયું છે? |
| WhatsApp message નથી આવતો | `config.php` માં `wa_session_id`/`wa_api_key` ભરેલા છે? |
| "Account awaiting admin approval" | Admin panel → Users → Approve દબાવો |
| "AI Model Failed" | Internet ચાલુ કરીને ફરી ચલાવો (model download થશે) |
| Scan ધીમો | Speed slider વધારો અથવા Enhancement બંધ કરો |
| વધુ માહિતી | `krishna_intelligence.log` જુઓ |
