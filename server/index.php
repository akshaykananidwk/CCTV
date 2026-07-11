<?php
/** Krishna Intelligence — web panel home / navigation page. */
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Krishna Intelligence — Web Panel</title>
<style>
body{font-family:Arial,sans-serif;background:#0A0E1A;color:#eee;margin:0;
     display:flex;flex-direction:column;min-height:100vh}
.hero{text-align:center;padding:60px 20px 30px}
.hero h1{color:#F97316;font-size:34px;margin:0 0 6px}
.hero p{color:#06B6D4;font-size:14px;margin:0}
.grid{max-width:900px;margin:30px auto;padding:0 16px;display:grid;
      grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px;
      flex:1}
.card{background:#111827;border-radius:12px;padding:26px 20px;text-align:center;
      text-decoration:none;color:#eee;transition:transform .15s}
.card:hover{transform:translateY(-3px);background:#1a2436}
.card .ic{font-size:34px;display:block;margin-bottom:10px}
.card b{display:block;font-size:15px;color:#F97316;margin-bottom:4px}
.card span{font-size:12px;color:#94A3B8}
footer{text-align:center;padding:20px;font-size:11px;color:#475569}
</style>
</head>
<body>
<div class="hero">
  <h1>🦚 Krishna Intelligence</h1>
  <p>Forensic CCTV Video Analysis Suite — Web Panel</p>
</div>
<div class="grid">
  <a class="card" href="register.php">
    <span class="ic">📝</span><b>Register</b>
    <span>New officer? Create your account (WhatsApp OTP)</span>
  </a>
  <a class="card" href="myreports.php">
    <span class="ic">📄</span><b>My Reports</b>
    <span>Login to see your case reports</span>
  </a>
  <a class="card" href="help.php">
    <span class="ic">❓</span><b>Help / How To Use</b>
    <span>Full guide — software + website</span>
  </a>
  <a class="card" href="admin/">
    <span class="ic">👥</span><b>Admin Panel</b>
    <span>Users, validity, reports, statistics (admin only)</span>
  </a>
</div>
<footer>Krishna Intelligence — reports are never available without internet;
videos never leave the officer's PC.</footer>
</body>
</html>
