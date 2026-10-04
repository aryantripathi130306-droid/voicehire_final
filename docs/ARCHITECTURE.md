# ARCHITECTURE.md — VoiceHire System Architecture

> **Document Type:** Technical Architecture Reference  
> **Version:** 1.0.0  
> **Last Updated:** October 2026  
> **Audience:** Developers, Architects, Technical Reviewers

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Layer-by-Layer Breakdown](#3-layer-by-layer-breakdown)
4. [Data Flow Diagrams](#4-data-flow-diagrams)
5. [Database Schema](#5-database-schema)
6. [Security Architecture](#6-security-architecture)
7. [File Storage Architecture](#7-file-storage-architecture)
8. [QR Code & Verification System](#8-qr-code--verification-system)
9. [Translation Architecture](#9-translation-architecture)
10. [Session Management](#10-session-management)
11. [API Design Principles](#11-api-design-principles)
12. [Scalability Considerations](#12-scalability-considerations)
13. [Known Limitations & Technical Debt](#13-known-limitations--technical-debt)

---

## 1. System Overview

VoiceHire is a **monolithic Flask web application** backed by **Supabase (PostgreSQL)** as its database and storage backend. The system implements a **dual-sided marketplace** with two actor types:

- **Workers** (service providers: plumbers, maids, electricians, etc.)
- **Users/Customers** (service seekers)

The platform's core innovation is its **accessibility-first design**: workers can create profiles entirely through voice input (speech-to-text via Web Speech API), removing barriers for low-literacy users.

### Core Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | Flask (monolith) | Rapid development, minimal complexity |
| Database | Supabase (PostgreSQL) | Real-time capable, hosted, generous free tier |
| Auth | Custom (bcrypt + sessions) | Avoids 3rd party dependency for Indian phone numbers |
| Storage | Local filesystem | Simple, no additional cost |
| Frontend | Server-rendered Jinja2 | Works on low-end devices without JS framework |
| QR Security | HMAC-SHA256 | Tamper-proof without external service |

---

## 2. High-Level Architecture

```
+=========================================================================+
||                         VOICEHIRE PLATFORM                           ||
+=========================================================================+

  CLIENT TIER                APPLICATION TIER           DATA TIER
  -----------                ----------------           ---------

  [Browser]                  [Flask App]                [Supabase]
  HTML/CSS/JS  <==HTTP==>    app.py (1488 LOC)  <===>  PostgreSQL
  Web Speech API             Jinja2 Templates           REST API
  Camera (QR scan)           Session Management         5 Tables
  Geolocation API            File Upload Handler
                             Translation Engine
                             QR Code Generator

  [Mobile Browser]
  Responsive CSS
  Touch Events
```

### Request Lifecycle

```
Browser Request
     |
     v
Flask Route Handler (app.py)
     |
     +---> Session Check (is_authenticated?)
     |          |
     |       [NO] --> redirect to /login
     |          |
     |       [YES] --> continue
     |
     +---> Supabase Query (via supabase-py client)
     |          |
     |       [ERROR] --> log + return 500
     |          |
     |       [OK] --> process data
     |
     +---> Render Template (Jinja2) OR return JSON
     |
     v
HTTP Response to Browser
```

---

## 3. Layer-by-Layer Breakdown

### 3.1 Presentation Layer (Templates)

Located in `/templates/`, all pages use **Jinja2** server-side rendering. Base template (`base.html`) provides shared navigation, session state, and language injection.

| Template | Route | Actor |
|----------|-------|-------|
| `gateway.html` | `/` | Public |
| `login.html` | `/login` | Public |
| `signup_role.html` | `/signup` | Public |
| `user_signup.html` | `/signup/user` | Public |
| `worker_signup.html` | `/signup/worker` | Public |
| `user_dashboard.html` | `/dashboard/user` | Customer |
| `worker_dashboard.html` | `/dashboard/worker` | Worker |
| `booking_slots.html` | `/book/<worker_id>` | Customer |
| `booking_detail.html` | `/bookings/<id>` | Both |
| `my_bookings.html` | `/bookings` | Both |
| `scan.html` | `/scan` | Worker |
| `qr_result.html` | `/complete-job/<token>` | Worker |

### 3.2 Application Layer (Flask Routes)

`app.py` is structured into logical sections:

```
app.py
├── Configuration & Initialization (L1-52)
│   ├── Flask app setup
│   ├── CORS configuration
│   ├── Upload folder creation
│   └── Supabase client init
│
├── Helper Functions (L54-92)
│   ├── allowed_file()        - extension validation
│   ├── is_valid_phone()      - Indian phone validation
│   ├── safe_str()            - input sanitization
│   ├── try_select()          - graceful DB query helper
│   └── inject_translation()  - context processor
│
├── Template Routes (L100-219)
│   ├── index / gateway / dashboard routes
│   └── QR completion route
│
├── Authentication API (L221-421)
│   ├── /api/auth/signup/user
│   ├── /api/auth/signup/worker
│   ├── /api/auth/login
│   └── /api/auth/logout
│
├── Worker API (L423-570)
│   ├── Profile edit
│   ├── Voice resume
│   ├── Live location (start/stop)
│   └── Availability toggle
│
├── Data API (L571-917)
│   ├── Worker discovery (/get_workers)
│   ├── Job posting & management
│   ├── Worker rating
│   └── Translation endpoint
│
├── Booking System (L919-1353)
│   ├── Time slot management
│   ├── QR token generation/verification
│   ├── Booking CRUD
│   └── Check-in / Complete / Cancel flows
│
└── Export & Stats (L1354-1488)
    ├── CSV export
    └── Earnings statistics
```

### 3.3 Data Layer (Supabase/PostgreSQL)

All database interactions go through the official `supabase-py` client. The `try_select()` helper provides resilience against schema evolution (e.g., missing `profile_pic` column).

---

## 4. Data Flow Diagrams

### 4.1 Worker Registration Flow

```
Worker --> /signup/worker (GET)
        --> Fills form (name, work, location, phone, password)
        --> Records voice note (Web Speech API)
        --> Records video introduction
        --> Uploads ID proof image
        --> Submits POST /api/auth/signup/worker
              |
              v
        Flask validates inputs
              |
        Saves files to static/uploads/{audio,video,ids,profile_pics}/
              |
        Inserts record into workers table (Supabase)
              |
        Creates session (user_id, role='worker', name, phone)
              |
        Redirects to /dashboard/worker
```

### 4.2 Job Booking Flow

```
Customer --> /book/<worker_id> (GET)
          --> Selects date + time slot
          --> GET /api/bookings/slots?worker_id=X&date=Y
                  |
                  v
            Supabase: Query bookings for conflicts
                  |
            Returns slot availability
                  |
          Customer picks available slot
          --> POST /api/bookings { worker_id, date, time_slot, notes }
                  |
                  v
            Double-booking guard check
                  |
            Insert into bookings table
            { status: 'Pending', qr_token: uuid4().hex }
                  |
            Redirect to /bookings/<id>

Worker --> GET /api/bookings (polling or notification)
        --> POST /api/bookings/<id>/accept
              |
              status = 'Booked'

On day of service:
Worker arrives --> Customer opens /bookings/<id>
               --> QR code displayed (HMAC token)
               --> Worker scans QR via /scan
               --> POST /api/bookings/<id>/checkin { token }
                     |
                     HMAC verification
                     |
                     status = 'Work Started'

Work done:
Customer --> POST /api/bookings/<id>/complete
              |
              status = 'Completed'
              |
Customer --> POST /api/workers/<id>/rate { rating, review, job_id }
```

### 4.3 Worker Discovery Flow

```
Customer --> GET /get_workers?work=plumber&location=delhi
              |
              v
        Supabase: SELECT * FROM workers WHERE work ILIKE '%plumber%'
                  AND location ILIKE '%delhi%'
              |
        Supabase: SELECT worker_id, rating FROM reviews
              |
        Compute avg_rating and review_count per worker
              |
        Sort: available first, then by avg_rating DESC, review_count DESC
              |
        Return JSON array to browser
              |
        Frontend renders worker cards
```

---

## 5. Database Schema

### Full SQL Schema

```sql
-- =============================================
-- TABLE: users (customers)
-- =============================================
CREATE TABLE users (
  id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  name        TEXT        NOT NULL,
  phone       TEXT        UNIQUE NOT NULL,
  password    TEXT        NOT NULL,           -- bcrypt hashed
  profile_pic TEXT,                           -- relative path to static/
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- =============================================
-- TABLE: workers (service providers)
-- =============================================
CREATE TABLE workers (
  id                   UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  name                 TEXT        NOT NULL,
  work                 TEXT        NOT NULL,  -- e.g. "Plumber", "Electrician"
  location             TEXT        NOT NULL,  -- area/city name
  phone                TEXT        UNIQUE NOT NULL,
  password             TEXT        NOT NULL,  -- bcrypt hashed
  voice_note           TEXT,                  -- path: uploads/audio/...
  video                TEXT,                  -- path: uploads/video/...
  id_proof_path        TEXT,                  -- path: uploads/ids/...
  profile_pic          TEXT,                  -- path: uploads/profile_pics/...
  voice_resume         TEXT,                  -- transcribed voice text (max 1000 chars)
  latitude             FLOAT,                 -- registration location
  longitude            FLOAT,
  live_lat             FLOAT,                 -- real-time GPS (nullable)
  live_lng             FLOAT,
  is_sharing_location  BOOLEAN     DEFAULT false,
  location_updated_at  TIMESTAMPTZ,
  is_available         BOOLEAN     DEFAULT true,
  is_verified          BOOLEAN     DEFAULT false,
  price                NUMERIC     DEFAULT 0, -- per-service rate (INR)
  created_at           TIMESTAMPTZ DEFAULT now()
);

-- =============================================
-- TABLE: jobs (quick service requests)
-- =============================================
CREATE TABLE jobs (
  id                BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id           UUID        REFERENCES users(id),
  worker_id         UUID        REFERENCES workers(id),     -- nullable until accepted
  user_name         TEXT,
  user_phone        TEXT,
  user_profile_pic  TEXT,
  service_type      TEXT        NOT NULL,
  description       TEXT        NOT NULL,
  location          TEXT        NOT NULL,
  is_urgent         BOOLEAN     DEFAULT false,
  status            TEXT        DEFAULT 'open',
  -- Allowed values: open | accepted | pending_confirmation | completed | cancelled
  price             NUMERIC,
  completion_token  TEXT,                                   -- one-time secure token
  token_expires_at  TIMESTAMPTZ,                            -- 48h window
  created_at        TIMESTAMPTZ DEFAULT now()
);

-- =============================================
-- TABLE: bookings (scheduled appointments)
-- =============================================
CREATE TABLE bookings (
  id           BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  customer_id  UUID        REFERENCES users(id),
  worker_id    UUID        REFERENCES workers(id),
  date         DATE        NOT NULL,
  time_slot    TEXT        NOT NULL,
  -- Allowed values: 09:00-11:00 | 11:00-13:00 | 13:00-15:00
  --                 15:00-17:00 | 17:00-19:00
  notes        TEXT,
  status       TEXT        DEFAULT 'Pending',
  -- Lifecycle: Pending -> Booked -> Work Started -> Completed
  --                                              -> Cancelled (any stage except Completed)
  total_price  NUMERIC,
  qr_token     TEXT,       -- UUID hex, used for HMAC verification
  created_at   TIMESTAMPTZ DEFAULT now(),
  updated_at   TIMESTAMPTZ DEFAULT now()
);

-- Prevent double-booking
CREATE UNIQUE INDEX uq_bookings_slot
  ON bookings (worker_id, date, time_slot)
  WHERE status != 'Cancelled';

-- =============================================
-- TABLE: reviews
-- =============================================
CREATE TABLE reviews (
  id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id     BIGINT      REFERENCES jobs(id),
  worker_id  UUID        REFERENCES workers(id),
  user_id    UUID        REFERENCES users(id),
  rating     INT         NOT NULL CHECK (rating BETWEEN 1 AND 5),
  review     TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Prevent duplicate reviews per job
CREATE UNIQUE INDEX uq_reviews_job ON reviews (job_id);
```

### Entity Relationships Summary

```
users ----<< jobs (user posts many jobs)
workers --<< jobs (worker accepts many jobs)
users ----<< bookings (customer has many bookings)
workers --<< bookings (worker has many bookings)
jobs -----< reviews (job has one review)
workers --<< reviews (worker has many reviews)
users ----<< reviews (user submits many reviews)
```

---

## 6. Security Architecture

### Authentication

- **Password Storage:** Werkzeug `generate_password_hash()` using **PBKDF2-SHA256** (bcrypt-compatible)
- **Session:** Flask server-side sessions with `SECRET_KEY`-signed cookies
- **Phone Validation:** Regex enforces Indian format (`^[6-9]\d{9}$`)

### Authorization

All protected routes check session state:

```python
# Pattern used throughout app.py
if 'user_id' not in session or session['role'] != 'worker':
    return jsonify({'error': 'Unauthorized'}), 401
```

Two distinct roles:
- `role == 'user'` → Customer access
- `role == 'worker'` → Worker access

### QR Code Security

The booking check-in QR uses **HMAC-SHA256** signing:

```python
def make_qr_token(booking_id) -> str:
    secret = app.secret_key.encode('utf-8')
    msg = str(booking_id).encode('utf-8')
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()

def verify_qr_token(booking_id, token: str) -> bool:
    # Constant-time comparison prevents timing attacks
    return hmac.compare_digest(make_qr_token(booking_id), token)
```

Job completion tokens use **cryptographically random** tokens:
```python
token = secrets.token_urlsafe(32)  # 256 bits of entropy
expires = (datetime.utcnow() + timedelta(hours=48)).isoformat()
```

### File Upload Security

```python
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a', 'aac'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'webm', 'ogg', 'mov'}
ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB hard limit
```

Filenames are sanitized with `werkzeug.utils.secure_filename()` and prefixed with `uuid4().hex` to prevent path traversal attacks.

### CORS Policy

```python
CORS(app, resources={r"/api/*": {"origins": "*"}})
```

> ⚠️ **Production Recommendation:** Restrict CORS `origins` to your specific domain.

---

## 7. File Storage Architecture

Files are stored on the local filesystem under `static/uploads/`:

```
static/uploads/
├── audio/          # Worker voice notes
│   └── <uuid>_<original_filename>.{mp3,wav,ogg,m4a,aac}
├── video/          # Worker video introductions
│   └── <uuid>_<original_filename>.{mp4,webm,ogg,mov}
├── ids/            # Government ID proof images
│   └── <uuid>_<original_filename>.{jpg,jpeg,png}
└── profile_pics/   # User and worker profile photos
    └── <uuid>_<original_filename>.{jpg,jpeg,png}
```

Paths stored in the database are **relative** to the `static/` directory, e.g., `uploads/audio/abc123_voice.mp3`. Templates render them as:

```html
<audio src="{{ url_for('static', filename=worker.voice_note) }}">
```

> ⚠️ **Production Consideration:** Migrate to Supabase Storage or AWS S3 for distributed deployment. Local filesystem does not scale horizontally.

---

## 8. QR Code & Verification System

### Booking Check-in Flow (QR-based)

```
1. Booking created → qr_token = uuid4().hex stored in DB
2. Customer views /bookings/<id> → QR rendered from HMAC token
3. Worker opens /scan → camera access → ZXing/native QR decode
4. Worker scans QR → payload = { "bid": <id>, "tok": <hmac_token> }
5. POST /api/bookings/<id>/checkin { token: <tok> }
6. Server verifies: token == booking.qr_token OR verify_hmac(id, token)
7. status updated: 'Booked' → 'Work Started'
```

### Job Completion Flow (URL-based)

```
1. Worker accepts job → completion_token = secrets.token_urlsafe(32)
   token_expires_at = now() + 48h
2. Customer receives QR code for /complete-job/<token>
3. Worker scans QR → browser opens /complete-job/<token>
4. Server: finds job by completion_token
5. Validates: token not expired AND job.worker_id == session.user_id
6. Updates: status = 'pending_confirmation', completion_token = NULL (one-time use)
```

---

## 9. Translation Architecture

The `translations.py` module provides a pre-compiled dictionary of key UI phrases in 10+ Indian languages:

```python
# translations.py structure (297,895 bytes — large pre-compiled dict)
TRANSLATIONS = {
    "hi": {  # Hindi
        "Welcome": "स्वागत है",
        ...
    },
    "ta": {  # Tamil
        ...
    },
    # etc.
}

def get_translation(lang_code: str, text: str) -> str:
    return TRANSLATIONS.get(lang_code, {}).get(text, text)
    # Falls back to original text if translation not found
```

Language selection is persisted in the **Flask session** (`session['lang']`) and set via `/set_lang/<lang_code>`.

A **Jinja2 context processor** makes the `t()` function available globally in all templates:

```python
@app.context_processor
def inject_translation():
    def t(text):
        lang = session.get('lang', 'en')
        return get_translation(lang, text)
    return dict(t=t)
```

Usage in templates:
```html
<h1>{{ t('Find a Worker') }}</h1>
```

---

## 10. Session Management

Flask server-side sessions store:

| Key | Value | Set On |
|-----|-------|--------|
| `user_id` | UUID string | Login / Signup |
| `role` | `'user'` or `'worker'` | Login / Signup |
| `name` | Display name | Login / Signup |
| `phone` | Phone number | Login (users only) |
| `lang` | Language code | `/set_lang/<code>` |
| `qr_token_pending` | Pending QR token | Unauthenticated QR scan |

Sessions are cleared on logout:
```python
session.clear()
```

---

## 11. API Design Principles

| Principle | Implementation |
|-----------|----------------|
| **RESTful** | Standard HTTP verbs; GET reads, POST creates/updates |
| **JSON API** | All `/api/*` routes return `Content-Type: application/json` |
| **Consistent Error Format** | `{ "error": "message" }` with appropriate HTTP status |
| **Session Auth** | No JWT; server-side session cookie |
| **Input Sanitization** | `safe_str()` strips all user inputs |
| **Graceful Degradation** | `try_select()` handles missing columns without crashing |

### HTTP Status Codes Used

| Code | Usage |
|------|-------|
| `200` | Success |
| `201` | Resource created |
| `400` | Bad request / validation error |
| `401` | Unauthenticated |
| `403` | Unauthorized (wrong role/ownership) |
| `404` | Resource not found |
| `409` | Conflict (double-booking) |
| `500` | Server error |

---

## 12. Scalability Considerations

### Current Bottlenecks

| Area | Limitation | Recommended Solution |
|------|-----------|---------------------|
| **File Storage** | Local filesystem; single server only | Migrate to Supabase Storage / S3 |
| **Real-time** | Workers poll location; no push | Add WebSockets or Supabase Realtime |
| **Session Store** | In-memory / cookie; no horizontal scaling | Redis session store |
| **Translation** | 297KB in-memory dict | Database-backed or CDN-cached |
| **QR Refresh** | Static QR code | Auto-refresh every 30s |

### Scaling Path

```
Phase 1 (Current):   Single Flask + Local Storage + Supabase
Phase 2 (Growth):    Gunicorn multi-worker + S3 uploads + Redis sessions
Phase 3 (Scale):     Microservices: Auth, Booking, Notification services
                     + Message queue (Redis/RabbitMQ) for notifications
```

---

## 13. Known Limitations & Technical Debt

| Issue | Location | Risk | Mitigation |
|-------|----------|------|------------|
| Hardcoded `SECRET_KEY` fallback | `app.py:27` | High | Enforce env var in production |
| CORS `origins: "*"` | `app.py:29` | Medium | Restrict to domain |
| No input length limits on most fields | Various | Medium | Add Supabase constraints |
| Password column stored as plain text reference in DB | `workers` table | — | Already bcrypt-hashed in Python |
| `translations.py` loaded fully at startup (297KB) | App startup | Low | Cache after first load |
| No rate limiting on API endpoints | All routes | High | Add Flask-Limiter |
| No HTTPS enforcement | `app.py` | High | Enforce via Nginx/platform |
| File size validated only at 16MB hard limit | Upload routes | Medium | Add per-type limits |
| Supabase key is `service_role` in .env | `.env` | High | Use `anon` key + RLS policies |

---

*VoiceHire Architecture Document — Maintained by the development team*  
*For questions, open an issue or refer to [PROJECT_RULES.md](../PROJECT_RULES.md)*
