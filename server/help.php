<?php
/** Krishna Intelligence — public Help / How-To-Use guide. */
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Krishna Intelligence — Help / How To Use</title>
<style>
body{font-family:Arial,sans-serif;background:#0A0E1A;color:#eee;margin:0;line-height:1.6}
a{color:#06B6D4}
.top{background:#111827;padding:14px 22px;display:flex;justify-content:space-between;
     align-items:center;flex-wrap:wrap}
.top h1{color:#F97316;font-size:19px;margin:0}
.nav a{margin-left:16px;font-weight:bold;font-size:13px;text-decoration:none}
.wrap{max-width:820px;margin:22px auto;padding:0 16px}
.card{background:#111827;border-radius:10px;padding:22px;margin-bottom:20px}
h2{color:#F97316;font-size:18px;margin-top:0}
h3{color:#06B6D4;font-size:14px;margin-bottom:6px}
ol,ul{margin:6px 0;padding-left:22px}
li{margin-bottom:6px;font-size:14px}
.step{background:#0A0E1A;border-radius:8px;padding:14px 16px;margin-bottom:14px}
.badge{display:inline-block;background:#064E3B;color:#10B981;padding:2px 10px;
       border-radius:10px;font-size:11px;font-weight:bold;margin-left:6px}
code{background:#0A0E1A;padding:2px 6px;border-radius:4px;font-size:12px}
</style>
</head>
<body>
<div class="top">
  <h1>🦚 Krishna Intelligence — Help</h1>
  <div class="nav">
    <a href="index.php">🏠 Home</a>
    <a href="register.php">📝 Register</a>
    <a href="myreports.php">📄 My Reports</a>
    <a href="admin/">👥 Admin</a>
  </div>
</div>
<div class="wrap">

<div class="card">
<h2>🔰 શરૂઆત કેવી રીતે કરવી — Getting Started</h2>
<div class="step">
<h3>1️⃣ પોલીસ સ્ટેશન/ઓપરેટર માટે — Register</h3>
<ol>
<li><a href="register.php">Register</a> પર જાઓ — નામ, ઓફિસ/પોલીસ સ્ટેશન, હોદ્દો, username, password, WhatsApp mobile ભરો.</li>
<li>WhatsApp પર 6-આંકડાનો OTP આવશે — નાખીને verify કરો.</li>
<li>Admin તમારું account <b>approve</b> કરે પછી જ software માં login થઈ શકાશે — approve થતાં WhatsApp પર જાણ થાય છે.</li>
</ol>
</div>
<div class="step">
<h3>2️⃣ Software Install & Login</h3>
<ol>
<li>Krishna Intelligence સોફ્ટવેર PC પર install કરો (README.md જુઓ).</li>
<li>ખોલો ત્યારે <b>Server URL</b> (આ વેબસાઇટનું URL), તમારો username અને password નાખો.</li>
<li>Login 7 દિવસ યાદ રહે છે — પછી ફરી login માંગશે.</li>
<li>Password ભૂલી ગયા? Login screen પર <b>Forgot Password</b> → WhatsApp OTP → નવો password.</li>
</ol>
</div>
<div class="step">
<h3>3️⃣ Video Scan કરવું</h3>
<ol>
<li><b>LOAD BATCH VIDEOS</b> થી CCTV ફૂટેજ પસંદ કરો (અથવા <b>Add Live Camera</b> થી RTSP camera).</li>
<li>જરૂર હોય તો object/color filter, loiter/crowd threshold, face recognition વગેરે સેટ કરો.</li>
<li><b>▶ START</b> દબાવો — evidence photos જમણી બાજુ gallery માં આવતા જાય.</li>
<li>Scan પૂરો થાય (કે Abort કરો) એટલે <b>report આપોઆપ આ website પર upload</b> થાય છે અને WhatsApp પર link આવે છે.</li>
</ol>
</div>
<div class="step">
<h3>4️⃣ Report જોવું</h3>
<ol>
<li>WhatsApp માં આવેલી link ખોલો — browser માં PDF report ખૂલશે.</li>
<li>અથવા <a href="myreports.php">My Reports</a> માં login કરીને તમારા બધા reports એક જ જગ્યાએ જુઓ.</li>
<li>PDF માં police station નું નામ, operator, verification code, અને (હોય તો) QR code હોય છે.</li>
</ol>
</div>
</div>

<div class="card">
<h2>⚙️ Software ના Functions — શું શું કરે છે</h2>
<ul>
<li><b>Smart Filters:</b> ફક્ત Person/Vehicle/Animal અથવા ચોક્કસ રંગ શોધો.</li>
<li><b>Face Recognition:</b> <code>Known_Suspects</code> folder માં shooter/suspect ના ફોટા મૂકો, "Train Face Recognizer" દબાવો.</li>
<li><b>Number Plate OCR, Overlay Timestamp OCR:</b> આશરે (approximate) reading — extra package જોઈએ.</li>
<li><b>Loitering/Crowd Alerts:</b> કોઈ વ્યક્તિ લાંબો સમય ઊભી હોય કે ભીડ વધારે હોય તો timeline માં alert.</li>
<li><b>Direction/Speed:</b> વ્યક્તિ/ગાડી કઈ દિશામાં ગઈ — આશરે speed (px/s, ચોક્કસ km/h નહીં).</li>
<li><b>Evidence Tools:</b> ➕ Manual add, ⭐ star, 📝 note, 🗑 delete, 🔍 search, 📦 ZIP export, 🎬 clip export.</li>
<li><b>Encryption/Watermark:</b> evidence photos PC પર encrypt/watermark કરી શકાય.</li>
<li><b>Auto-lock:</b> અમુક મિનિટ કંઈ ન કરો તો software lock — ફરી password જોઈએ.</li>
<li><b>Resume Scan:</b> power જાય તો પણ ત્યાંથી જ scan ફરી શરૂ થાય.</li>
</ul>
</div>

<div class="card">
<h2>🌐 Website ના Functions</h2>
<ul>
<li><b><a href="register.php">Register</a>:</b> નવું account — WhatsApp OTP verification.</li>
<li><b><a href="myreports.php">My Reports</a>:</b> operator પોતાના (અને share થયેલા) reports જુએ.</li>
<li><b><a href="admin/">Admin Panel</a>:</b> users બનાવવા/approve, validity, login history, reports, statistics, audit log — ફક્ત admin માટે.</li>
<li><b>Report Link:</b> દરેક report ને એક ગુપ્ત link હોય છે — એ link વગર કોઈ report ખોલી ન શકે.</li>
</ul>
</div>

<div class="card">
<h2>❓ સામાન્ય પ્રશ્નો</h2>
<p><b>Q: Video ક્યાં સચવાય છે?</b><br>Video ક્યારેય website પર upload થતો નથી — ફક્ત PC પર જ રહે છે. Website પર ફક્ત report (PDF/JSON) જાય છે.</p>
<p><b>Q: Internet ન હોય તો?</b><br>Software ખૂલશે નહીં (login ફરજિયાત internet માંગે) અને report internet વગર ક્યાંય upload નહીં થાય — internet આવે એટલે આપોઆપ upload થઈ જાય.</p>
<p><b>Q: Report ની link ખોવાઈ ગઈ?</b><br>Admin panel → Reports → "Send Again" દબાવો, WhatsApp પર ફરી link જશે. અથવા <a href="myreports.php">My Reports</a> માં login કરો.</p>
</div>

</div>
</body>
</html>
