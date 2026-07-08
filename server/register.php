<?php
/**
 * Krishna Intelligence — self-registration with WhatsApp OTP.
 * New accounts stay "pending" until the admin approves them.
 */
require_once __DIR__ . '/helpers.php';
session_start();

$step = $_SESSION['reg_step'] ?? 1;
$msg = '';
$err = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    if (isset($_POST['send_otp'])) {
        $name = trim($_POST['name'] ?? '');
        $station = trim($_POST['police_station'] ?? '');
        $username = trim($_POST['username'] ?? '');
        $password = $_POST['password'] ?? '';
        $mobile = normalize_mobile($_POST['mobile'] ?? '');

        if ($name === '' || $station === '' || $username === ''
            || strlen($password) < 6 || strlen($mobile) !== 12) {
            $err = 'Fill all fields (password min 6 chars, valid 10-digit mobile).';
        } elseif (!preg_match('/^[A-Za-z0-9_.-]{3,30}$/', $username)) {
            $err = 'Username: 3-30 chars, letters/numbers/._- only.';
        } else {
            $q = db()->prepare("SELECT id FROM users WHERE username = ?");
            $q->execute([$username]);
            if ($q->fetch()) {
                $err = 'Username already taken.';
            } elseif (!otp_send($mobile, 'register')) {
                $err = 'Could not send OTP (limit reached or WhatsApp API not configured).';
            } else {
                $_SESSION['reg'] = [
                    'name' => $name, 'police_station' => $station,
                    'username' => $username,
                    'password_hash' => password_hash($password, PASSWORD_DEFAULT),
                    'mobile' => $mobile,
                ];
                $_SESSION['reg_step'] = $step = 2;
                $msg = "OTP sent on WhatsApp to $mobile.";
            }
        }
    } elseif (isset($_POST['verify_otp']) && !empty($_SESSION['reg'])) {
        $reg = $_SESSION['reg'];
        if (!otp_verify($reg['mobile'], $_POST['otp'] ?? '', 'register')) {
            $err = 'Wrong or expired OTP.';
            $step = 2;
        } else {
            $ins = db()->prepare("INSERT INTO users
                (username, password_hash, name, police_station, mobile, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)");
            try {
                $ins->execute([$reg['username'], $reg['password_hash'], $reg['name'],
                    $reg['police_station'], $reg['mobile'], now()]);
                wa_send($reg['mobile'],
                    "🦚 Krishna Intelligence\n✅ Registration successful!\n"
                    . "👤 Username: {$reg['username']}\n"
                    . "🏢 {$reg['police_station']}\n"
                    . "Your software account is ready — it will activate "
                    . "after admin approval.");
                unset($_SESSION['reg'], $_SESSION['reg_step']);
                $step = 3;
            } catch (PDOException $e) {
                $err = 'Username already taken.';
                $step = 1;
                unset($_SESSION['reg'], $_SESSION['reg_step']);
            }
        }
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Krishna Intelligence — Registration</title>
<style>
body{font-family:Arial,sans-serif;background:#0A0E1A;color:#eee;display:flex;
     justify-content:center;align-items:center;min-height:100vh;margin:0}
.card{background:#111827;padding:32px;border-radius:12px;width:360px;max-width:92vw}
h1{color:#F97316;font-size:22px;margin:0 0 4px;text-align:center}
h2{color:#06B6D4;font-size:12px;margin:0 0 20px;text-align:center;font-weight:normal}
input{width:100%;box-sizing:border-box;padding:11px;margin:6px 0;border-radius:7px;
      border:1px solid #333;background:#0A0E1A;color:#eee}
button{width:100%;padding:12px;margin-top:14px;border:0;border-radius:7px;
       background:#10B981;color:#fff;font-weight:bold;cursor:pointer;font-size:14px}
.err{color:#EF4444;font-size:13px;margin-top:10px;text-align:center}
.msg{color:#10B981;font-size:13px;margin-top:10px;text-align:center}
.ok{color:#10B981;text-align:center;font-size:15px;line-height:1.6}
</style>
</head>
<body>
<div class="card">
<h1>🦚 Krishna Intelligence</h1>
<h2>LCB Technical Cell | Devbhoomi Dwarka — New Registration</h2>
<?php if ($step === 1): ?>
  <form method="post">
    <input name="name" placeholder="Full Name" required>
    <input name="police_station" placeholder="Police Station Name" required>
    <input name="username" placeholder="Username" required>
    <input name="password" type="password" placeholder="Password (min 6 chars)" required>
    <input name="mobile" placeholder="WhatsApp Mobile (10 digits)" required>
    <button name="send_otp" value="1">📲 Send WhatsApp OTP</button>
  </form>
<?php elseif ($step === 2): ?>
  <form method="post">
    <p style="text-align:center;font-size:13px">Enter the 6-digit OTP sent on WhatsApp.</p>
    <input name="otp" placeholder="OTP" maxlength="6" required
           style="text-align:center;font-size:20px;letter-spacing:6px">
    <button name="verify_otp" value="1">✅ Verify &amp; Register</button>
  </form>
<?php else: ?>
  <p class="ok">✅ Registration successful!<br>
  A WhatsApp confirmation was sent to your number.<br><br>
  Your account will be activated after admin approval — then login from the
  Krishna Intelligence software.</p>
<?php endif; ?>
<?php if ($err): ?><p class="err"><?= htmlspecialchars($err) ?></p><?php endif; ?>
<?php if ($msg): ?><p class="msg"><?= htmlspecialchars($msg) ?></p><?php endif; ?>
</div>
</body>
</html>
