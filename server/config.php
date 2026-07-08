<?php
/**
 * Krishna Intelligence — Server Configuration
 * LCB Technical Cell, Devbhoomi Dwarka
 *
 * !!! IMPORTANT !!!
 * 1) Fill in your WhatsApp API details below (from bulk.akdwk.in).
 * 2) CHANGE the admin password before going live.
 * 3) Never commit this file with real keys to a public repository.
 */
return [
    // Public base URL of this server folder, WITHOUT trailing slash.
    // Example: 'https://yourdomain.in/krishna'
    'base_url' => 'https://CHANGE-ME.example.in/krishna',

    // Admin panel login
    'admin_user' => 'admin',
    'admin_password' => 'ChangeMe@123',   // <-- CHANGE THIS!

    // WhatsApp API (bulk.akdwk.in) — paste YOUR values here.
    'wa_api_url' => 'https://bulk.akdwk.in/api.php',
    'wa_session_id' => 'PASTE_YOUR_SESSION_ID_HERE',
    'wa_api_key' => 'PASTE_YOUR_API_KEY_HERE',

    // Software session validity (days) — login asked again after this.
    'token_days' => 7,

    // OTP validity (minutes) for web registration.
    'otp_minutes' => 5,
];
