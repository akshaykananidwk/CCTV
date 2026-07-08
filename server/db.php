<?php
/** Krishna Intelligence — SQLite database bootstrap. */

function db(): PDO
{
    static $pdo = null;
    if ($pdo !== null) {
        return $pdo;
    }
    $dir = __DIR__ . '/data';
    if (!is_dir($dir)) {
        mkdir($dir, 0775, true);
    }
    $pdo = new PDO('sqlite:' . $dir . '/krishna.db');
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $pdo->exec('PRAGMA journal_mode = WAL');

    $pdo->exec("CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        name TEXT NOT NULL,
        police_station TEXT NOT NULL,
        mobile TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',   -- pending|active|disabled
        created_at TEXT NOT NULL
    )");

    $pdo->exec("CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        device_name TEXT, device_os TEXT, device_user TEXT, ip TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        last_seen TEXT
    )");

    $pdo->exec("CREATE TABLE IF NOT EXISTS login_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        device_name TEXT, device_os TEXT, device_user TEXT, ip TEXT,
        status TEXT NOT NULL,                      -- success|failed
        created_at TEXT NOT NULL
    )");

    $pdo->exec("CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        case_id TEXT NOT NULL,
        pdf_file TEXT, json_file TEXT,
        view_token TEXT UNIQUE NOT NULL,
        persons INTEGER DEFAULT 0,
        vehicles INTEGER DEFAULT 0,
        total INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )");

    $pdo->exec("CREATE TABLE IF NOT EXISTS otps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mobile TEXT NOT NULL,
        code TEXT NOT NULL,
        purpose TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )");

    return $pdo;
}
