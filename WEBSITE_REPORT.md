# 🦚 Krishna Intelligence — Website નો સંપૂર્ણ રિપોર્ટ

**Version:** v15 | **તારીખ:** 08-07-2026
**ટેક્નોલોજી:** PHP 8+ / SQLite Database / WhatsApp API (bulk.akdwk.in)

આ રિપોર્ટમાં website (web panel) શું શું કરે છે, કેવી રીતે કરે છે, અને શું **નથી** કરતી — એ બધું વિગતવાર લખેલું છે.

---

## 1️⃣ Website શેની બનેલી છે — ફાઈલોનું માળખું

```
server/
├── config.php        → બધા settings (URL, admin password, WhatsApp API key, validity દિવસ)
├── db.php            → Database બનાવે/જૂનું database આપોઆપ update કરે
├── helpers.php       → WhatsApp મોકલવાનું, OTP બનાવવા/ચકાસવાનું engine
├── api.php           → Software સાથે વાત કરતું API (login, verify, report upload, forgot password)
├── register.php      → જાહેર registration page (WhatsApp OTP સાથે)
├── view.php          → Report જોવાનું page (secret link થી જ ખૂલે)
├── index.php         → સીધા admin panel પર લઈ જાય
├── admin/index.php   → આખું Admin Panel
└── data/             → Database + બધા reports (બહારથી કોઈ ખોલી ન શકે — .htaccess થી blocked)
    └── reports/      → Upload થયેલા PDF/JSON reports
```

---

## 2️⃣ Website શું શું કામ કરે છે ✅

### 🔐 A. Software નું Login System (api.php)

| કામ | વિગત |
|---|---|
| Login | Software ખૂલે ત્યારે username/password અહીં ચકાસાય છે. સાચું હોય તો જ software ચાલે. |
| 7-દિવસ session | Login થાય એટલે 7 દિવસનો secret token મળે. 7 દિવસ પછી token server પર જ expire થાય — PC પર તારીખ બદલીને છેતરી ન શકાય. |
| PC ની માહિતી | દરેક login વખતે **PC નું નામ, Operating System, PC user, IP address** server પર નોંધાય છે. |
| ખોટા પ્રયાસ block | એક username પર 10 મિનિટમાં 8 ખોટા password નાખો તો 10 મિનિટ માટે block. |
| Validity check | User ની validity પતી ગઈ હોય તો login/verify/upload — ત્રણેય જગ્યાએ block ("Account validity expired"). |
| Account status | Pending user ને "admin approval બાકી છે", disabled user ને "account disabled" — સ્પષ્ટ message. |
| Disable = તરત બહાર | Admin કોઈને disable કરે એટલે એના ચાલુ sessions પણ તરત કપાઈ જાય. |

### 📄 B. Report Upload + WhatsApp (api.php)

| કામ | વિગત |
|---|---|
| Report સ્વીકારે | Software scan પતાવે એટલે PDF + JSON report અહીં આપોઆપ આવે. **Video ક્યારેય upload થતો નથી** — server video સ્વીકારતું જ નથી. |
| Size limit | PDF વધુમાં વધુ 50 MB, JSON 20 MB. |
| Secret link | દરેક report ને 48-અક્ષરનો secret token મળે. Link: `view.php?t=XXXX...` — આ link વગર report કોઈ ખોલી ન શકે. |
| WhatsApp message | Upload થતાં જ operator ના registered WhatsApp પર message જાય: Case ID, પોલીસ સ્ટેશન, Persons/Vehicles/Total ના આંકડા, અને **report ની link** (PDF media attach સાથે). |
| Case ની વિગત સચવાય | કયા user એ, કયા case નો, ક્યારે, કેટલા evidence સાથે report મૂક્યો — બધું database માં. |

### 👥 C. Admin Panel (admin/index.php)

| કામ | વિગત |
|---|---|
| Admin login | Username + password (config.php માં સેટ થાય). |
| Dashboard આંકડા | કુલ Users, કુલ Reports, કુલ Logins — ઉપર મોટા આંકડામાં. |
| User બનાવવો | નામ, ઓફિસ/પોલીસ સ્ટેશન, **હોદ્દો**, username, password, WhatsApp mobile, validity (દિવસ) — બધું એક form માંથી. બનતાં જ user ને WhatsApp પર બધી વિગત જાય (**password સિવાય**). |
| Approve / Disable | Register થયેલા pending users ને approve કરવા, કોઈને પણ ગમે ત્યારે disable કરવા. Approve થાય એટલે WhatsApp પર "account ACTIVE" message જાય. |
| Password Reset | નવો random password બને → **admin ને screen પર દેખાય** (WhatsApp પર ન જાય), user ને ફક્ત "password reset થયો છે" ની જાણ જાય. જૂના sessions કપાઈ જાય. |
| ⏳ Validity control | દરેક user સામે badge: 🟢 UNLIMITED / 🟡 till તારીખ / 🔴 EXPIRED. બાજુમાં જ દિવસ નાખીને "Set" — આજથી એટલા દિવસ. 0 = unlimited. બદલાય એટલે user ને WhatsApp પર જાણ. |
| 🖥 Login History | છેલ્લા 300 logins: સમય, username, **PC નું નામ, OS, PC user, IP**, સફળ/નિષ્ફળ — બધું table માં. |
| 📄 Reports page | બધા reports: સમય, Case ID, operator, પોલીસ સ્ટેશન, આંકડા, PDF/JSON ખોલવાની link, **copy કરવા માટે આખી link** (click = copy), **📲 Send Again** button (WhatsApp ફરી મોકલે), Delete button. |

### 📝 D. Registration Page (register.php)

| કામ | વિગત |
|---|---|
| જાહેર form | નામ, ઓફિસ/પોલીસ સ્ટેશન, હોદ્દો, username, password, WhatsApp mobile — બધું ફરજિયાત. Software ના login screen પરથી પણ સીધું ખૂલે. |
| WhatsApp OTP | Form ભરો એટલે 6-આંકડાનો OTP WhatsApp પર જાય (5 મિનિટ માટે માન્ય). સાચો OTP = registration પાકું. |
| OTP limit | એક mobile પર 10 મિનિટમાં વધુમાં વધુ 3 OTP — spam અટકે. |
| Confirmation | Registration થતાં જ WhatsApp પર આખી વિગત જાય: નામ, ઓફિસ, હોદ્દો, username, mobile, **Server URL** — **password ક્યારેય નહીં**. |
| Admin approval | નવો user "pending" રહે — admin approve કરે પછી જ login થઈ શકે. કોઈ અજાણ્યો માણસ જાતે active ન થઈ શકે. |

### 🔑 E. Forgot Password (api.php + software)

| કામ | વિગત |
|---|---|
| OTP થી reset | Software માં username નાખો → registered WhatsApp પર OTP જાય (number છુપાયેલો બતાવે: ******9999) → સાચો OTP + નવો password = બદલાઈ ગયું. |
| Security | Reset થતાં જ જૂના બધા sessions કપાય, અને "password બદલાયો — તમે ન કર્યું હોય તો admin ને કહો" નો WhatsApp જાય. |

### 🛡 F. Security — શું સાચવેલું છે

1. **Password hash થઈને સચવાય** (bcrypt) — database ખૂલી જાય તો પણ password કોઈ વાંચી ન શકે.
2. **બધા database queries prepared statements થી** — SQL injection શક્ય નથી.
3. **data/ folder .htaccess થી blocked** — database file કે reports સીધા URL થી ડાઉનલોડ ન થાય; report ફક્ત secret token વાળી link થી જ ખૂલે.
4. **Random tokens** (`random_bytes`) — session 64 hex, report link 48 hex — ધારી ન શકાય.
5. **Login rate-limit + OTP rate-limit** — brute force અઘરું.
6. **Expired/disabled user દરેક રસ્તે block** — login, verify, upload ત્રણેય જગ્યાએ ચકાસણી.
7. **WhatsApp પર ક્યારેય password નહીં** — કોઈ પણ message માં નહીં.

---

## 3️⃣ Website શું કામ **નથી** કરતી ❌ (મર્યાદાઓ — સાચું ચિત્ર)

### Operators માટે
1. **Operator website પર login નથી કરી શકતો** — website પર ફક્ત admin નું login છે. Operator ને પોતાના reports જોવા હોય તો WhatsApp ની links થી જ; "મારા બધા reports" એવું કોઈ page operator માટે નથી.
2. **Report edit/ફેરફાર નથી થતો** — જે upload થયું એ final. ભૂલ હોય તો ફરી scan કરીને નવો report જ મૂકવો પડે.
3. **જૂના reports search નથી થતા** — admin panel માં છેલ્લા 300 reports દેખાય છે, પણ Case ID/તારીખ/user થી શોધવાનું (search/filter) નથી.

### Admin માટે
4. **એક જ admin છે** — અલગ અલગ admin accounts, roles (કોણ શું કરી શકે) એવું નથી. Admin password config.php માં સાદા લખાણમાં છે — file ની સુરક્ષા hosting પર આધારિત.
5. **User કાયમ delete નથી થતો** — ફક્ત disable થાય (record કાયદેસર રીતે સચવાય એ સારું પણ છે). Reports delete થાય છે.
6. **Admin ના કામનો log નથી** — કયા admin action ક્યારે થયા (કોને approve કર્યો, કોની validity બદલી) એની અલગ નોંધ નથી રહેતી.
7. **Admin login પર 2FA/OTP નથી** — ફક્ત username+password.

### Report links બાબતે
8. **Report ની link કાયમ ચાલે છે** — expiry નથી. જેની પાસે link હોય (WhatsApp forward થાય તો પણ) એ report ખોલી શકે. Link ધારી શકાય એવી નથી, પણ **share થઈ જાય તો ખૂલે** — એ ડિઝાઈન જ એવી છે (WhatsApp થી જોવા માટે). જરૂર પડે તો admin panel માંથી report delete કરવો.
9. **Reports encrypt થઈને નથી સચવાતા** — server પર સામાન્ય files તરીકે રહે (folder blocked છે, પણ hosting hack થાય તો વંચાય).

### Technical મર્યાદાઓ
10. **WhatsApp ત્રીજા પક્ષ પર આધારિત** — bulk.akdwk.in બંધ હોય/API key ખોટી હોય તો messages ન જાય (registration OTP પણ ન જાય = registration અટકે). Website message ફરી આપોઆપ મોકલવાનો પ્રયાસ નથી કરતી — Reports માં "Send Again" જાતે દબાવવું પડે.
11. **SQLite database છે** — નાની/મધ્યમ ટીમ (સેંકડો users, હજારો reports) માટે perfect; પણ એકસાથે હજારો લોકો વાપરે એવા મોટા સ્કેલ માટે MySQL જોઈએ.
12. **Backup આપોઆપ નથી થતું** — `data/` folder નો backup hosting પરથી જાતે/schedule કરીને લેવો પડે.
13. **Email નથી** — બધું WhatsApp થી જ; email notification નથી.
14. **HTTPS ફરજિયાત code માં નથી** — hosting પર SSL હોવું જ જોઈએ (વગર HTTPS એ password રસ્તામાં વંચાઈ શકે). cPanel માં ફ્રી SSL (Let's Encrypt) ચાલુ કરી દેવું.
15. **Admin forms માં CSRF token નથી** — admin login થયેલો હોય ત્યારે કોઈ કપટી page એના browser થી form submit કરાવી શકે એ સૈદ્ધાંતિક જોખમ છે (વ્યવહારમાં ઓછું, પણ છે).
16. **CCTV live monitoring નથી** — આ website CCTV સાથે સીધી જોડાતી નથી; એ ફક્ત software ના reports, users અને logins સંભાળે છે. Video નું બધું કામ PC પરના software માં જ થાય છે.
17. **Report ના evidence ફોટા website પર નથી આવતા** — PDF ની અંદર જે ફોટા છે એ જ; અલગ અલગ image files server પર upload નથી થતી. (Video ની જેમ ફોટા પણ PC પર જ રહે છે.)

---

## 4️⃣ Database માં શું શું સચવાય છે

| Table | શું સચવાય |
|---|---|
| **users** | username, password (hash), નામ, ઓફિસ, હોદ્દો, mobile, status (pending/active/disabled), validity તારીખ, બન્યાની તારીખ |
| **sessions** | કયો user, secret token, PC name/OS/user/IP, ક્યારે બન્યું, ક્યારે expire, છેલ્લે ક્યારે વપરાયું |
| **login_logs** | દરેક login પ્રયાસ — સફળ કે નિષ્ફળ, PC ની આખી માહિતી, IP, સમય |
| **reports** | કયો user, Case ID, PDF/JSON file, secret view token, Persons/Vehicles/Total, સમય |
| **otps** | mobile, code, હેતુ (register/forgot), expiry, વપરાયો કે નહીં |

---

## 5️⃣ આખો ફ્લો — એક નજરમાં

```
[Operator]                     [Website]                      [Admin]
    │                              │                              │
    ├─ Register (OTP) ──────────►  pending user  ◄── Approve ─────┤
    │  ◄─ WhatsApp: વિગત+URL       │      ◄─ WhatsApp: ACTIVE     │
    │                              │                              │
    ├─ Software Login ──────────►  ચકાસણી + PC log ──────────────►│ (Login History માં દેખાય)
    │  ◄─ 7-દિવસ token             │                              │
    │                              │                              │
    ├─ Scan પૂરો → Report ──────►  સાચવે + secret link બનાવે      │
    │  ◄─ WhatsApp: link           │  ────────────────────────────►│ (Reports માં link + Send Again)
    │                              │                              │
    ├─ Password ભૂલ્યા → OTP ───►  reset + જૂના session cut       │
    │                              │      ◄── Validity Set ───────┤
    │  ◄─ WhatsApp: validity       │                              │
```

---

## 6️⃣ ભવિષ્યમાં ઉમેરી શકાય એવું (સૂચનો)

1. Operator માટે website login — "મારા reports" page
2. Reports માં search/filter (Case ID, તારીખ, user પ્રમાણે)
3. Report link ની expiry (દા.ત. 30 દિવસ) અથવા link પર OTP
4. એકથી વધુ admin + admin actions નો log
5. આપોઆપ backup (દરરોજ data/ folder નું zip)
6. Admin login પર OTP (2FA)
7. WhatsApp fail થાય તો આપોઆપ ફરી પ્રયાસ (retry queue)
8. Monthly summary report (કયા સ્ટેશને કેટલા case scan થયા)

---

*આ રિપોર્ટ v15 (branch: claude/forensic-video-intelligence-df037w) ના code પ્રમાણે બનાવેલો છે.*
