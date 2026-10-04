# CHANGELOG.md — VoiceHire

All notable changes to the VoiceHire project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Push notifications via Firebase Cloud Messaging (FCM)
- In-app messaging between customers and workers
- Razorpay / UPI payment gateway integration
- AI-based worker recommendation engine
- Offline mode using Service Workers
- Aadhaar-based ID verification API
- Admin analytics dashboard

---

## [1.2.0] — 2026-10

### Added
- **Booking System** — Full time-slot-based scheduling (5 slots/day)
- **QR Code Check-in** — HMAC-SHA256 signed QR tokens for booking verification
- **Worker Earnings Dashboard** — Today's and monthly earnings, last 2 jobs
- **Data Export** — Workers can download their profile + booking history as CSV
- **Worker Stats API** — `GET /api/worker/stats` with earnings calculations
- **Booking Accept/Decline** — Workers can accept or decline Pending bookings
- **Booking Cancel** — Customers and workers can cancel non-completed bookings
- **Live Worker Tracking** — Real-time GPS tracking via `GET /api/jobs/<id>/track`
- **Voice Resume** — Workers can save transcribed voice text (max 1000 chars)
- **Booking Detail Page** — QR code display with status polling

### Changed
- Worker dashboard redesigned with earnings stats card
- `try_select()` helper added for resilient `profile_pic` column queries
- Worker discovery now sorted: available → rating desc → review count desc
- Job completion tokens expire after 48 hours (previously no expiry)

### Fixed
- Double-booking race condition resolved with `UNIQUE INDEX uq_bookings_slot`
- QR token comparison now uses `hmac.compare_digest()` (timing-attack safe)
- Profile edit no longer crashes when `profile_pic` column is missing in DB

---

## [1.1.0] — 2026-09

### Added
- **Job Board System** — Customers post job requests, workers accept them
- **Urgent Jobs** — `is_urgent` flag surfaces urgent requests at top
- **Job Completion via QR** — `GET /complete-job/<token>` route
- **Worker Rating System** — `POST /api/workers/<id>/rate` with 1-5 stars + review text
- **Duplicate Review Prevention** — One review per job enforced
- **Live Location Sharing** — Workers share/stop GPS via dedicated API endpoints
- **Location Tracking for Jobs** — Customers track accepted worker's live location
- **Customer Job History** — `GET /api/jobs/customer` with worker enrichment
- **Profile Picture Upload** — Both users and workers can upload profile photos

### Changed
- Authentication API unified: single `POST /api/auth/login` handles both roles
- Session now stores `phone` for users (used in job posting)

### Fixed
- Worker signup no longer fails silently when `profile_pic` column doesn't exist

---

## [1.0.0] — 2026-08

### Added
- **Initial Release**
- **Dual-role Authentication** — Separate registration/login for customers and workers
- **Worker Registration** — Voice note, video, ID proof, GPS coordinates, price
- **Worker Discovery** — Filter by service type and location
- **Multilingual UI** — `translations.py` engine with 10+ Indian language support
- **Language Selector** — Session-persisted language preference
- **Worker Profile Edit** — Update all profile fields including media files
- **Availability Toggle** — Workers can set Available/Unavailable
- **CORS Support** — Configured for `/api/*` routes
- **File Upload Security** — Extension whitelist + `secure_filename()` + UUID prefix
- **Indian Phone Validation** — Regex: `^[6-9]\d{9}$`
- **Responsive UI** — Mobile-first CSS design
- **Flask Session Management** — Server-side sessions with signed cookies

---

*Maintained by the VoiceHire Engineering Team*
