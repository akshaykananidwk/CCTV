<?php
/**
 * Krishna Intelligence — public report viewer.
 * Reports are served ONLY through their secret view token
 * (the link that arrives on WhatsApp).
 */
require_once __DIR__ . '/helpers.php';

$token = preg_replace('/[^a-f0-9]/', '', $_GET['t'] ?? '');
if ($token === '') {
    http_response_code(404);
    exit('Report not found.');
}

$q = db()->prepare("SELECT * FROM reports WHERE view_token = ?");
$q->execute([$token]);
$report = $q->fetch(PDO::FETCH_ASSOC);
if (!$report) {
    http_response_code(404);
    exit('Report not found.');
}

$dir = __DIR__ . '/data/reports';
$wantJson = isset($_GET['f']) && $_GET['f'] === 'json';

$file = $wantJson ? $report['json_file'] : ($report['pdf_file'] ?: $report['json_file']);
if (!$file || !is_file("$dir/$file")) {
    http_response_code(404);
    exit('Report file missing.');
}

$isPdf = str_ends_with($file, '.pdf');
header('Content-Type: ' . ($isPdf ? 'application/pdf' : 'application/json'));
header('Content-Disposition: inline; filename="'
    . $report['case_id'] . ($isPdf ? '_report.pdf' : '_report.json') . '"');
header('Content-Length: ' . filesize("$dir/$file"));
readfile("$dir/$file");
