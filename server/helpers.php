<?php
/** Krishna Intelligence — shared helpers. */

require_once __DIR__ . '/db.php';

function cfg(): array
{
    static $cfg = null;
    if ($cfg === null) {
        $cfg = require __DIR__ . '/config.php';
    }
    return $cfg;
}

function json_out(array $data): void
{
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}

function now(): string
{
    return date('Y-m-d H:i:s');
}

function client_ip(): string
{
    return $_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? '';
}

function rand_token(int $bytes = 32): string
{
    return bin2hex(random_bytes($bytes));
}

/** Normalise an Indian mobile number to 91XXXXXXXXXX. */
function normalize_mobile(string $mobile): string
{
    $digits = preg_replace('/\D/', '', $mobile);
    if (strlen($digits) === 10) {
        $digits = '91' . $digits;
    }
    return $digits;
}

/**
 * Send a WhatsApp message through the configured bulk.akdwk.in gateway.
 * $mediaUrl (optional) attaches a file/image link.
 */
function wa_send(string $mobile, string $message, string $mediaUrl = ''): bool
{
    $c = cfg();
    if (strpos($c['wa_session_id'], 'PASTE_') === 0
        || strpos($c['wa_api_key'], 'PASTE_') === 0) {
        error_log('Krishna: WhatsApp API not configured — message skipped.');
        return false;
    }
    $params = [
        'number' => normalize_mobile($mobile),
        'message' => $message,
        'session_id' => $c['wa_session_id'],
        'api_key' => $c['wa_api_key'],
    ];
    if ($mediaUrl !== '') {
        $params['media_url'] = $mediaUrl;
    }
    $url = $c['wa_api_url'] . '?' . http_build_query($params);

    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 20,
        CURLOPT_SSL_VERIFYPEER => true,
    ]);
    $out = curl_exec($ch);
    $err = curl_error($ch);
    curl_close($ch);
    if ($out === false) {
        error_log("Krishna: WhatsApp send failed: $err");
        return false;
    }
    return true;
}

/** Create + send an OTP for a mobile number. Returns true when sent. */
function otp_send(string $mobile, string $purpose): bool
{
    $pdo = db();
    // Basic rate-limit: max 3 OTPs per mobile per 10 minutes.
    $q = $pdo->prepare("SELECT COUNT(*) FROM otps
                        WHERE mobile = ? AND created_at > datetime('now', '-10 minutes')");
    $q->execute([normalize_mobile($mobile)]);
    if ((int)$q->fetchColumn() >= 3) {
        return false;
    }
    $code = strval(random_int(100000, 999999));
    $mins = (int)cfg()['otp_minutes'];
    $ins = $pdo->prepare("INSERT INTO otps (mobile, code, purpose, expires_at, created_at)
                          VALUES (?, ?, ?, datetime('now', '+{$mins} minutes'), datetime('now'))");
    $ins->execute([normalize_mobile($mobile), $code, $purpose]);
    return wa_send($mobile,
        "Krishna Intelligence OTP: $code\nValid for {$mins} minutes. Do not share.");
}

/** Verify an OTP; marks it used on success. */
function otp_verify(string $mobile, string $code, string $purpose): bool
{
    $pdo = db();
    $q = $pdo->prepare("SELECT id FROM otps
                        WHERE mobile = ? AND code = ? AND purpose = ?
                          AND used = 0 AND expires_at > datetime('now')
                        ORDER BY id DESC LIMIT 1");
    $q->execute([normalize_mobile($mobile), trim($code), $purpose]);
    $id = $q->fetchColumn();
    if (!$id) {
        return false;
    }
    $pdo->prepare("UPDATE otps SET used = 1 WHERE id = ?")->execute([$id]);
    return true;
}
