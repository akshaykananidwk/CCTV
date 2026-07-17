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

// ------------------------------------------------------- file downloads ----
// Handled before any HTML output since they send their own headers.
if ($logged && isset($_GET['export']) && $_GET['export'] === 'reports_csv') {
    header('Content-Type: text/csv; charset=utf-8');
    header('Content-Disposition: attachment; filename="krishna_reports.csv"');
    $out = fopen('php://output', 'w');
    fputcsv($out, ['Date', 'Case ID', 'Operator', 'Police Station',
        'Persons', 'Vehicles', 'Total', 'View Link']);
    foreach ($pdo->query(
        "SELECT r.*, u.username, u.police_station FROM reports r
         JOIN users u ON u.id = r.user_id ORDER BY r.id DESC") as $r) {
        fputcsv($out, [$r['created_at'], $r['case_id'], $r['username'],
            $r['police_station'], $r['persons'], $r['vehicles'], $r['total'],
            cfg()['base_url'] . '/view.php?t=' . $r['view_token']]);
    }
    fclose($out);
    audit_log('export_csv', 'reports', 'Admin exported reports CSV');
    exit;
}

if ($logged && isset($_GET['export']) && $_GET['export'] === 'reports_zip') {
    $zipPath = tempnam(sys_get_temp_dir(), 'krishna_zip_');
    $zip = new ZipArchive();
    $zip->open($zipPath, ZipArchive::OVERWRITE);
    $reportsDir = __DIR__ . '/../data/reports';
    foreach ($pdo->query(
        "SELECT case_id, pdf_file FROM reports
         WHERE pdf_file IS NOT NULL ORDER BY id DESC LIMIT 500") as $r) {
        $full = "$reportsDir/{$r['pdf_file']}";
        if (is_file($full)) {
            $safeCase = preg_replace('/[^A-Za-z0-9_-]/', '_', $r['case_id']);
            $zip->addFile($full, "{$safeCase}_{$r['pdf_file']}");
        }
    }
    $zip->close();
    audit_log('export_zip', 'reports', 'Admin downloaded all report PDFs as ZIP');
    header('Content-Type: application/zip');
    header('Content-Disposition: attachment; filename="krishna_all_reports.zip"');
    header('Content-Length: ' . filesize($zipPath));
    readfile($zipPath);
    unlink($zipPath);
    exit;
}

// ---------------------------------------------------------------- actions --
if ($logged && $_SERVER['REQUEST_METHOD'] === 'POST') {
    $do = $_POST['do'] ?? '';

    if ($do === 'add_user') {
        $name = trim($_POST['name'] ?? '');
        $station = trim($_POST['police_station'] ?? '');
        $designation = trim($_POST['designation'] ?? '');
        $username = trim($_POST['username'] ?? '');
        $password = $_POST['password'] ?? '';
        $mobile = normalize_mobile($_POST['mobile'] ?? '');
        $validDays = (int)($_POST['valid_days'] ?? 0);
        $validUntil = $validDays > 0
            ? date('Y-m-d H:i:s', strtotime("+$validDays days")) : null;
        if ($name === '' || $station === '' || strlen($password) < 6
            || !preg_match('/^[A-Za-z0-9_.-]{3,30}$/', $username)
            || strlen($mobile) !== 12) {
            $err = 'Check the fields (password ≥ 6, valid username & 10-digit mobile).';
        } else {
            try {
                $pdo->prepare("INSERT INTO users
                    (username, password_hash, name, police_station, designation,
                     mobile, status, valid_until, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)")
                    ->execute([$username, password_hash($password, PASSWORD_DEFAULT),
                        $name, $station, $designation, $mobile,
                        $validUntil, now()]);
                // The password is NEVER sent on WhatsApp — the admin gives
                // it personally, or the user sets one via Forgot Password.
                wa_send($mobile,
                    "🦚 Krishna Intelligence\n"
                    . "✅ Your software account is ready!\n"
                    . "🙍 Name: $name\n"
                    . "🏢 Office: $station\n"
                    . "🎖 Designation: $designation\n"
                    . "👤 Username: $username\n"
                    . "🌐 Server URL: " . cfg()['base_url'] . "\n"
                    . "⏳ Validity: " . ($validUntil
                        ? "till " . date('d-m-Y', strtotime($validUntil))
                        : "unlimited") . "\n"
                    . "🔑 Password: get it from your admin, or use "
                    . "'Forgot Password' in the software to set your own.");
                $msg = "User '$username' created and WhatsApp sent "
                     . "(password NOT included in the message).";
                audit_log('add_user', $username, "station=$station validity=" .
                    ($validUntil ?: 'unlimited'));
            } catch (PDOException $e) {
                $err = 'Username already exists.';
            }
        }
    }

    if ($do === 'set_validity' && isset($_POST['uid'])) {
        $days = (int)($_POST['days'] ?? 0);
        $validUntil = $days > 0
            ? date('Y-m-d H:i:s', strtotime("+$days days")) : null;
        $pdo->prepare("UPDATE users SET valid_until = ? WHERE id = ?")
            ->execute([$validUntil, (int)$_POST['uid']]);
        $u = $pdo->prepare("SELECT * FROM users WHERE id = ?");
        $u->execute([(int)$_POST['uid']]);
        if ($row = $u->fetch(PDO::FETCH_ASSOC)) {
            wa_send($row['mobile'],
                "🦚 Krishna Intelligence\n"
                . "⏳ Account validity updated for '{$row['username']}': "
                . ($validUntil
                    ? "valid till " . date('d-m-Y', strtotime($validUntil))
                    : "unlimited") . ".");
            $msg = "Validity for '{$row['username']}' set to "
                 . ($validUntil ? date('d-m-Y', strtotime($validUntil))
                                : 'unlimited') . ".";
            audit_log('set_validity', $row['username'],
                $validUntil ? "till $validUntil" : 'unlimited');
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
        audit_log('set_status', (string)$_POST['uid'], $_POST['status']);
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
            // Password is NEVER sent on WhatsApp — shown to the admin only.
            wa_send($row['mobile'],
                "🦚 Krishna Intelligence\n"
                . "🔑 Your password was reset by admin for "
                . "'{$row['username']}'.\nGet the new password from your "
                . "admin, or use 'Forgot Password' in the software.");
            $msg = "Password for '{$row['username']}' reset to: $new "
                 . "(share it personally — NOT sent on WhatsApp).";
            audit_log('reset_pass', $row['username'], 'Password reset by admin');
        }
    }

    if ($do === 'share_report' && isset($_POST['rid'])) {
        $target = trim($_POST['share_username'] ?? '');
        $u = $pdo->prepare("SELECT id FROM users WHERE username = ?");
        $u->execute([$target]);
        $targetUser = $u->fetch(PDO::FETCH_ASSOC);
        if (!$targetUser) {
            $err = "User '$target' not found.";
        } else {
            try {
                $pdo->prepare(
                    "INSERT INTO report_shares (report_id, user_id, added_at)
                     VALUES (?, ?, ?)")
                    ->execute([(int)$_POST['rid'], $targetUser['id'], now()]);
                $msg = "Report shared with '$target' — it will appear in "
                     . "their My Reports page.";
                audit_log('share_report', (string)$_POST['rid'], "with=$target");
            } catch (PDOException $e) {
                $err = "Already shared with '$target'.";
            }
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
            [$ok, $reason] = wa_send($row['mobile'], $m, $row['pdf_file'] ? $viewUrl : '');
            $msg = $ok ? "WhatsApp sent again to {$row['mobile']}."
                       : "WhatsApp send failed: $reason";
            audit_log('resend_report', (string)$_POST['rid'], "case={$row['case_id']}");
        }
    }

    if ($do === 'test_whatsapp' && !empty($_POST['test_mobile'])) {
        $testMobile = trim($_POST['test_mobile']);
        [$waTestOk, $waTestReason] = wa_send($testMobile,
            "🦚 Krishna Intelligence — this is a TEST message from the "
            . "admin panel (" . now() . "). If you received this, WhatsApp "
            . "sending is working correctly.");
        $waTestResult = $waTestOk
            ? "✅ Gateway accepted the message. Raw response: "
              . htmlspecialchars(substr($waTestReason, 0, 400))
              . " — now check the phone ($testMobile) actually received it "
              . "within a minute; if not, the gateway itself is lying about "
              . "delivery and bulk.akdwk.in needs checking directly."
            : "❌ Send failed: " . htmlspecialchars($waTestReason);
        audit_log('test_whatsapp', $testMobile, $waTestOk ? 'accepted' : 'failed');
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
            $pdo->prepare("DELETE FROM report_shares WHERE report_id = ?")
                ->execute([$row['id']]);
            $msg = 'Report deleted.';
            audit_log('del_report', (string)$row['id'], "case={$row['case_id']}");
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
    <a href="?page=stats">📊 Statistics</a>
    <a href="?page=audit">🧾 Audit Log</a>
    <a href="../help.php" target="_blank">❓ Help</a>
    <a href="?logout=1" style="color:#EF4444">Logout</a>
  </div>
</div>
<div class="wrap">
<?php
$configWarnings = [];
if (strpos($c['wa_session_id'], 'PASTE_') === 0 || strpos($c['wa_api_key'], 'PASTE_') === 0) {
    $configWarnings[] = 'WhatsApp API not configured — edit server/config.php '
        . '(wa_session_id / wa_api_key) or NO messages or report links will '
        . 'ever be sent.';
}
if (strpos($c['base_url'], 'CHANGE-ME') !== false) {
    $configWarnings[] = "base_url in server/config.php is still the example "
        . "placeholder — report links in WhatsApp messages will be broken.";
}
if (!function_exists('curl_init')) {
    $configWarnings[] = 'PHP curl extension is not enabled on this server — '
        . 'WhatsApp messages cannot be sent. Ask your hosting provider to '
        . 'enable ext-curl.';
}
if (!is_writable(__DIR__ . '/../data')) {
    $configWarnings[] = 'server/data/ is not writable — reports cannot be '
        . 'saved. Fix folder permissions (755 or 775).';
}
if ($configWarnings): ?>
  <div class="card" style="border:2px solid #EF4444;background:#2A0E0E">
    <h2 style="color:#EF4444">⚠ Configuration Problem(s) Found</h2>
    <ul style="margin:0;padding-left:20px;font-size:13px">
      <?php foreach ($configWarnings as $w): ?>
        <li style="margin-bottom:6px"><?= htmlspecialchars($w) ?></li>
      <?php endforeach; ?>
    </ul>
  </div>
<?php endif; ?>
<?php if ($err): ?><p class="err"><?= htmlspecialchars($err) ?></p><?php endif; ?>
<?php if ($msg): ?><p class="msg"><?= htmlspecialchars($msg) ?></p><?php endif; ?>

<div class="card">
  <h2>📲 Send Test WhatsApp Message</h2>
  <p style="font-size:12px;color:#94A3B8;margin-top:0">
    "Configured" only means the API keys are filled in — it does NOT mean
    WhatsApp is actually delivering. Send yourself a real test message and
    check your phone; if the gateway says OK but nothing arrives, your
    session on bulk.akdwk.in has likely disconnected and needs the QR code
    scanned again.</p>
  <form method="post" style="display:flex;gap:8px;flex-wrap:wrap">
    <input type="hidden" name="do" value="test_whatsapp">
    <input name="test_mobile" placeholder="10-digit mobile number" required
           style="flex:1;min-width:180px">
    <button>📤 Send Test</button>
  </form>
  <?php if (isset($waTestResult)): ?>
    <p style="font-size:13px;margin-top:10px;padding:10px;background:#0A0E1A;
              border-radius:6px;word-break:break-word"><?= $waTestResult ?></p>
  <?php endif; ?>
</div>

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
    <h2>➕ Create New User (details sent on WhatsApp — password is NOT sent)</h2>
    <form method="post">
      <input type="hidden" name="do" value="add_user">
      <input name="name" placeholder="Full Name" required>
      <input name="police_station" placeholder="Police Station / Office" required>
      <input name="designation" placeholder="Designation / Post" required>
      <input name="username" placeholder="Username" required>
      <input name="password" placeholder="Password (min 6)" required>
      <input name="mobile" placeholder="WhatsApp Mobile" required>
      <input name="valid_days" type="number" min="0" placeholder="Validity (days, 0=unlimited)" style="width:170px">
      <button>Create & Send WhatsApp</button>
    </form>
  </div>
  <div class="card">
    <h2>👥 All Users</h2>
    <table>
      <tr><th>ID</th><th>Name</th><th>Office</th><th>Designation</th>
          <th>Username</th><th>Mobile</th><th>Status</th>
          <th>⏳ Validity</th><th>Created</th><th>Actions</th></tr>
      <?php foreach ($pdo->query("SELECT * FROM users ORDER BY id DESC") as $u):
          $vExpired = !empty($u['valid_until'])
              && strtotime($u['valid_until']) < time(); ?>
      <tr>
        <td><?= $u['id'] ?></td>
        <td><?= htmlspecialchars($u['name']) ?></td>
        <td><?= htmlspecialchars($u['police_station']) ?></td>
        <td><?= htmlspecialchars($u['designation']) ?></td>
        <td><?= htmlspecialchars($u['username']) ?></td>
        <td><?= htmlspecialchars($u['mobile']) ?></td>
        <td><span class="badge b-<?= $u['status'] ?>"><?= strtoupper($u['status']) ?></span></td>
        <td>
          <?php if (empty($u['valid_until'])): ?>
            <span class="badge b-active">UNLIMITED</span>
          <?php elseif ($vExpired): ?>
            <span class="badge b-disabled">EXPIRED
              <?= date('d-m-Y', strtotime($u['valid_until'])) ?></span>
          <?php else: ?>
            <span class="badge b-pending">till
              <?= date('d-m-Y', strtotime($u['valid_until'])) ?></span>
          <?php endif; ?>
          <form method="post" style="display:inline;white-space:nowrap">
            <input type="hidden" name="do" value="set_validity">
            <input type="hidden" name="uid" value="<?= $u['id'] ?>">
            <input name="days" type="number" min="0" placeholder="days"
                   style="width:60px;padding:5px" title="0 = unlimited">
            <button class="gray" title="Set validity from today (0 = unlimited)">Set</button>
          </form>
        </td>
        <td><?= $u['created_at'] ?></td>
        <td style="white-space:nowrap">
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

<?php elseif ($page === 'reports'):
  $q = trim($_GET['q'] ?? '');
  $from = trim($_GET['from'] ?? '');
  $to = trim($_GET['to'] ?? '');
  $sql = "SELECT r.*, u.username, u.police_station FROM reports r
          JOIN users u ON u.id = r.user_id WHERE 1=1";
  $params = [];
  if ($q !== '') {
      $sql .= " AND (r.case_id LIKE ? OR u.username LIKE ? OR u.police_station LIKE ?)";
      $like = "%$q%";
      $params = array_merge($params, [$like, $like, $like]);
  }
  if ($from !== '') {
      $sql .= " AND date(r.created_at) >= ?";
      $params[] = $from;
  }
  if ($to !== '') {
      $sql .= " AND date(r.created_at) <= ?";
      $params[] = $to;
  }
  $sql .= " ORDER BY r.id DESC LIMIT 300";
  $stmt = $pdo->prepare($sql);
  $stmt->execute($params);
  ?>
  <div class="card">
    <h2>🔍 Search / Filter Reports</h2>
    <form method="get">
      <input type="hidden" name="page" value="reports">
      <input name="q" placeholder="Case ID / Username / Station"
             value="<?= htmlspecialchars($q) ?>">
      <input name="from" type="date" value="<?= htmlspecialchars($from) ?>" title="From date">
      <input name="to" type="date" value="<?= htmlspecialchars($to) ?>" title="To date">
      <button>Search</button>
      <a href="?page=reports" class="gray" style="margin-left:6px">Clear</a>
      &nbsp;|&nbsp;
      <a href="?export=reports_csv">📊 Export CSV</a>
      &nbsp;
      <a href="?export=reports_zip">📦 Download All PDFs (ZIP)</a>
    </form>
  </div>
  <div class="card">
    <h2>📄 Uploaded Case Reports</h2>
    <table>
      <tr><th>Time</th><th>Case ID</th><th>Operator</th><th>Police Station</th>
          <th>👤</th><th>🚗</th><th>📸</th><th>View</th>
          <th>Report Link</th><th>Share</th><th>Actions</th></tr>
      <?php foreach ($stmt as $r):
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
                 style="width:170px;font-size:11px"
                 onclick="this.select();document.execCommand('copy');
                          this.style.borderColor='#10B981';"
                 title="Click to copy link">
        </td>
        <td>
          <form method="post" style="display:flex;gap:4px">
            <input type="hidden" name="do" value="share_report">
            <input type="hidden" name="rid" value="<?= $r['id'] ?>">
            <input name="share_username" placeholder="username" style="width:80px">
            <button class="gray" title="Also show this report in that user's My Reports">Share</button>
          </form>
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

<?php elseif ($page === 'stats'): ?>
  <div class="card">
    <h2>🏢 Station-wise Reports</h2>
    <table>
      <tr><th>Police Station</th><th>Reports</th><th>👤 Persons</th><th>🚗 Vehicles</th></tr>
      <?php foreach ($pdo->query(
          "SELECT u.police_station, COUNT(*) AS cnt, SUM(r.persons) AS p,
                  SUM(r.vehicles) AS v
           FROM reports r JOIN users u ON u.id = r.user_id
           GROUP BY u.police_station ORDER BY cnt DESC") as $s): ?>
      <tr>
        <td><?= htmlspecialchars($s['police_station']) ?></td>
        <td><?= $s['cnt'] ?></td>
        <td><?= (int)$s['p'] ?></td>
        <td><?= (int)$s['v'] ?></td>
      </tr>
      <?php endforeach; ?>
    </table>
  </div>
  <div class="card">
    <h2>📅 Monthly Reports</h2>
    <table>
      <tr><th>Month</th><th>Reports</th><th>👤 Persons</th><th>🚗 Vehicles</th></tr>
      <?php foreach ($pdo->query(
          "SELECT strftime('%Y-%m', created_at) AS ym, COUNT(*) AS cnt,
                  SUM(persons) AS p, SUM(vehicles) AS v
           FROM reports GROUP BY ym ORDER BY ym DESC LIMIT 24") as $s): ?>
      <tr>
        <td><?= $s['ym'] ?></td>
        <td><?= $s['cnt'] ?></td>
        <td><?= (int)$s['p'] ?></td>
        <td><?= (int)$s['v'] ?></td>
      </tr>
      <?php endforeach; ?>
    </table>
  </div>

<?php elseif ($page === 'audit'): ?>
  <div class="card">
    <h2>🧾 Admin Audit Log</h2>
    <table>
      <tr><th>Time</th><th>Action</th><th>Target</th><th>Detail</th></tr>
      <?php foreach ($pdo->query(
          "SELECT * FROM admin_audit_log ORDER BY id DESC LIMIT 300") as $a): ?>
      <tr>
        <td><?= $a['created_at'] ?></td>
        <td><?= htmlspecialchars($a['action']) ?></td>
        <td><?= htmlspecialchars($a['target']) ?></td>
        <td><?= htmlspecialchars($a['detail']) ?></td>
      </tr>
      <?php endforeach; ?>
    </table>
  </div>
<?php endif; ?>
</div>
<?php endif; ?>
</body>
</html>
