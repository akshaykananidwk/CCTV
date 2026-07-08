<?php
/**
 * Krishna Intelligence — Admin Panel.
 * Users (create/approve/disable/reset password), login history with
 * PC details, and uploaded reports.
 */
require_once __DIR__ . '/../helpers.php';
session_start();

$c = cfg();
$pdo = db();
$err = '';
$msg = '';

// ---------------------------------------------------------------- logout ---
if (isset($_GET['logout'])) {
    unset($_SESSION['admin']);
    header('Location: index.php');
    exit;
}

// ----------------------------------------------------------------- login ---
if (($_POST['do'] ?? '') === 'admin_login') {
    if (hash_equals($c['admin_user'], $_POST['u'] ?? '')
        && hash_equals($c['admin_password'], $_POST['p'] ?? '')) {
        $_SESSION['admin'] = true;
        session_regenerate_id(true);
    } else {
        $err = 'Wrong admin username or password.';
    }
}

$logged = !empty($_SESSION['admin']);

// ---------------------------------------------------------------- actions --
if ($logged && $_SERVER['REQUEST_METHOD'] === 'POST') {
    $do = $_POST['do'] ?? '';

    if ($do === 'add_user') {
        $name = trim($_POST['name'] ?? '');
        $station = trim($_POST['police_station'] ?? '');
        $username = trim($_POST['username'] ?? '');
        $password = $_POST['password'] ?? '';
        $mobile = normalize_mobile($_POST['mobile'] ?? '');
        if ($name === '' || $station === '' || strlen($password) < 6
            || !preg_match('/^[A-Za-z0-9_.-]{3,30}$/', $username)
            || strlen($mobile) !== 12) {
            $err = 'Check the fields (password ≥ 6, valid username & 10-digit mobile).';
        } else {
            try {
                $pdo->prepare("INSERT INTO users
                    (username, password_hash, name, police_station, mobile, status, created_at)
                    VALUES (?, ?, ?, ?, ?, 'active', ?)")
                    ->execute([$username, password_hash($password, PASSWORD_DEFAULT),
                        $name, $station, $mobile, now()]);
                wa_send($mobile,
                    "🦚 Krishna Intelligence\n✅ Your software account is ready!\n"
                    . "👤 Username: $username\n🔑 Password: $password\n"
                    . "🏢 $station\nLogin from the software now.");
                $msg = "User '$username' created and WhatsApp sent.";
            } catch (PDOException $e) {
                $err = 'Username already exists.';
            }
        }
    }

    if ($do === 'set_status' && isset($_POST['uid'], $_POST['status'])
        && in_array($_POST['status'], ['active', 'disabled'], true)) {
        $pdo->prepare("UPDATE users SET status = ? WHERE id = ?")
            ->execute([$_POST['status'], (int)$_POST['uid']]);
        if ($_POST['status'] === 'disabled') {
            // Kill all live software sessions of the disabled user.
            $pdo->prepare("DELETE FROM sessions WHERE user_id = ?")
                ->execute([(int)$_POST['uid']]);
        } else {
            $u = $pdo->prepare("SELECT * FROM users WHERE id = ?");
            $u->execute([(int)$_POST['uid']]);
            if ($row = $u->fetch(PDO::FETCH_ASSOC)) {
                wa_send($row['mobile'],
                    "🦚 Krishna Intelligence\n✅ Your account '{$row['username']}' "
                    . "is now ACTIVE. You can login from the software.");
            }
        }
        $msg = 'User status updated.';
    }

    if ($do === 'reset_pass' && isset($_POST['uid'])) {
        $u = $pdo->prepare("SELECT * FROM users WHERE id = ?");
        $u->execute([(int)$_POST['uid']]);
        if ($row = $u->fetch(PDO::FETCH_ASSOC)) {
            $new = substr(str_shuffle('ABCDEFGHJKLMNPQRSTUVWXYZ23456789'), 0, 8);
            $pdo->prepare("UPDATE users SET password_hash = ? WHERE id = ?")
                ->execute([password_hash($new, PASSWORD_DEFAULT), $row['id']]);
            $pdo->prepare("DELETE FROM sessions WHERE user_id = ?")
                ->execute([$row['id']]);
            wa_send($row['mobile'],
                "🦚 Krishna Intelligence\n🔑 Password reset for '{$row['username']}'.\n"
                . "New password: $new");
            $msg = "Password reset — sent on WhatsApp to {$row['mobile']}.";
        }
    }

    if ($do === 'resend_report' && isset($_POST['rid'])) {
        $r = $pdo->prepare("SELECT r.*, u.mobile, u.police_station FROM reports r
                            JOIN users u ON u.id = r.user_id WHERE r.id = ?");
        $r->execute([(int)$_POST['rid']]);
        if ($row = $r->fetch(PDO::FETCH_ASSOC)) {
            $viewUrl = cfg()['base_url'] . '/view.php?t=' . $row['view_token'];
            $m = "🦚 Krishna Intelligence\n"
               . "📋 Case: {$row['case_id']}\n"
               . "🏢 {$row['police_station']}\n"
               . "👤 Persons: {$row['persons']} | 🚗 Vehicles: {$row['vehicles']}"
               . " | 📸 Total: {$row['total']}\n"
               . "🔗 View report: $viewUrl";
            $ok = wa_send($row['mobile'], $m, $row['pdf_file'] ? $viewUrl : '');
            $msg = $ok ? "WhatsApp sent again to {$row['mobile']}."
                       : 'WhatsApp send failed — check API config.';
        }
    }

    if ($do === 'del_report' && isset($_POST['rid'])) {
        $r = $pdo->prepare("SELECT * FROM reports WHERE id = ?");
        $r->execute([(int)$_POST['rid']]);
        if ($row = $r->fetch(PDO::FETCH_ASSOC)) {
            foreach (['pdf_file', 'json_file'] as $f) {
                if ($row[$f] && is_file(__DIR__ . '/../data/reports/' . $row[$f])) {
                    unlink(__DIR__ . '/../data/reports/' . $row[$f]);
                }
            }
            $pdo->prepare("DELETE FROM reports WHERE id = ?")->execute([$row['id']]);
            $msg = 'Report deleted.';
        }
    }
}

$page = $_GET['page'] ?? 'users';
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Krishna Intelligence — Admin Panel</title>
<style>
body{font-family:Arial,sans-serif;background:#0A0E1A;color:#eee;margin:0}
a{color:#06B6D4;text-decoration:none}
.top{background:#111827;padding:14px 22px;display:flex;justify-content:space-between;
     align-items:center;flex-wrap:wrap}
.top h1{color:#F97316;font-size:19px;margin:0}
.nav a{margin-left:16px;font-weight:bold;font-size:14px}
.wrap{max-width:1150px;margin:22px auto;padding:0 16px}
.card{background:#111827;border-radius:10px;padding:20px;margin-bottom:20px;overflow-x:auto}
h2{color:#06B6D4;font-size:15px;margin-top:0}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid #1F2937;text-align:left}
th{color:#FCD34D;font-size:12px}
input,select{padding:9px;margin:4px 4px 4px 0;border-radius:6px;border:1px solid #333;
       background:#0A0E1A;color:#eee}
button{padding:8px 14px;border:0;border-radius:6px;background:#10B981;color:#fff;
       font-weight:bold;cursor:pointer;font-size:12px}
button.warn{background:#EF4444}
button.gray{background:#374151}
.badge{padding:2px 9px;border-radius:10px;font-size:11px;font-weight:bold}
.b-active{background:#064E3B;color:#10B981}
.b-pending{background:#453411;color:#F59E0B}
.b-disabled{background:#450A0A;color:#EF4444}
.b-success{background:#064E3B;color:#10B981}
.b-failed{background:#450A0A;color:#EF4444}
.err{color:#EF4444;margin:10px 0}
.msg{color:#10B981;margin:10px 0}
.login{max-width:340px;margin:12vh auto}
.stat{display:inline-block;background:#0A0E1A;border-radius:8px;
      padding:12px 22px;margin:0 10px 10px 0;text-align:center}
.stat b{display:block;font-size:22px;color:#F97316}
</style>
</head>
<body>
<?php if (!$logged): ?>
  <div class="login card" style="margin-top:12vh">
    <h1 style="color:#F97316;text-align:center">🦚 Krishna Intelligence</h1>
    <p style="text-align:center;color:#06B6D4;font-size:12px">ADMIN PANEL</p>
    <form method="post">
      <input type="hidden" name="do" value="admin_login">
      <input name="u" placeholder="Admin username" style="width:100%;box-sizing:border-box" required>
      <input name="p" type="password" placeholder="Admin password" style="width:100%;box-sizing:border-box" required>
      <button style="width:100%;margin-top:12px;padding:12px">🔐 LOGIN</button>
    </form>
    <?php if ($err): ?><p class="err"><?= htmlspecialchars($err) ?></p><?php endif; ?>
  </div>
<?php else: ?>
<div class="top">
  <h1>🦚 Krishna Intelligence — Admin</h1>
  <div class="nav">
    <a href="?page=users">👥 Users</a>
    <a href="?page=logins">🖥 Login History</a>
    <a href="?page=reports">📄 Reports</a>
    <a href="?logout=1" style="color:#EF4444">Logout</a>
  </div>
</div>
<div class="wrap">
<?php if ($err): ?><p class="err"><?= htmlspecialchars($err) ?></p><?php endif; ?>
<?php if ($msg): ?><p class="msg"><?= htmlspecialchars($msg) ?></p><?php endif; ?>

<?php
$totU = $pdo->query("SELECT COUNT(*) FROM users")->fetchColumn();
$totR = $pdo->query("SELECT COUNT(*) FROM reports")->fetchColumn();
$totL = $pdo->query("SELECT COUNT(*) FROM login_logs")->fetchColumn();
?>
<div>
  <span class="stat"><b><?= $totU ?></b>Users</span>
  <span class="stat"><b><?= $totR ?></b>Reports</span>
  <span class="stat"><b><?= $totL ?></b>Logins</span>
</div>

<?php if ($page === 'users'): ?>
  <div class="card">
    <h2>➕ Create New User (WhatsApp credentials sent automatically)</h2>
    <form method="post">
      <input type="hidden" name="do" value="add_user">
      <input name="name" placeholder="Full Name" required>
      <input name="police_station" placeholder="Police Station" required>
      <input name="username" placeholder="Username" required>
      <input name="password" placeholder="Password (min 6)" required>
      <input name="mobile" placeholder="WhatsApp Mobile" required>
      <button>Create & Send WhatsApp</button>
    </form>
  </div>
  <div class="card">
    <h2>👥 All Users</h2>
    <table>
      <tr><th>ID</th><th>Name</th><th>Police Station</th><th>Username</th>
          <th>Mobile</th><th>Status</th><th>Created</th><th>Actions</th></tr>
      <?php foreach ($pdo->query("SELECT * FROM users ORDER BY id DESC") as $u): ?>
      <tr>
        <td><?= $u['id'] ?></td>
        <td><?= htmlspecialchars($u['name']) ?></td>
        <td><?= htmlspecialchars($u['police_station']) ?></td>
        <td><?= htmlspecialchars($u['username']) ?></td>
        <td><?= htmlspecialchars($u['mobile']) ?></td>
        <td><span class="badge b-<?= $u['status'] ?>"><?= strtoupper($u['status']) ?></span></td>
        <td><?= $u['created_at'] ?></td>
        <td>
          <form method="post" style="display:inline">
            <input type="hidden" name="uid" value="<?= $u['id'] ?>">
            <?php if ($u['status'] !== 'active'): ?>
              <input type="hidden" name="do" value="set_status">
              <input type="hidden" name="status" value="active">
              <button>Approve</button>
            <?php else: ?>
              <input type="hidden" name="do" value="set_status">
              <input type="hidden" name="status" value="disabled">
              <button class="warn">Disable</button>
            <?php endif; ?>
          </form>
          <form method="post" style="display:inline">
            <input type="hidden" name="do" value="reset_pass">
            <input type="hidden" name="uid" value="<?= $u['id'] ?>">
            <button class="gray">Reset Pass</button>
          </form>
        </td>
      </tr>
      <?php endforeach; ?>
    </table>
  </div>

<?php elseif ($page === 'logins'): ?>
  <div class="card">
    <h2>🖥 Login History — which PC, PC name, basic information</h2>
    <table>
      <tr><th>Time</th><th>Username</th><th>PC Name</th><th>Operating System</th>
          <th>PC User</th><th>IP Address</th><th>Result</th></tr>
      <?php foreach ($pdo->query(
          "SELECT * FROM login_logs ORDER BY id DESC LIMIT 300") as $l): ?>
      <tr>
        <td><?= $l['created_at'] ?></td>
        <td><?= htmlspecialchars($l['username']) ?></td>
        <td><?= htmlspecialchars($l['device_name']) ?></td>
        <td><?= htmlspecialchars($l['device_os']) ?></td>
        <td><?= htmlspecialchars($l['device_user']) ?></td>
        <td><?= htmlspecialchars($l['ip']) ?></td>
        <td><span class="badge b-<?= $l['status'] ?>"><?= strtoupper($l['status']) ?></span></td>
      </tr>
      <?php endforeach; ?>
    </table>
  </div>

<?php elseif ($page === 'reports'): ?>
  <div class="card">
    <h2>📄 Uploaded Case Reports</h2>
    <table>
      <tr><th>Time</th><th>Case ID</th><th>Operator</th><th>Police Station</th>
          <th>👤</th><th>🚗</th><th>📸</th><th>View</th>
          <th>Report Link</th><th>Actions</th></tr>
      <?php foreach ($pdo->query(
          "SELECT r.*, u.username, u.police_station FROM reports r
           JOIN users u ON u.id = r.user_id ORDER BY r.id DESC LIMIT 300") as $r):
          $link = cfg()['base_url'] . '/view.php?t=' . $r['view_token']; ?>
      <tr>
        <td><?= $r['created_at'] ?></td>
        <td><?= htmlspecialchars($r['case_id']) ?></td>
        <td><?= htmlspecialchars($r['username']) ?></td>
        <td><?= htmlspecialchars($r['police_station']) ?></td>
        <td><?= $r['persons'] ?></td>
        <td><?= $r['vehicles'] ?></td>
        <td><?= $r['total'] ?></td>
        <td>
          <?php if ($r['pdf_file']): ?>
            <a href="../view.php?t=<?= $r['view_token'] ?>" target="_blank">PDF</a>
          <?php endif; ?>
          <?php if ($r['json_file']): ?>
            <a href="../view.php?t=<?= $r['view_token'] ?>&f=json" target="_blank">JSON</a>
          <?php endif; ?>
        </td>
        <td>
          <input readonly value="<?= htmlspecialchars($link) ?>"
                 style="width:190px;font-size:11px"
                 onclick="this.select();document.execCommand('copy');
                          this.style.borderColor='#10B981';"
                 title="Click to copy link">
        </td>
        <td style="white-space:nowrap">
          <form method="post" style="display:inline">
            <input type="hidden" name="do" value="resend_report">
            <input type="hidden" name="rid" value="<?= $r['id'] ?>">
            <button title="Send the report link again on WhatsApp">📲 Send Again</button>
          </form>
          <form method="post" style="display:inline"
                onsubmit="return confirm('Delete this report?')">
            <input type="hidden" name="do" value="del_report">
            <input type="hidden" name="rid" value="<?= $r['id'] ?>">
            <button class="warn">Delete</button>
          </form>
        </td>
      </tr>
      <?php endforeach; ?>
    </table>
  </div>
<?php endif; ?>
</div>
<?php endif; ?>
</body>
</html>
