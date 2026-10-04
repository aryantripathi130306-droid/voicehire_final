# 🎙️ VoiceHire

> **AI-powered, voice-first employment platform** connecting local skilled workers with customers — built for accessibility-first India.

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0.3-black?logo=flask)](https://flask.palletsprojects.com)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-green?logo=supabase)](https://supabase.com)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active%20Development-brightgreen)]()

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Problem Statement](#-problem-statement)
- [Solution](#-solution)
- [Key Features](#-key-features)
- [Tech Stack](#-tech-stack)
- [System Architecture](#-system-architecture)
- [ER Diagram](#-er-diagram)
- [API Reference](#-api-reference)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
- [Environment Variables](#-environment-variables)
- [Deployment](#-deployment)
- [Future Roadmap](#-future-roadmap)
- [Contributing](#-contributing)

---

## 🎯 Overview

**VoiceHire** is a dual-sided marketplace platform designed to bridge the digital divide between India's 450+ million informal workforce and the customers who need their services. By leveraging voice-first UX, multilingual support (10+ Indian languages), and QR-based job verification, VoiceHire makes employment discovery accessible to users regardless of literacy level.

---

## 🚨 Problem Statement

Millions of skilled workers — plumbers, maids, electricians, carpenters, vendors — remain unemployed or underutilized because:

| Challenge | Impact |
|-----------|--------|
| Cannot read/type in English | Excluded from digital platforms |
| No digital presence | Invisible to potential customers |
| Existing platforms are complex | High adoption barrier |
| No trust mechanism | Workers can't prove credibility |
| No booking system | Informal, unreliable arrangements |

---

## ✅ Solution

VoiceHire provides a complete platform where:

- **Workers** create profiles using **voice input** (speech-to-text), upload video introductions, and get discovered by nearby customers
- **Customers** search workers by service type and location, book time slots, and verify job completion via QR codes
- **Trust** is built through ratings, reviews, ID verification, and QR-based check-in/completion flow

---

## ⭐ Key Features

### For Workers
- 🎙️ **Voice Profile Creation** — record voice notes and video introductions
- 📍 **Live Location Sharing** — real-time GPS tracking during jobs
- 📅 **Booking Management** — accept/decline, view earnings stats
- 🔒 **ID Verification** — upload government ID proof
- 📊 **Earnings Dashboard** — today's and monthly earnings, job history
- 📤 **Data Export** — download profile + booking history as CSV

### For Customers
- 🔍 **Smart Worker Discovery** — filter by service type, location, rating
- 📆 **Slot-Based Booking** — structured time-slot scheduling system
- 📱 **QR Code Verification** — tamper-proof HMAC-signed QR for check-in
- ⭐ **Ratings and Reviews** — post-completion review system
- 🚨 **Urgent Jobs** — flag urgent service requests
- 🗺️ **Worker Tracking** — real-time GPS tracking of accepted worker

### Platform-Wide
- 🌐 **Multilingual UI** — 10+ Indian languages via built-in translation engine
- 🔐 **Secure Authentication** — bcrypt-hashed passwords, server-side sessions
- 📱 **Responsive Design** — mobile-first, works on low-end devices

---

## 🛠️ Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| **Backend Framework** | Flask | 3.0.3 |
| **Database** | Supabase (PostgreSQL) | 2.4.6 |
| **Auth** | Flask Sessions + Werkzeug bcrypt | — |
| **Frontend** | Vanilla HTML/CSS/JS | — |
| **QR Generation** | qrcode + Pillow | latest |
| **CORS** | Flask-CORS | 4.0.0 |
| **Environment** | python-dotenv | 1.2.2 |
| **Production Server** | Gunicorn | latest |
| **Storage** | Local filesystem (static/uploads) | — |
| **Translation** | Custom translations.py engine | — |

---

## 🏗️ System Architecture

```
+---------------------------------------------------------------------+
|                          CLIENT LAYER                               |
|  +------------------+  +------------------+  +------------------+  |
|  | Browser (Web)    |  | Mobile Browser   |  | QR Scanner       |  |
|  | HTML/CSS/JS      |  | Responsive UI    |  | (Camera API)     |  |
|  +--------+---------+  +--------+---------+  +--------+---------+  |
+-----------|------------------------|----------------------|---------+
            |   HTTPS Requests       |                      |
            v                        v                      v
+---------------------------------------------------------------------+
|                       APPLICATION LAYER                             |
|                  Flask (app.py -- 1488 lines)                       |
|  +--------------+  +--------------+  +---------------------------+ |
|  | Auth Routes  |  | Worker API   |  | Booking / QR System       | |
|  | /api/auth/*  |  | /api/worker/*|  | /api/bookings/*           | |
|  +--------------+  +--------------+  +---------------------------+ |
|  +--------------+  +--------------+  +---------------------------+ |
|  | Job Board    |  | Translation  |  | File Upload               | |
|  | /api/jobs/*  |  | /api/trans.. |  | /static/uploads/          | |
|  +--------------+  +--------------+  +---------------------------+ |
|                                                                     |
|  +---------------------------------------------------------------+  |
|  |              Template Engine (Jinja2)                         |  |
|  | gateway | login | signup | dashboard | booking | scan        |  |
|  +---------------------------------------------------------------+  |
+----------------------------+----------------------------------------+
                             | Supabase Python Client
                             v
+---------------------------------------------------------------------+
|                         DATA LAYER                                  |
|               Supabase (PostgreSQL + REST API)                      |
|  +----------+  +----------+  +----------+  +--------------+        |
|  |  users   |  | workers  |  |   jobs   |  |   bookings   |        |
|  +----------+  +----------+  +----------+  +--------------+        |
|  +----------+                                                       |
|  | reviews  |                                                       |
|  +----------+                                                       |
+---------------------------------------------------------------------+
```

---

## 🗄️ ER Diagram

```
+------------------+          +-------------------------------+
|      USERS       |          |           WORKERS             |
|------------------|          |-------------------------------|
| PK id (uuid)     |          | PK id (uuid)                  |
|    name          |          |    name                       |
|    phone (UNIQUE)|          |    work                       |
|    password      |          |    location                   |
|    profile_pic   |          |    phone (UNIQUE)             |
|    created_at    |          |    password                   |
+--------+---------+          |    voice_note                 |
         |                    |    video                      |
         |                    |    id_proof_path              |
         |                    |    profile_pic                |
         |                    |    voice_resume               |
         |                    |    latitude / longitude       |
         |                    |    live_lat / live_lng        |
         |                    |    is_sharing_location (bool) |
         |                    |    is_available (bool)        |
         |                    |    is_verified (bool)         |
         |                    |    price (numeric)            |
         |                    |    created_at                 |
         |                    +----------+--------------------+
         |                               |
         | 1 POSTS               ACCEPTS | 1
         | *                           * |
         v                               v
+-------------------------------------------------------+
|                        JOBS                           |
|-------------------------------------------------------|
| PK id (bigint, auto)                                  |
| FK user_id   --> users.id                             |
| FK worker_id --> workers.id  (nullable)               |
|    user_name, user_phone, user_profile_pic            |
|    service_type, description, location                |
|    is_urgent (bool)                                   |
|    status: open|accepted|pending_confirmation|        |
|            completed|cancelled                        |
|    price, completion_token, token_expires_at          |
|    created_at                                         |
+-------------------+-----------------------------------+
                    |
         +----------+----------+
         |                     |
         | 1 PLACES            | 1 ASSIGNED_TO
         | *                   *
         v                     v
+-------------------------------------------------------+
|                      BOOKINGS                         |
|-------------------------------------------------------|
| PK id (bigint, auto)                                  |
| FK customer_id --> users.id                           |
| FK worker_id   --> workers.id                         |
|    date (date)                                        |
|    time_slot: 09:00-11:00 | 11:00-13:00 | ...         |
|    notes                                              |
|    status: Pending|Booked|Work Started|               |
|            Completed|Cancelled                        |
|    total_price (numeric)                              |
|    qr_token  <-- HMAC-SHA256 signed                   |
|    created_at, updated_at                             |
+-------------------------------------------------------+
         |
         | After status=Completed
         | 1
         v
+-------------------------------------------------------+
|                       REVIEWS                         |
|-------------------------------------------------------|
| PK id (bigint, auto)                                  |
| FK job_id    --> jobs.id                              |
| FK worker_id --> workers.id                           |
| FK user_id   --> users.id                             |
|    rating (int, 1-5)                                  |
|    review (text)                                      |
|    created_at                                         |
+-------------------------------------------------------+
```

> **Legend:** PK = Primary Key | FK = Foreign Key | bool = boolean

---

## 📡 API Reference

### Authentication

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/auth/signup/user` | Register a new customer | No |
| `POST` | `/api/auth/signup/worker` | Register a new worker | No |
| `POST` | `/api/auth/login` | Login (user or worker) | No |
| `POST` | `/api/auth/logout` | Logout and clear session | Yes |
| `POST` | `/api/auth/profile/user` | Edit customer profile | Yes (User) |

### Workers

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `GET` | `/get_workers` | Discover workers with filters | No |
| `POST` | `/api/worker/edit` | Edit worker profile | Yes (Worker) |
| `POST` | `/api/worker/voice-resume` | Save voice resume text | Yes (Worker) |
| `POST` | `/api/worker/location` | Update live GPS location | Yes (Worker) |
| `POST` | `/api/worker/location/stop` | Stop sharing location | Yes (Worker) |
| `POST` | `/api/worker/availability` | Toggle availability status | Yes (Worker) |
| `GET` | `/api/worker/stats` | Earnings and job statistics | Yes (Worker) |
| `GET` | `/api/export-workers` | Export profile data as CSV | Yes (Worker) |

### Jobs

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/jobs` | Post a new job request | Yes (User) |
| `GET` | `/api/jobs` | Get open jobs (worker view) | Yes (Worker) |
| `GET` | `/api/jobs/customer` | Get customer's own jobs | Yes (User) |
| `POST` | `/api/jobs/<id>/accept` | Worker accepts a job | Yes (Worker) |
| `POST` | `/api/jobs/<id>/status` | Update job status | Yes (User) |
| `GET` | `/api/jobs/<id>/track` | Track accepted worker location | Yes (User) |
| `POST` | `/api/workers/<id>/rate` | Rate a worker after job | Yes (User) |

### Bookings

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `GET` | `/api/bookings/slots` | Get slot availability for date | Yes |
| `POST` | `/api/bookings` | Create a new booking | Yes (User) |
| `GET` | `/api/bookings` | Get my bookings | Yes |
| `GET` | `/api/bookings/<id>` | Get single booking details | Yes |
| `POST` | `/api/bookings/<id>/accept` | Worker accepts booking | Yes (Worker) |
| `POST` | `/api/bookings/<id>/decline` | Worker declines booking | Yes (Worker) |
| `POST` | `/api/bookings/<id>/checkin` | QR scan worker check-in | Yes |
| `POST` | `/api/bookings/<id>/complete` | Customer marks work complete | Yes (User) |
| `POST` | `/api/bookings/<id>/cancel` | Cancel a booking | Yes |

### Miscellaneous

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| `POST` | `/api/translate` | Translate text to selected language | No |
| `GET` | `/complete-job/<token>` | QR-based job completion link | Yes (Worker) |
| `GET` | `/set_lang/<lang_code>` | Set UI language | No |

---

## 📁 Project Structure

```
voicehire-final/
├── app.py                    # Main Flask application (1488 lines)
├── translations.py           # Translation engine (10+ Indian languages)
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (not committed)
├── .gitignore
├── VERSION
│
├── templates/                # Jinja2 HTML templates
│   ├── base.html             # Base layout with navigation
│   ├── gateway.html          # Landing page + language selector
│   ├── login.html            # Unified login page
│   ├── signup_role.html      # Role selection (user/worker)
│   ├── user_signup.html      # Customer registration
│   ├── worker_signup.html    # Worker registration (voice/video upload)
│   ├── user_dashboard.html   # Customer dashboard
│   ├── worker_dashboard.html # Worker dashboard + earnings
│   ├── booking_slots.html    # Time slot picker
│   ├── booking_detail.html   # Booking details + QR code display
│   ├── my_bookings.html      # Booking list view
│   ├── scan.html             # QR scanner page (worker)
│   └── qr_result.html        # QR scan result display
│
├── static/
│   ├── css/responsive.css    # Responsive styles
│   ├── js/                   # Client-side JavaScript
│   └── uploads/              # User-uploaded media
│       ├── audio/            # Voice notes (.mp3 .wav .ogg .m4a .aac)
│       ├── video/            # Video introductions (.mp4 .webm .mov)
│       ├── ids/              # ID proof images (.jpg .png)
│       └── profile_pics/     # Profile photos
│
├── docs/
│   ├── ARCHITECTURE.md       # System architecture deep-dive
│   ├── REQUIREMENTS.md       # Functional & non-functional requirements
│   └── API.md                # Detailed API documentation
│
├── adapters/                 # AI model adapter configurations
│   ├── CLAUDE.md
│   ├── GEMINI.md
│   └── GPT_OSS.md
│
├── .agent/workflows/         # GSD slash-command workflows
├── .agents/skills/           # Agent skill definitions
└── .gsd/                     # GSD project state files
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- A [Supabase](https://supabase.com) account and project
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/voicehire-final.git
cd voicehire-final
```

### 2. Create Virtual Environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env with your Supabase credentials and secret key
```

### 5. Set Up Supabase Database Tables

Run the SQL schema provided in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#database-schema) in your Supabase SQL editor.

### 6. Run the Application

```bash
python app.py
```

Open `http://localhost:5000` in your browser.

---

## 🔐 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SUPABASE_URL` | Your Supabase project URL | Yes |
| `SUPABASE_KEY` | Supabase service role key | Yes |
| `SECRET_KEY` | Flask session secret (use a strong random string) | Yes |
| `FLASK_DEBUG` | Enable debug mode (`True`/`False`) | No |
| `PORT` | Server port (default: `5000`) | No |

> ⚠️ **Security:** Never commit `.env` to version control. Rotate `SUPABASE_KEY` and `SECRET_KEY` periodically in production.

---

## 🌍 Deployment

### Production with Gunicorn

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
```

### Supported Platforms

| Platform | Notes |
|----------|-------|
| **Railway** | Set env vars in dashboard; auto-detects Gunicorn |
| **Render** | Start command: `gunicorn app:app` |
| **Heroku** | Add `Procfile`: `web: gunicorn app:app` |
| **AWS EC2** | Run behind Nginx as reverse proxy |

---

## 🗺️ Future Roadmap

| Feature | Priority | Status |
|---------|----------|--------|
| Push notifications (FCM) | High | Planned |
| In-app messaging | High | Planned |
| Payment gateway (Razorpay/UPI) | High | Planned |
| AI-based worker recommendations | Medium | Planned |
| Offline mode with service workers | Medium | Planned |
| Government ID verification (Aadhaar API) | Medium | Planned |
| Worker premium subscription tiers | Low | Concept |
| Admin dashboard and analytics panel | Low | Concept |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Follow the [GSD methodology](PROJECT_RULES.md) — spec before implementation
4. Commit atomically: `git commit -m "feat(scope): description"`
5. Push and open a Pull Request

Please read [PROJECT_RULES.md](PROJECT_RULES.md) and [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) before contributing.

---

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

*Built with ❤️ for India's informal workforce — making opportunity accessible to everyone.*
