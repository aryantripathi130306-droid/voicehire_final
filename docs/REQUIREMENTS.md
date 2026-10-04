# REQUIREMENTS.md — VoiceHire Product Requirements

> **Document Type:** Product & Technical Requirements Specification  
> **Version:** 1.2.0  
> **Status:** FINALIZED  
> **Last Updated:** October 2026  
> **Author:** VoiceHire Engineering Team

---

## Table of Contents

1. [Document Purpose](#1-document-purpose)
2. [Product Vision](#2-product-vision)
3. [Stakeholders](#3-stakeholders)
4. [User Personas](#4-user-personas)
5. [Functional Requirements](#5-functional-requirements)
6. [Non-Functional Requirements](#6-non-functional-requirements)
7. [System Constraints](#7-system-constraints)
8. [Business Rules](#8-business-rules)
9. [Use Cases](#9-use-cases)
10. [Acceptance Criteria](#10-acceptance-criteria)
11. [Out of Scope](#11-out-of-scope)
12. [Glossary](#12-glossary)

---

## 1. Document Purpose

This document defines the complete functional and non-functional requirements for the VoiceHire platform. It serves as the authoritative specification for:

- Development team implementation decisions
- Quality assurance test planning
- Stakeholder alignment and sign-off
- Future feature prioritization

> **Planning Lock:** No implementation shall begin for any feature not described herein without first updating this document and receiving stakeholder sign-off.

---

## 2. Product Vision

**Mission:** Make skilled employment accessible to every Indian worker, regardless of literacy level, by removing the text-first barrier of existing platforms.

**Vision Statement:** VoiceHire will be India's most accessible blue-collar employment marketplace — where a plumber in a village can get hired as easily as a software engineer in Bengaluru.

**Target Market:** India's informal workforce — estimated at 450+ million workers — in sectors including home services, construction, domestic help, and local vendors.

---

## 3. Stakeholders

| Stakeholder | Role | Interest |
|-------------|------|----------|
| **Workers** | Primary End User | Get discovered, get hired, earn money |
| **Customers** | Primary End User | Find reliable, affordable, nearby services |
| **Platform Admin** | Internal | Platform health, fraud prevention |
| **Engineering Team** | Internal | Build & maintain the system |
| **Product Team** | Internal | Feature decisions, roadmap |

---

## 4. User Personas

### Persona A: Ramesh — The Local Plumber

- **Age:** 38 | **Location:** Semi-urban Delhi NCR
- **Literacy:** Reads Hindi partially, cannot read English
- **Tech Access:** Android smartphone (basic), 4G internet
- **Goal:** Get regular work orders without relying on word-of-mouth
- **Pain Points:** Cannot use existing apps (English-only), no digital presence
- **VoiceHire Benefit:** Creates profile using voice in Hindi, gets bookings without typing

### Persona B: Priya — The Busy Professional Customer

- **Age:** 29 | **Location:** Urban Bengaluru
- **Literacy:** Highly educated, fluent English
- **Tech Access:** iPhone, high-speed internet
- **Goal:** Find reliable home service workers quickly
- **Pain Points:** Unreliable workers, no scheduling, no way to verify quality
- **VoiceHire Benefit:** Browses verified workers, books slots, tracks arrival, pays after review

### Persona C: Lakshmi — The House Maid

- **Age:** 45 | **Location:** Hyderabad
- **Literacy:** Telugu native speaker, minimal English
- **Tech Access:** Basic Android, shared smartphone
- **Goal:** Supplement income with additional household clients
- **VoiceHire Benefit:** Telugu interface, voice-based signup, simple availability toggle

---

## 5. Functional Requirements

### FR-001: User Authentication

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-001.1 | System shall allow registration via phone number and password | Must Have |
| FR-001.2 | System shall validate Indian phone numbers (10 digits, starts with 6-9) | Must Have |
| FR-001.3 | System shall hash passwords using bcrypt before storage | Must Have |
| FR-001.4 | System shall maintain authenticated session across page loads | Must Have |
| FR-001.5 | System shall support two distinct roles: `user` (customer) and `worker` | Must Have |
| FR-001.6 | System shall redirect authenticated users to their role-appropriate dashboard | Must Have |
| FR-001.7 | System shall clear all session data on logout | Must Have |

### FR-002: Worker Registration & Profile

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-002.1 | Worker shall provide: name, service type, location, phone, password | Must Have |
| FR-002.2 | Worker shall be able to upload a voice note (audio file) as profile introduction | Must Have |
| FR-002.3 | Worker shall be able to upload a video introduction | Should Have |
| FR-002.4 | Worker shall be able to upload an ID proof image | Must Have |
| FR-002.5 | Worker shall be able to upload a profile photo | Should Have |
| FR-002.6 | Worker shall be able to provide GPS coordinates at registration | Should Have |
| FR-002.7 | Worker shall be able to set an hourly/service price | Must Have |
| FR-002.8 | System shall support audio formats: mp3, wav, ogg, m4a, aac | Must Have |
| FR-002.9 | System shall support video formats: mp4, webm, ogg, mov | Should Have |
| FR-002.10 | System shall support image formats: jpg, jpeg, png | Must Have |
| FR-002.11 | System shall enforce 16MB maximum file upload size | Must Have |

### FR-003: Worker Profile Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-003.1 | Worker shall be able to edit all profile fields | Must Have |
| FR-003.2 | Worker shall be able to toggle availability status (Available/Unavailable) | Must Have |
| FR-003.3 | Worker shall be able to share live GPS location | Should Have |
| FR-003.4 | Worker shall be able to stop sharing live GPS location | Should Have |
| FR-003.5 | Worker shall be able to save a voice resume as transcribed text (max 1000 chars) | Should Have |
| FR-003.6 | Worker shall be able to export their profile and booking history as CSV | Nice to Have |

### FR-004: Worker Discovery

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-004.1 | System shall allow filtering workers by service type | Must Have |
| FR-004.2 | System shall allow filtering workers by location (partial match) | Must Have |
| FR-004.3 | System shall display workers sorted by: availability first, then rating descending | Must Have |
| FR-004.4 | System shall display average rating and review count per worker | Must Have |
| FR-004.5 | System shall show worker availability status prominently | Must Have |
| FR-004.6 | System shall display worker voice note for playback | Should Have |
| FR-004.7 | System shall display worker video introduction | Should Have |

### FR-005: Job Posting (Quick Requests)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-005.1 | Customer shall be able to post a service request with: service type, description, location | Must Have |
| FR-005.2 | Customer shall be able to mark a job as urgent | Should Have |
| FR-005.3 | Workers shall see open job requests filtered by their work type and location | Must Have |
| FR-005.4 | Worker shall be able to accept an open job | Must Have |
| FR-005.5 | System shall generate a one-time completion token (valid 48 hours) when job is accepted | Must Have |
| FR-005.6 | Customer shall be able to update job status (completed, cancelled) | Must Have |
| FR-005.7 | Worker shall be able to mark job as done via QR scan | Must Have |
| FR-005.8 | System shall invalidate completion token after single use | Must Have |

### FR-006: Booking System (Scheduled Appointments)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-006.1 | System shall support 5 time slots per day: 09:00-11:00, 11:00-13:00, 13:00-15:00, 15:00-17:00, 17:00-19:00 | Must Have |
| FR-006.2 | System shall prevent double-booking of the same worker-date-slot combination | Must Have |
| FR-006.3 | Customer shall see slot availability before booking | Must Have |
| FR-006.4 | Booking shall follow lifecycle: Pending → Booked → Work Started → Completed | Must Have |
| FR-006.5 | Booking may be Cancelled at any stage before Completed | Must Have |
| FR-006.6 | Worker shall be able to accept or decline a Pending booking | Must Have |
| FR-006.7 | QR code shall be generated for each confirmed booking | Must Have |
| FR-006.8 | QR code check-in shall transition booking from Booked → Work Started | Must Have |
| FR-006.9 | Customer shall confirm job completion to transition Work Started → Completed | Must Have |
| FR-006.10 | System shall display booking price (worker's listed rate) at booking | Must Have |

### FR-007: QR Code System

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-007.1 | System shall generate QR codes using HMAC-SHA256 signing | Must Have |
| FR-007.2 | QR verification shall use constant-time comparison to prevent timing attacks | Must Have |
| FR-007.3 | QR tokens shall be single-use only | Must Have |
| FR-007.4 | Job completion QR tokens shall expire after 48 hours | Must Have |
| FR-007.5 | System shall display appropriate error messages for invalid/expired QR codes | Must Have |
| FR-007.6 | System shall validate that the scanning worker matches the assigned worker | Must Have |

### FR-008: Rating & Review System

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-008.1 | Customer shall be able to rate a worker on a 1-5 star scale after job completion | Must Have |
| FR-008.2 | Customer shall be able to leave a text review | Should Have |
| FR-008.3 | System shall prevent duplicate reviews for the same job | Must Have |
| FR-008.4 | System shall calculate and display average rating per worker | Must Have |
| FR-008.5 | Review can only be submitted for jobs with status `completed` | Must Have |

### FR-009: Multilingual Support

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-009.1 | System shall support at minimum: English, Hindi | Must Have |
| FR-009.2 | System shall support additional Indian languages via translations.py | Should Have |
| FR-009.3 | Language preference shall persist in user session | Must Have |
| FR-009.4 | System shall fall back to original text if translation not found | Must Have |
| FR-009.5 | Language can be changed via UI without losing other session data | Must Have |

### FR-010: Worker Earnings & Statistics

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-010.1 | Worker dashboard shall display today's earnings | Should Have |
| FR-010.2 | Worker dashboard shall display current month's earnings | Should Have |
| FR-010.3 | Worker dashboard shall display the last 2 completed jobs | Should Have |
| FR-010.4 | System shall calculate earnings from `total_price` on completed bookings | Must Have |

---

## 6. Non-Functional Requirements

### NFR-001: Performance

| ID | Requirement |
|----|-------------|
| NFR-001.1 | API responses shall complete within 2 seconds under normal load |
| NFR-001.2 | Page load time shall not exceed 4 seconds on 3G connection |
| NFR-001.3 | Worker discovery query shall handle 10,000+ worker records |
| NFR-001.4 | File uploads shall not block the main request thread |

### NFR-002: Security

| ID | Requirement |
|----|-------------|
| NFR-002.1 | Passwords must be hashed using PBKDF2-SHA256 (via Werkzeug) |
| NFR-002.2 | All session cookies must be HttpOnly and Secure in production |
| NFR-002.3 | File uploads must be validated by extension AND magic bytes |
| NFR-002.4 | Uploaded filenames must be sanitized to prevent path traversal |
| NFR-002.5 | HMAC tokens must use constant-time comparison |
| NFR-002.6 | Environment secrets must never be hardcoded in source code |
| NFR-002.7 | API endpoints must enforce role-based access control |

### NFR-003: Accessibility

| ID | Requirement |
|----|-------------|
| NFR-003.1 | Platform must support voice input via Web Speech API |
| NFR-003.2 | UI must function on devices with 1GB RAM and 4G internet |
| NFR-003.3 | Critical actions (book, accept, complete) must work with a single tap |
| NFR-003.4 | All text displayed must be available in the selected language |

### NFR-004: Reliability

| ID | Requirement |
|----|-------------|
| NFR-004.1 | System must handle database errors gracefully without exposing stack traces to users |
| NFR-004.2 | File upload failures must not corrupt the database record |
| NFR-004.3 | Double-booking prevention must be atomic (no race condition) |
| NFR-004.4 | Session must be invalidated immediately upon logout |

### NFR-005: Maintainability

| ID | Requirement |
|----|-------------|
| NFR-005.1 | All API routes must have docstrings describing purpose and auth requirements |
| NFR-005.2 | Database queries must go through the Supabase client (no raw SQL in templates) |
| NFR-005.3 | File type validation must be centralized in `allowed_file()` |
| NFR-005.4 | Translation calls must go through `get_translation()` function |

### NFR-006: Compatibility

| ID | Requirement |
|----|-------------|
| NFR-006.1 | Must support Chrome 90+, Firefox 88+, Safari 14+ |
| NFR-006.2 | Must be responsive on screen widths 320px and above |
| NFR-006.3 | QR scanning must work using device camera via browser API |
| NFR-006.4 | Voice input must work on Chrome for Android |

---

## 7. System Constraints

| Constraint | Description |
|------------|-------------|
| **Budget** | Must use free/low-cost infrastructure (Supabase free tier, local file storage) |
| **Phone Numbers** | Indian phone numbers only (10 digits, starting 6-9) |
| **File Size** | Maximum 16MB per uploaded file |
| **Authentication** | Phone number + password only; no social login |
| **Language** | Python 3.11+ required |
| **Database** | Must use Supabase REST API; no direct PostgreSQL connections |
| **QR Expiry** | Job completion tokens expire in 48 hours |
| **Review Limit** | One review per job only |
| **Voice Resume** | Maximum 1000 characters |

---

## 8. Business Rules

| Rule ID | Business Rule |
|---------|--------------|
| BR-001 | A phone number can only be registered once (either as user OR worker) |
| BR-002 | A worker cannot accept a job that is not in `open` status |
| BR-003 | A booking can only be cancelled before status `Completed` |
| BR-004 | A review can only be submitted for `completed` jobs |
| BR-005 | Only the customer who posted a job can mark it completed or cancelled |
| BR-006 | Only the worker assigned to a booking can accept or decline it |
| BR-007 | QR check-in is only valid when booking status is `Booked` |
| BR-008 | Job completion via QR only transitions to `pending_confirmation` (customer must confirm) |
| BR-009 | Workers are sorted by availability, then rating, then review count |
| BR-010 | Available workers appear above unavailable workers in all listings |
| BR-011 | Earnings are calculated only from `Completed` bookings |
| BR-012 | File type validation uses extension whitelist (no executable types allowed) |

---

## 9. Use Cases

### UC-001: Worker Completes Registration

**Actor:** Unregistered Worker  
**Precondition:** Worker has a smartphone and Indian phone number  
**Trigger:** Worker opens VoiceHire and selects "Register as Worker"

**Main Flow:**
1. Worker fills in name, service type, location, phone, password
2. Worker records a voice introduction
3. Worker optionally records a video introduction
4. Worker uploads ID proof image
5. System validates all inputs
6. System saves files to local storage
7. System inserts worker record into database
8. System creates session and redirects to worker dashboard

**Alternative Flows:**
- 5a. Phone already registered → error message displayed
- 5b. Invalid file type → error message, form not submitted
- 5c. Invalid phone format → validation error shown

---

### UC-002: Customer Books a Worker

**Actor:** Authenticated Customer  
**Precondition:** Customer is logged in; target worker exists  
**Trigger:** Customer clicks "Book Now" on a worker card

**Main Flow:**
1. Customer is redirected to `/book/<worker_id>`
2. Customer selects a date
3. System fetches available slots for that date
4. Customer selects an available time slot
5. Customer optionally adds notes
6. Customer confirms booking
7. System checks for double-booking conflict
8. System creates booking record with status `Pending`
9. System redirects to booking detail page with QR code
10. Worker receives booking notification (checks dashboard)
11. Worker accepts booking → status changes to `Booked`

**Alternative Flows:**
- 7a. Slot already taken → 409 Conflict error shown
- 11a. Worker declines → status changes to `Cancelled`

---

### UC-003: QR Check-in on Job Day

**Actor:** Worker (authenticated)  
**Precondition:** Booking is in `Booked` status  
**Trigger:** Worker arrives at customer location

**Main Flow:**
1. Worker opens `/scan` page on their device
2. System requests camera permission
3. Worker scans QR code displayed on customer's phone
4. Browser decodes QR payload: `{ "bid": <id>, "tok": <token> }`
5. POST `/api/bookings/<id>/checkin` with token
6. System verifies token against booking record
7. Status updates to `Work Started`
8. Both parties see status update

**Alternative Flows:**
- 6a. Invalid token → 403 error, check-in rejected
- 6b. Booking not in `Booked` status → 400 error with current status

---

## 10. Acceptance Criteria

| Feature | Acceptance Criteria |
|---------|---------------------|
| Worker Registration | Worker can register with voice note, video, ID proof; profile appears in discovery within 30 seconds |
| Customer Registration | Customer can register with name, phone, password; redirected to dashboard |
| Worker Discovery | Workers filterable by service type and location; sorted by availability then rating |
| Job Posting | Job visible to workers within 10 seconds of posting; urgent jobs appear at top |
| Booking Creation | Booking created with correct time slot; double-booking prevented; QR code displayed |
| QR Check-in | Valid QR changes status to Work Started; invalid/expired QR returns error |
| Job Completion | Customer marks complete; review form appears; rating stored and averaged |
| Multilingual | Switching language changes UI text immediately; preference persists |
| Availability Toggle | Worker can toggle status; change reflected in discovery within 5 seconds |
| CSV Export | Worker data exported as valid CSV with profile and booking history sections |

---

## 11. Out of Scope

The following features are explicitly **not** in scope for the current version:

| Feature | Reason |
|---------|--------|
| Payment processing | Requires payment gateway integration (planned for v2) |
| In-app messaging | Requires WebSocket infrastructure |
| Push notifications | Requires FCM integration |
| Admin panel | Internal tooling, not customer-facing |
| AI-based matching | Requires ML pipeline |
| Aadhaar verification | Government API approval needed |
| Worker subscription tiers | Business model not finalized |
| Offline mode | Service worker implementation deferred |
| Social login (Google/Facebook) | Not relevant for target demographic |
| iOS/Android native apps | Web-first approach chosen |

---

## 12. Glossary

| Term | Definition |
|------|------------|
| **Worker** | A service provider registered on VoiceHire (plumber, maid, electrician, etc.) |
| **Customer / User** | A person who uses VoiceHire to find and hire workers |
| **Job** | A quick, informal service request posted by a customer |
| **Booking** | A scheduled, time-slotted appointment between customer and worker |
| **QR Token** | A cryptographically signed token embedded in a QR code for verification |
| **Completion Token** | A one-time-use URL token generated when a worker accepts a job |
| **Voice Resume** | Transcribed text from a worker's spoken self-introduction |
| **Slot** | A 2-hour time window for a booking (e.g., 09:00-11:00) |
| **IST** | Indian Standard Time (UTC+5:30) |
| **HMAC** | Hash-based Message Authentication Code — used for QR security |
| **GSD** | Get Shit Done — the agile methodology used by the development team |
| **Supabase** | The Backend-as-a-Service platform providing the PostgreSQL database |

---

*VoiceHire Requirements Document — Status: FINALIZED*  
*For change requests, follow the GSD SPEC amendment process in [PROJECT_RULES.md](../PROJECT_RULES.md)*
