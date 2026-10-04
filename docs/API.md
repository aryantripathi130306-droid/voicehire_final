# API.md — VoiceHire REST API Documentation

> **Document Type:** API Reference  
> **Version:** 1.0.0  
> **Base URL:** `http://localhost:5000` (development) | `https://your-domain.com` (production)  
> **Authentication:** Server-side session (cookie-based)  
> **Content-Type:** `application/json` for request/response bodies

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Worker Endpoints](#2-worker-endpoints)
3. [Job Board Endpoints](#3-job-board-endpoints)
4. [Booking Endpoints](#4-booking-endpoints)
5. [Review Endpoints](#5-review-endpoints)
6. [Utility Endpoints](#6-utility-endpoints)
7. [Error Responses](#7-error-responses)
8. [Status Enums](#8-status-enums)

---

## 1. Authentication

### POST /api/auth/signup/user

Register a new customer account.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Customer display name |
| `phone` | string | Yes | Indian mobile number (10 digits, starts 6-9) |
| `password` | string | Yes | Min 6 characters |
| `profile_pic` | file | No | JPG/JPEG/PNG, max 16MB |

**Success Response: 201**
```json
{
  "message": "User registered successfully",
  "redirect": "/dashboard/user"
}
```

**Error Responses:**
```json
{ "error": "All fields are required" }                         // 400
{ "error": "Invalid Indian phone number" }                     // 400
{ "error": "Password must be at least 6 characters" }          // 400
{ "error": "Phone number already registered" }                  // 400
{ "error": "Invalid image file type for profile picture" }     // 400
{ "error": "Server error" }                                    // 500
```

---

### POST /api/auth/signup/worker

Register a new worker account.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Worker display name |
| `work` | string | Yes | Service type (e.g., "Plumber") |
| `location` | string | Yes | Area/city |
| `phone` | string | Yes | Indian mobile number |
| `password` | string | Yes | Min 6 characters |
| `voice_note` | file | No | mp3/wav/ogg/m4a/aac |
| `video` | file | No | mp4/webm/ogg/mov |
| `id_proof` | file | No | jpg/jpeg/png |
| `profile_pic` | file | No | jpg/jpeg/png |
| `latitude` | float | No | GPS latitude |
| `longitude` | float | No | GPS longitude |
| `price` | float | No | Service rate in INR |

**Success Response: 201**
```json
{
  "message": "Worker registered successfully",
  "redirect": "/dashboard/worker"
}
```

---

### POST /api/auth/login

Login for both customers and workers.

**Request:** `application/json`
```json
{
  "phone": "9876543210",
  "password": "yourpassword",
  "role": "user"
}
```

| Field | Values |
|-------|--------|
| `role` | `"user"` or `"worker"` |

**Success Response: 200**
```json
{
  "message": "Login successful",
  "redirect": "/dashboard/user"
}
```

**Error Response: 401**
```json
{ "error": "Invalid phone or password" }
```

---

### POST /api/auth/logout

**Auth Required:** Yes  
**Request:** No body required

**Response: 200**
```json
{ "redirect": "/signup" }
```

---

### POST /api/auth/profile/user

Edit customer profile.

**Auth Required:** Yes (Customer)  
**Request:** `multipart/form-data`

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Updated name |
| `phone` | Yes | Updated phone |
| `password` | No | New password (min 6 chars) |
| `profile_pic` | No | New profile photo |

**Response: 200**
```json
{
  "message": "Profile updated successfully",
  "redirect": "/dashboard/user"
}
```

---

## 2. Worker Endpoints

### POST /api/worker/edit

Edit worker profile.

**Auth Required:** Yes (Worker)  
**Request:** `multipart/form-data`

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Updated name |
| `work` | Yes | Service type |
| `location` | Yes | Area/city |
| `phone` | Yes | Phone number |
| `password` | No | New password |
| `voice_note` | No | New voice note file |
| `video` | No | New video file |
| `id_proof` | No | New ID proof image |
| `profile_pic` | No | New profile photo |
| `latitude` | No | GPS latitude |
| `longitude` | No | GPS longitude |
| `price` | No | Updated service rate |

**Response: 200**
```json
{
  "message": "Profile updated successfully",
  "redirect": "/dashboard/worker"
}
```

---

### POST /api/worker/voice-resume

Save worker's transcribed voice resume text.

**Auth Required:** Yes (Worker)  
**Request:** `application/json`
```json
{
  "resume_text": "I am an experienced plumber with 10 years..."
}
```

Constraints: max 1000 characters

**Response: 200**
```json
{ "message": "Saved" }
```

---

### POST /api/worker/location

Share live GPS location.

**Auth Required:** Yes (Worker)  
**Request:** `application/json`
```json
{
  "lat": 28.7041,
  "lng": 77.1025
}
```

**Response: 200**
```json
{ "message": "Updated" }
```

---

### POST /api/worker/location/stop

Stop sharing live location.

**Auth Required:** Yes (Worker)  
**Request:** No body

**Response: 200**
```json
{ "message": "Stopped" }
```

---

### POST /api/worker/availability

Toggle worker availability status.

**Auth Required:** Yes (Worker)  
**Request:** `application/json`
```json
{
  "is_available": true
}
```

**Response: 200**
```json
{
  "message": "Availability updated",
  "is_available": true
}
```

---

### GET /api/worker/stats

Get worker earnings and job statistics.

**Auth Required:** Yes (Worker)

**Response: 200**
```json
{
  "name": "Ramesh Kumar",
  "today_earnings": 500.00,
  "month_earnings": 12500.00,
  "last_jobs": [
    {
      "work": "Plumber",
      "date": "2026-10-03",
      "status": "Completed"
    },
    {
      "work": "Plumber",
      "date": "2026-10-01",
      "status": "Completed"
    }
  ]
}
```

---

### GET /api/export-workers

Export worker's own profile data and booking history as CSV.

**Auth Required:** Yes (Worker)

**Response: 200** `Content-Type: text/csv`  
Attachment: `worker_data_<id_prefix>.csv`

The CSV contains two sections:
1. `--- WORKER PROFILE ---` with all profile fields (password excluded)
2. `--- BOOKING HISTORY ---` with all booking records

---

### GET /get_workers

Discover and list workers. Publicly accessible.

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `work` | string | Filter by service type (partial match, case-insensitive) |
| `location` | string | Filter by location (partial match, case-insensitive) |

**Example:** `GET /get_workers?work=plumber&location=delhi`

**Response: 200**
```json
[
  {
    "id": "uuid-here",
    "name": "Ramesh Kumar",
    "work": "Plumber",
    "location": "South Delhi",
    "phone": "9876543210",
    "voice_note": "uploads/audio/abc123_voice.mp3",
    "video": null,
    "profile_pic": "uploads/profile_pics/abc123_pic.jpg",
    "latitude": 28.7041,
    "longitude": 77.1025,
    "is_available": true,
    "is_verified": false,
    "price": 500.00,
    "avg_rating": 4.5,
    "review_count": 12,
    "created_at": "2026-09-01T10:00:00+00:00"
  }
]
```

Workers sorted: available first, then by `avg_rating` descending.

---

## 3. Job Board Endpoints

### POST /api/jobs

Post a new service request.

**Auth Required:** Yes (Customer)  
**Request:** `application/json`
```json
{
  "service_type": "Plumber",
  "description": "Kitchen pipe leaking, need urgent fix",
  "location": "Vasant Kunj, Delhi",
  "is_urgent": true
}
```

**Response: 201**
```json
{ "message": "Job posted successfully!" }
```

---

### GET /api/jobs

Get open jobs (worker's perspective, filtered for their service type).

**Auth Required:** Yes (Worker)  
**Query Parameters:**

| Parameter | Description |
|-----------|-------------|
| `work` | Filter by service type |
| `location` | Filter by location |

**Response: 200**
```json
[
  {
    "id": 42,
    "user_id": "uuid-here",
    "user_name": "Priya Sharma",
    "user_phone": "9988776655",
    "service_type": "Plumber",
    "description": "Kitchen pipe leaking",
    "location": "Vasant Kunj, Delhi",
    "is_urgent": true,
    "status": "open",
    "created_at": "2026-10-04T10:30:00+00:00"
  }
]
```

Sorted: urgent first, then newest first.

---

### GET /api/jobs/customer

Get all jobs posted by the logged-in customer.

**Auth Required:** Yes (Customer)

**Response: 200**
```json
[
  {
    "id": 42,
    "service_type": "Plumber",
    "description": "Kitchen pipe leaking",
    "location": "Vasant Kunj, Delhi",
    "status": "accepted",
    "worker_name": "Ramesh Kumar",
    "worker_phone": "9876543210",
    "price": 500.0,
    "created_at": "2026-10-04T10:30:00+00:00"
  }
]
```

---

### POST /api/jobs/{job_id}/accept

Worker accepts an open job.

**Auth Required:** Yes (Worker)  
**Request:** `application/json`
```json
{
  "price": 600
}
```

**Response: 200**
```json
{
  "message": "Job accepted successfully",
  "price": 600
}
```

**Error Responses:**
```json
{ "error": "Job not found" }             // 404
{ "error": "Job is no longer open" }     // 400
```

---

### POST /api/jobs/{job_id}/status

Update job status (customer only).

**Auth Required:** Yes (Customer)  
**Request:** `application/json`
```json
{
  "status": "completed"
}
```

Valid values: `"open"`, `"completed"`, `"cancelled"`

**Response: 200**
```json
{ "message": "Job marked as completed" }
```

---

### GET /api/jobs/{job_id}/track

Get real-time location of the worker assigned to a job.

**Auth Required:** Yes (Customer)

**Response: 200**
```json
{
  "name": "Ramesh Kumar",
  "is_sharing_location": true,
  "live_lat": 28.7041,
  "live_lng": 77.1025,
  "location_updated_at": "2026-10-04T11:45:00+00:00"
}
```

**Error Responses:**
```json
{ "error": "Job not active" }           // 400
{ "error": "Worker not found" }         // 404
```

---

## 4. Booking Endpoints

### GET /api/bookings/slots

Get slot availability for a worker on a specific date.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `worker_id` | string (UUID) | Yes | Worker's UUID |
| `date` | string | Yes | Format: `YYYY-MM-DD` |

**Example:** `GET /api/bookings/slots?worker_id=uuid&date=2026-10-10`

**Response: 200**
```json
[
  { "slot": "09:00-11:00", "available": true },
  { "slot": "11:00-13:00", "available": false },
  { "slot": "13:00-15:00", "available": true },
  { "slot": "15:00-17:00", "available": true },
  { "slot": "17:00-19:00", "available": true }
]
```

---

### POST /api/bookings

Create a new booking.

**Auth Required:** Yes (Customer)  
**Request:** `application/json`
```json
{
  "worker_id": "uuid-here",
  "date": "2026-10-10",
  "time_slot": "09:00-11:00",
  "notes": "Please bring pipe sealant"
}
```

**Response: 201**
```json
{
  "message": "Booking confirmed!",
  "booking_id": 101,
  "redirect": "/bookings/101"
}
```

**Error Responses:**
```json
{ "error": "This slot is already booked. Please choose another." }  // 409
{ "error": "Worker not found" }                                      // 404
{ "error": "date must be YYYY-MM-DD" }                              // 400
```

---

### GET /api/bookings

Get all bookings for the logged-in user (customer or worker).

**Auth Required:** Yes

**Response: 200**
```json
[
  {
    "id": 101,
    "customer_id": "customer-uuid",
    "worker_id": "worker-uuid",
    "date": "2026-10-10",
    "time_slot": "09:00-11:00",
    "notes": "Please bring pipe sealant",
    "status": "Booked",
    "total_price": 500.0,
    "customer_name": "Priya Sharma",
    "customer_profile_pic": null,
    "worker_name": "Ramesh Kumar",
    "worker_work": "Plumber",
    "worker_profile_pic": "uploads/profile_pics/abc.jpg"
  }
]
```

---

### GET /api/bookings/{booking_id}

Get a single booking's current status.

**Auth Required:** Yes (Customer or assigned Worker)

**Response: 200** — Full booking object (same structure as list above)

---

### POST /api/bookings/{booking_id}/accept

Worker accepts a Pending booking.

**Auth Required:** Yes (Worker — must be the assigned worker)

**Response: 200**
```json
{
  "message": "Booking accepted!",
  "status": "Booked"
}
```

**Error Responses:**
```json
{ "error": "Cannot accept. Current status: Booked" }   // 400
{ "error": "Unauthorized" }                             // 403
```

---

### POST /api/bookings/{booking_id}/decline

Worker declines a Pending booking.

**Auth Required:** Yes (Worker — must be assigned worker)

**Response: 200**
```json
{
  "message": "Booking declined.",
  "status": "Cancelled"
}
```

---

### POST /api/bookings/{booking_id}/checkin

QR-based check-in. Transitions Booked → Work Started.

**Auth Required:** Yes  
**Request:** `application/json`
```json
{
  "token": "hmac-or-uuid-token-here"
}
```

**Response: 200**
```json
{
  "message": "Check-in successful! Work has started.",
  "status": "Work Started"
}
```

**Error Responses:**
```json
{ "error": "Invalid or expired QR code" }                   // 403
{ "error": "Cannot check in. Current status: Completed" }   // 400
```

---

### POST /api/bookings/{booking_id}/complete

Customer marks job as complete. Transitions Work Started → Completed.

**Auth Required:** Yes (Customer only)

**Response: 200**
```json
{
  "message": "Work marked as completed!",
  "status": "Completed"
}
```

---

### POST /api/bookings/{booking_id}/cancel

Cancel a booking (customer or worker).

**Auth Required:** Yes

**Response: 200**
```json
{
  "message": "Booking cancelled.",
  "status": "Cancelled"
}
```

**Error Responses:**
```json
{ "error": "Cannot cancel a completed or already cancelled booking" }  // 400
```

---

## 5. Review Endpoints

### POST /api/workers/{worker_id}/rate

Submit a rating and review for a worker after job completion.

**Auth Required:** Yes (Customer)  
**Request:** `application/json`
```json
{
  "job_id": 42,
  "rating": 5,
  "review": "Excellent work! Very professional."
}
```

| Field | Constraint |
|-------|-----------|
| `job_id` | Must be a completed job belonging to caller |
| `rating` | Integer 1–5 |
| `review` | Optional text |

**Response: 201**
```json
{ "message": "Review submitted successfully" }
```

**Error Responses:**
```json
{ "error": "Valid job ID and rating (1-5) are required" }      // 400
{ "error": "Job must be completed to leave a review" }          // 400
{ "error": "Review already submitted for this job" }            // 400
{ "error": "Rating must be an integer" }                        // 400
```

---

## 6. Utility Endpoints

### POST /api/translate

Translate a text string or array of strings to the specified language.

**Request:** `application/json`
```json
{
  "lang": "hi",
  "text": "Find a Worker"
}
```

Or batch:
```json
{
  "lang": "hi",
  "text": ["Find a Worker", "Login", "Book Now"]
}
```

**Response: 200**
```json
{ "translated": "एक कर्मचारी खोजें" }
```

Or batch:
```json
{
  "translated": {
    "Find a Worker": "एक कर्मचारी खोजें",
    "Login": "लॉग इन करें",
    "Book Now": "अभी बुक करें"
  }
}
```

---

### GET /complete-job/{token}

Complete a job via QR-embedded token link (for the Job Board system, not booking system).

**Auth Required:** Yes (Worker — must be assigned to job)  
**URL Parameter:** `token` — completion token from accepted job

**Response:** Renders `qr_result.html` with success/failure message

Success: Status updated to `pending_confirmation`, token invalidated  
Failure: Token invalid, expired, or wrong worker

---

### GET /set_lang/{lang_code}

Set the UI language for the current session.

**Auth Required:** No  
**URL Parameter:** `lang_code` — language code (e.g., `hi`, `ta`, `te`, `en`)

**Response: 302** Redirect to `/` (homepage)

---

## 7. Error Responses

All API errors follow this format:

```json
{
  "error": "Human-readable error description"
}
```

### HTTP Status Code Reference

| Code | Meaning | Common Cause |
|------|---------|--------------|
| `200` | OK | Successful GET/update |
| `201` | Created | Resource successfully created |
| `400` | Bad Request | Missing fields, invalid format, business rule violation |
| `401` | Unauthorized | Not logged in or wrong role |
| `403` | Forbidden | Logged in but not permitted (wrong owner, wrong role) |
| `404` | Not Found | Resource doesn't exist |
| `409` | Conflict | Double-booking attempt |
| `500` | Server Error | Unhandled exception (check server logs) |

---

## 8. Status Enums

### Job Status Lifecycle

```
open ──────────────────────────────────────────────> cancelled
  |
  v
accepted ──────────────────────────────────────────> cancelled
  |
  v
pending_confirmation
  |
  v
completed
```

| Status | Description |
|--------|-------------|
| `open` | Job posted, waiting for worker to accept |
| `accepted` | Worker has accepted; one-time QR token active |
| `pending_confirmation` | Worker scanned QR; waiting for customer to confirm |
| `completed` | Customer confirmed job completion |
| `cancelled` | Job cancelled by customer |

---

### Booking Status Lifecycle

```
Pending ────────────────────────────────────────────> Cancelled
  |
  v (Worker accepts)
Booked ─────────────────────────────────────────────> Cancelled
  |
  v (QR check-in)
Work Started ───────────────────────────────────────> Cancelled
  |
  v (Customer confirms)
Completed
```

| Status | Description |
|--------|-------------|
| `Pending` | Booking created, worker has not accepted yet |
| `Booked` | Worker accepted; appointment confirmed |
| `Work Started` | Worker has checked in via QR code |
| `Completed` | Customer confirmed work is done |
| `Cancelled` | Booking cancelled by customer or worker (before Completed) |

---

## Available Time Slots

```
09:00-11:00
11:00-13:00
13:00-15:00
15:00-17:00
17:00-19:00
```

---

*VoiceHire API Documentation — v1.0.0*  
*Last updated: October 2026*
