<?php
/**
 * Krishna Intelligence — Operator "My Reports" page.
 * Operators log in with the SAME username/password as the software and
 * see only their own reports (plus any report an admin shared with them).
 */
require_once __DIR__ . '/helpers.php';
session_start();

$pdo = db();
$err = '';

if (isset($_GET['logout'])) {
    unset($_SESSION['op_user_id']);
    header('Location: myreports.php');
    exit;
}

if (($_POST['do'] ?? '') === 'op_login') {
    $username = trim($_POST['username'] ?? '');
    $password = $_POST['password'] ?? '';
    $q = $pdo->prepare("SELECT * FROM users WHERE username = ?");
    $q->execute([$username]);
    $user = $q->fetch(PDO::FETCH_ASSOC);
    $expired = $user && !empty($user['valid_until'])
        && strtotime($user['valid_until']) < time();
    if (!$user || !password_verify($password, $user['password_hash'])) {
        $err = 'Invalid username or password.';
    } elseif ($user['status'] !== 'active') {
        $err = 'Account is not active. Contact admin.';
    } elseif ($expired) {
        $err = 'Account validity expired. Contact admin.';
    } else {
        $_SESSION['op_user_id'] = $user['id'];
        session_regenerate_id(true);
    }
}

$opId = $_SESSION['op_user_id'] ?? null;
$op = null;
if ($opId) {
    $q = $pdo->prepare("SELECT * FROM users WHERE id = ?");
    $q->execute([$opId]);
    $op = $q->fetch(PDO::FETCH_ASSOC);
    if (!$op || $op['status'] !== 'active') {
        unset($_SESSION['op_user_id']);
        $op = null;
    }
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Krishna Intelligence — My Reports</title>
<style>
body{font-family:Arial,sans-serif;background:#0A0E1A;color:#eee;margin:0}
a{color:#06B6D4;text-decoration:none}
.top{background:#111827;padding:14px 22px;display:flex;justify-content:space-between;
     align-items:center;flex-wrap:wrap}
.top h1{color:#F97316;font-size:19px;margin:0}
.nav a{margin-left:16px;font-weight:bold;font-size:13px}
.wrap{max-width:900px;margin:22px auto;padding:0 16px}
.card{background:#111827;border-radius:10px;padding:20px;margin-bottom:20px;overflow-x:auto}
h2{color:#06B6D4;font-size:15px;margin-top:0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid #1F2937;text-align:left}
th{color:#FCD34D;font-size:12px}
input{width:100%;box-sizing:border-box;padding:11px;margin:6px 0;border-radius:7px;
      border:1px solid #333;background:#0A0E1A;color:#eee}
button{padding:11px 16px;border:0;border-radius:7px;background:#10B981;color:#fff;
       font-weight:bold;cursor:pointer;font-size:13px}
.err{color:#EF4444;margin:10px 0}
.login{max-width:340px;margin:12vh auto}
.badge{padding:2px 9px;border-radius:10px;font-size:11px;font-weight:bold;background:#064E3B;color:#10B981}
</style>
</head>
<body>
<?php if (!$op): ?>
  <div class="login card" style="margin-top:12vh">
    <h1 style="color:#F97316;text-align:center">🦚 Krishna Intelligence</h1>
    <p style="text-align:center;color:#06B6D4;font-size:12px">MY REPORTS —
       login with your software username/password</p>
    <form method="post">
      <input type="hidden" name="do" value="op_login">
      <input name="username" placeholder="Username" required>
      <input name="password" type="password" placeholder="Password" required>
      <button style="width:100%;margin-top:6px">🔐 LOGIN</button>
    </form>
    <?php if ($err): ?><p class="err"><?= htmlspecialchars($err) ?></p><?php endif; ?>
    <p style="text-align:center;font-size:12px;margin-top:14px">
      New here? <a href="register.php">Register</a> &nbsp;|&nbsp;
      <a href="help.php">Help</a></p>
  </div>
<?php else: ?>
<div class="top">
  <h1>🦚 My Reports</h1>
  <div class="nav">
    <a href="index.php">🏠 Home</a>
    <a href="help.php">❓ Help</a>
    <a href="?logout=1" style="color:#EF4444">Logout</a>
  </div>
</div>
<div class="wrap">
  <div class="card">
    <h2>👮 <?= htmlspecialchars($op['name']) ?>
        <?php if ($op['designation']): ?>(<?= htmlspecialchars($op['designation']) ?>)<?php endif; ?>
        — 🏢 <?= htmlspecialchars($op['police_station']) ?></h2>
  </div>
  <div class="card">
    <h2>📄 Reports (yours + shared with you)</h2>
    <table>
      <tr><th>Time</th><th>Case ID</th><th>👤</th><th>🚗</th><th>📸</th><th>View</th></tr>
      <?php
      $q = $pdo->prepare(
          "SELECT r.*, CASE WHEN r.user_id = ? THEN 'Mine' ELSE 'Shared' END AS kind
           FROM reports r
           LEFT JOIN report_shares s ON s.report_id = r.id AND s.user_id = ?
           WHERE r.user_id = ? OR s.user_id = ?
           ORDER BY r.id DESC LIMIT 200");
      $q->execute([$opId, $opId, $opId, $opId]);
      foreach ($q as $r):
      ?>
      <tr>
        <td><?= $r['created_at'] ?></td>
        <td><?= htmlspecialchars($r['case_id']) ?>
            <?php if ($r['kind'] === 'Shared'): ?><span class="badge">SHARED</span><?php endif; ?></td>
        <td><?= $r['persons'] ?></td>
        <td><?= $r['vehicles'] ?></td>
        <td><?= $r['total'] ?></td>
        <td>
          <?php if ($r['pdf_file']): ?>
            <a href="view.php?t=<?= $r['view_token'] ?>" target="_blank">PDF</a>
          <?php endif; ?>
          <?php if ($r['json_file']): ?>
            <a href="view.php?t=<?= $r['view_token'] ?>&f=json" target="_blank">JSON</a>
          <?php endif; ?>
        </td>
      </tr>
      <?php endforeach; ?>
    </table>
  </div>
</div>
<?php endif; ?>
</body>
</html>
