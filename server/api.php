<?php
/**
 * Krishna Intelligence — Desktop app API.
 * Actions: login | verify | upload_report | forgot_request | forgot_reset
 */
require_once __DIR__ . '/helpers.php';

$action = $_GET['action'] ?? '';
$pdo = db();

// ---------------------------------------------------------------- login ----
if ($action === 'login') {
    $username = trim($_POST['username'] ?? '');
    $password = $_POST['password'] ?? '';
    $device = [
        'device_name' => substr(trim($_POST['device_name'] ?? ''), 0, 100),
        'device_os' => substr(trim($_POST['device_os'] ?? ''), 0, 100),
        'device_user' => substr(trim($_POST['device_user'] ?? ''), 0, 100),
    ];
    if ($username === '' || $password === '') {
        json_out(['ok' => false, 'error' => 'Username and password required.']);
    }

    // Rate-limit: max 8 failed attempts per username in 10 minutes.
    $q = $pdo->prepare("SELECT COUNT(*) FROM login_logs
                        WHERE username = ? AND status = 'failed'
                          AND created_at > datetime('now', '-10 minutes')");
    $q->execute([$username]);
    if ((int)$q->fetchColumn() >= 8) {
        json_out(['ok' => false, 'error' => 'Too many attempts. Try again in 10 minutes.']);
    }

    $q = $pdo->prepare("SELECT * FROM users WHERE username = ?");
    $q->execute([$username]);
    $user = $q->fetch(PDO::FETCH_ASSOC);

    $expired = $user && !empty($user['valid_until'])
        && strtotime($user['valid_until']) < time();
    $ok = $user && password_verify($password, $user['password_hash'])
        && $user['status'] === 'active' && !$expired;

    // Every attempt is logged with the PC's basic information.
    $log = $pdo->prepare("INSERT INTO login_logs
        (user_id, username, device_name, device_os, device_user, ip, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)");
    $log->execute([$user['id'] ?? null, $username, $device['device_name'],
        $device['device_os'], $device['device_user'], client_ip(),
        $ok ? 'success' : 'failed', now()]);

    if (!$user || !password_verify($password, $user['password_hash'])) {
        json_out(['ok' => false, 'error' => 'Invalid username or password.']);
    }
    if ($user['status'] === 'pending') {
        json_out(['ok' => false, 'error' => 'Account awaiting admin approval.']);
    }
    if ($user['status'] !== 'active') {
        json_out(['ok' => false, 'error' => 'Account is disabled. Contact admin.']);
    }
    if ($expired) {
        json_out(['ok' => false,
            'error' => 'Account validity expired — contact admin to extend.']);
    }

    $days = (int)cfg()['token_days'];
    $token = rand_token();
    $ins = $pdo->prepare("INSERT INTO sessions
        (user_id, token, device_name, device_os, device_user, ip,
         created_at, expires_at, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', '+{$days} days'), ?)");
    $ins->execute([$user['id'], $token, $device['device_name'],
        $device['device_os'], $device['device_user'], client_ip(),
        now(), now()]);

    json_out([
        'ok' => true,
        'token' => $token,
        'valid_days' => $days,
        'profile' => [
            'username' => $user['username'],
            'name' => $user['name'],
            'police_station' => $user['police_station'],
            'designation' => $user['designation'],
            'mobile' => $user['mobile'],
            'valid_until' => $user['valid_until'],
        ],
    ]);
}

// --------------------------------------------------------------- verify ----
if ($action === 'verify') {
    $token = $_POST['token'] ?? '';
    if ($token === '') {
        json_out(['ok' => false, 'error' => 'Token required.']);
    }
    $q = $pdo->prepare(
        "SELECT s.*, u.username, u.name, u.police_station, u.designation,
                u.mobile, u.status, u.valid_until
         FROM sessions s JOIN users u ON u.id = s.user_id
         WHERE s.token = ? AND s.expires_at > datetime('now')");
    $q->execute([$token]);
    $row = $q->fetch(PDO::FETCH_ASSOC);
    if (!$row || $row['status'] !== 'active') {
        json_out(['ok' => false, 'error' => 'Session expired or account disabled.']);
    }
    if (!empty($row['valid_until']) && strtotime($row['valid_until']) < time()) {
        json_out(['ok' => false,
            'error' => 'Account validity expired — contact admin to extend.']);
    }
    $pdo->prepare("UPDATE sessions SET last_seen = ? WHERE id = ?")
        ->execute([now(), $row['id']]);
    json_out([
        'ok' => true,
        'profile' => [
            'username' => $row['username'],
            'name' => $row['name'],
            'police_station' => $row['police_station'],
            'designation' => $row['designation'],
            'mobile' => $row['mobile'],
            'valid_until' => $row['valid_until'],
        ],
    ]);
}

// -------------------------------------------------------- upload_report ----
if ($action === 'upload_report') {
    $token = $_POST['token'] ?? '';
    $q = $pdo->prepare(
        "SELECT s.user_id, u.mobile, u.police_station, u.status, u.valid_until
         FROM sessions s JOIN users u ON u.id = s.user_id
         WHERE s.token = ? AND s.expires_at > datetime('now')");
    $q->execute([$token]);
    $sess = $q->fetch(PDO::FETCH_ASSOC);
    if (!$sess || $sess['status'] !== 'active'
        || (!empty($sess['valid_until'])
            && strtotime($sess['valid_until']) < time())) {
        json_out(['ok' => false, 'error' => 'Not authorised.']);
    }

    $caseId = substr(preg_replace('/[^A-Za-z0-9 _-]/', '_',
        trim($_POST['case_id'] ?? 'CASE')), 0, 80);
    $persons = (int)($_POST['persons'] ?? 0);
    $vehicles = (int)($_POST['vehicles'] ?? 0);
    $total = (int)($_POST['total'] ?? 0);

    $dir = __DIR__ . '/data/reports';
    if (!is_dir($dir)) {
        mkdir($dir, 0775, true);
    }

    // The client may pre-generate its own token so the QR code it already
    // baked into the PDF matches the final view URL. Use it only if it
    // looks right and is not already taken; otherwise fall back to a
    // server-generated one (older client versions, or a collision).
    $clientToken = preg_replace('/[^a-f0-9]/', '', $_POST['client_token'] ?? '');
    $viewToken = null;
    if (strlen($clientToken) === 48) {
        $chk = $pdo->prepare("SELECT id FROM reports WHERE view_token = ?");
        $chk->execute([$clientToken]);
        if (!$chk->fetch()) {
            $viewToken = $clientToken;
        }
    }
    if ($viewToken === null) {
        $viewToken = rand_token(24);
    }
    $pdfFile = null;
    $jsonFile = null;

    // Accept ONLY PDF / JSON report files — never videos.
    if (!empty($_FILES['report_pdf']) && $_FILES['report_pdf']['error'] === UPLOAD_ERR_OK) {
        if ($_FILES['report_pdf']['size'] > 50 * 1024 * 1024) {
            json_out(['ok' => false, 'error' => 'PDF too large (max 50 MB).']);
        }
        $pdfFile = $viewToken . '.pdf';
        move_uploaded_file($_FILES['report_pdf']['tmp_name'], "$dir/$pdfFile");
    }
    if (!empty($_FILES['report_json']) && $_FILES['report_json']['error'] === UPLOAD_ERR_OK) {
        if ($_FILES['report_json']['size'] > 20 * 1024 * 1024) {
            json_out(['ok' => false, 'error' => 'JSON too large (max 20 MB).']);
        }
        $jsonFile = $viewToken . '.json';
        move_uploaded_file($_FILES['report_json']['tmp_name'], "$dir/$jsonFile");
    }
    if (!$pdfFile && !$jsonFile) {
        json_out(['ok' => false, 'error' => 'No report file received.']);
    }

    $ins = $pdo->prepare("INSERT INTO reports
        (user_id, case_id, pdf_file, json_file, view_token,
         persons, vehicles, total, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)");
    $ins->execute([$sess['user_id'], $caseId, $pdfFile, $jsonFile,
        $viewToken, $persons, $vehicles, $total, now()]);

    $viewUrl = cfg()['base_url'] . '/view.php?t=' . $viewToken;

    // WhatsApp message with the report link (media attach when PDF exists).
    $msg = "🦚 Krishna Intelligence\n"
         . "📋 Case: $caseId\n"
         . "🏢 " . $sess['police_station'] . "\n"
         . "👤 Persons: $persons | 🚗 Vehicles: $vehicles | 📸 Total: $total\n"
         . "🔗 View report: $viewUrl";
    wa_send($sess['mobile'], $msg, $pdfFile ? $viewUrl : '');

    json_out(['ok' => true, 'view_url' => $viewUrl]);
}

// ------------------------------------------------------- forgot_request ----
if ($action === 'forgot_request') {
    $username = trim($_POST['username'] ?? '');
    if ($username === '') {
        json_out(['ok' => false, 'error' => 'Username required.']);
    }
    $q = $pdo->prepare("SELECT * FROM users WHERE username = ?");
    $q->execute([$username]);
    $user = $q->fetch(PDO::FETCH_ASSOC);
    if (!$user || $user['status'] !== 'active') {
        json_out(['ok' => false, 'error' => 'User not found or not active.']);
    }
    $sent = otp_send($user['mobile'], 'forgot');
    if ($sent === 'rate_limit') {
        json_out(['ok' => false,
            'error' => 'OTP limit reached — try again after 10 minutes.']);
    }
    if ($sent !== 'ok') {
        json_out(['ok' => false,
            'error' => 'Could not send WhatsApp OTP — contact admin.']);
    }
    json_out(['ok' => true,
        'mobile_hint' => '******' . substr($user['mobile'], -4)]);
}

// --------------------------------------------------------- forgot_reset ----
if ($action === 'forgot_reset') {
    $username = trim($_POST['username'] ?? '');
    $otp = trim($_POST['otp'] ?? '');
    $newPass = $_POST['new_password'] ?? '';
    if ($username === '' || $otp === '' || strlen($newPass) < 6) {
        json_out(['ok' => false,
            'error' => 'OTP and a new password (min 6 chars) required.']);
    }
    $q = $pdo->prepare("SELECT * FROM users WHERE username = ?");
    $q->execute([$username]);
    $user = $q->fetch(PDO::FETCH_ASSOC);
    if (!$user || $user['status'] !== 'active') {
        json_out(['ok' => false, 'error' => 'User not found or not active.']);
    }
    if (!otp_verify($user['mobile'], $otp, 'forgot')) {
        json_out(['ok' => false, 'error' => 'Wrong or expired OTP.']);
    }
    $pdo->prepare("UPDATE users SET password_hash = ? WHERE id = ?")
        ->execute([password_hash($newPass, PASSWORD_DEFAULT), $user['id']]);
    // Old software sessions become invalid after a password reset.
    $pdo->prepare("DELETE FROM sessions WHERE user_id = ?")
        ->execute([$user['id']]);
    wa_send($user['mobile'],
        "🦚 Krishna Intelligence\n🔑 Password changed for '{$user['username']}'.\n"
        . "If this was not you, contact admin immediately.");
    json_out(['ok' => true]);
}

json_out(['ok' => false, 'error' => 'Unknown action.']);
