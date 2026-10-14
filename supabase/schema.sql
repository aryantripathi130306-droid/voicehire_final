-- =====================================================================
-- VOICEHIRE — SUPABASE POSTGRESQL DATABASE SCHEMA
-- Version: 1.2.0
-- =====================================================================

-- Enable UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =====================================================================
-- TABLE: users (Customers / Employers)
-- =====================================================================
CREATE TABLE IF NOT EXISTS users (
  id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  name        TEXT        NOT NULL,
  phone       TEXT        UNIQUE NOT NULL,
  password    TEXT        NOT NULL,           -- Werkzeug hashed
  profile_pic TEXT,                           -- relative path in static/uploads
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);

-- =====================================================================
-- TABLE: workers (Service Providers)
-- =====================================================================
CREATE TABLE IF NOT EXISTS workers (
  id                   UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  name                 TEXT        NOT NULL,
  work                 TEXT        NOT NULL,  -- e.g. "Plumber", "Electrician"
  location             TEXT        NOT NULL,  -- area/city name
  phone                TEXT        UNIQUE NOT NULL,
  password             TEXT        NOT NULL,  -- Werkzeug hashed
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
  price                NUMERIC     DEFAULT 0, -- per-service / per-day rate (INR)
  created_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workers_phone ON workers(phone);
CREATE INDEX IF NOT EXISTS idx_workers_work ON workers(work);
CREATE INDEX IF NOT EXISTS idx_workers_location ON workers(location);
CREATE INDEX IF NOT EXISTS idx_workers_available ON workers(is_available);

-- =====================================================================
-- TABLE: jobs (On-demand Service Requests)
-- =====================================================================
CREATE TABLE IF NOT EXISTS jobs (
  id                BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id           UUID        REFERENCES users(id) ON DELETE SET NULL,
  worker_id         UUID        REFERENCES workers(id) ON DELETE SET NULL,
  user_name         TEXT,
  user_phone        TEXT,
  user_profile_pic  TEXT,
  service_type      TEXT        NOT NULL,
  description       TEXT        NOT NULL,
  location          TEXT        NOT NULL,
  is_urgent         BOOLEAN     DEFAULT false,
  status            TEXT        DEFAULT 'open',
  -- Status lifecycle: open | accepted | pending_confirmation | completed | cancelled
  price             NUMERIC,
  completion_token  TEXT,       -- One-time secure token for job completion
  token_expires_at  TIMESTAMPTZ,
  created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_worker_id ON jobs(worker_id);
CREATE INDEX IF NOT EXISTS idx_jobs_token ON jobs(completion_token);

-- =====================================================================
-- TABLE: bookings (Scheduled Time-Slot Appointments)
-- =====================================================================
CREATE TABLE IF NOT EXISTS bookings (
  id           BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  customer_id  UUID        REFERENCES users(id) ON DELETE CASCADE,
  worker_id    UUID        REFERENCES workers(id) ON DELETE CASCADE,
  date         DATE        NOT NULL,
  time_slot    TEXT        NOT NULL,
  -- Allowed slots: 09:00-11:00 | 11:00-13:00 | 13:00-15:00 | 15:00-17:00 | 17:00-19:00
  notes        TEXT,
  status       TEXT        DEFAULT 'Pending',
  -- Status lifecycle: Pending -> Booked -> Work Started -> Completed (or Cancelled)
  total_price  NUMERIC,
  qr_token     TEXT,       -- UUID hex, used for HMAC-SHA256 verification
  created_at   TIMESTAMPTZ DEFAULT now(),
  updated_at   TIMESTAMPTZ DEFAULT now()
);

-- Unique index to prevent double-booking of any active slot
CREATE UNIQUE INDEX IF NOT EXISTS uq_bookings_slot
  ON bookings (worker_id, date, time_slot)
  WHERE status != 'Cancelled';

CREATE INDEX IF NOT EXISTS idx_bookings_customer_id ON bookings(customer_id);
CREATE INDEX IF NOT EXISTS idx_bookings_worker_id ON bookings(worker_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status);

-- =====================================================================
-- TABLE: reviews (Worker Ratings & Feedback)
-- =====================================================================
CREATE TABLE IF NOT EXISTS reviews (
  id         BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id     BIGINT      REFERENCES jobs(id) ON DELETE SET NULL,
  worker_id  UUID        REFERENCES workers(id) ON DELETE CASCADE,
  user_id    UUID        REFERENCES users(id) ON DELETE SET NULL,
  rating     INT         NOT NULL CHECK (rating BETWEEN 1 AND 5),
  review     TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Ensure only one review per job
CREATE UNIQUE INDEX IF NOT EXISTS uq_reviews_job ON reviews (job_id);
CREATE INDEX IF NOT EXISTS idx_reviews_worker_id ON reviews(worker_id);

-- =====================================================================
-- TABLE: service_categories
-- =====================================================================
CREATE TABLE IF NOT EXISTS service_categories (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  slug        TEXT NOT NULL UNIQUE,
  description TEXT,
  icon        TEXT,
  is_active   BOOLEAN DEFAULT true,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_categories_slug ON service_categories(slug);
CREATE INDEX IF NOT EXISTS idx_categories_active ON service_categories(is_active);

-- =====================================================================
-- TABLE: worker_skills
-- =====================================================================
CREATE TABLE IF NOT EXISTS worker_skills (
  id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  worker_id        UUID NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
  category_id      BIGINT REFERENCES service_categories(id) ON DELETE SET NULL,
  skill_name       TEXT NOT NULL,
  experience_years INT DEFAULT 1,
  is_primary       BOOLEAN DEFAULT false,
  created_at       TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT uq_worker_skill UNIQUE (worker_id, skill_name)
);

CREATE INDEX IF NOT EXISTS idx_worker_skills_worker ON worker_skills(worker_id);
CREATE INDEX IF NOT EXISTS idx_worker_skills_cat ON worker_skills(category_id);

-- =====================================================================
-- TABLE: job_offers
-- =====================================================================
CREATE TABLE IF NOT EXISTS job_offers (
  id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id                    BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  worker_id                 UUID NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
  proposed_price            NUMERIC NOT NULL CHECK (proposed_price >= 0),
  estimated_arrival_minutes INT,
  message                   TEXT,
  status                    TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'withdrawn')),
  created_at                TIMESTAMPTZ DEFAULT now(),
  updated_at                TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT uq_job_worker_offer UNIQUE (job_id, worker_id)
);

CREATE INDEX IF NOT EXISTS idx_job_offers_job ON job_offers(job_id);
CREATE INDEX IF NOT EXISTS idx_job_offers_worker ON job_offers(worker_id);
CREATE INDEX IF NOT EXISTS idx_job_offers_status ON job_offers(status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_job_offers_accepted
  ON job_offers (job_id)
  WHERE status = 'accepted';

-- =====================================================================
-- TABLE: booking_status_history
-- =====================================================================
CREATE TABLE IF NOT EXISTS booking_status_history (
  id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  booking_id        BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  from_status       TEXT NOT NULL,
  to_status         TEXT NOT NULL,
  changed_by        UUID,
  changed_by_role   TEXT NOT NULL,
  reason            TEXT,
  created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bsh_booking_id ON booking_status_history(booking_id);

-- =====================================================================
-- TABLE: job_status_history
-- =====================================================================
CREATE TABLE IF NOT EXISTS job_status_history (
  id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id            BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  from_status       TEXT NOT NULL,
  to_status         TEXT NOT NULL,
  changed_by        UUID,
  changed_by_role   TEXT NOT NULL,
  reason            TEXT,
  created_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_jsh_job_id ON job_status_history(job_id);

-- =====================================================================
-- TABLE: booking_checkin_events
-- =====================================================================
CREATE TABLE IF NOT EXISTS booking_checkin_events (
  id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  booking_id     BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
  worker_id      UUID NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
  customer_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type     TEXT NOT NULL CHECK (event_type IN ('checkin_attempt', 'checkin_verified', 'checkout_completed')),
  status         TEXT NOT NULL CHECK (status IN ('success', 'failed', 'expired', 'tampered')),
  token_hash     TEXT,
  client_lat     FLOAT,
  client_lng     FLOAT,
  ip_address     TEXT,
  user_agent     TEXT,
  failure_reason TEXT,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bce_booking ON booking_checkin_events(booking_id);

-- =====================================================================
-- TABLE: payments
-- =====================================================================
CREATE TABLE IF NOT EXISTS payments (
  id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  booking_id       BIGINT REFERENCES bookings(id) ON DELETE SET NULL,
  job_id           BIGINT REFERENCES jobs(id) ON DELETE SET NULL,
  payer_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  payee_id         UUID NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
  amount           NUMERIC NOT NULL CHECK (amount >= 0),
  currency         TEXT DEFAULT 'INR',
  payment_method   TEXT DEFAULT 'cash' CHECK (payment_method IN ('cash', 'upi', 'qr', 'wallet', 'card')),
  payment_status   TEXT DEFAULT 'pending' CHECK (payment_status IN ('pending', 'authorized', 'captured', 'completed', 'failed', 'refunded')),
  idempotency_key  TEXT UNIQUE,
  transaction_ref  TEXT,
  notes            TEXT,
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payments_booking ON payments(booking_id);
CREATE INDEX IF NOT EXISTS idx_payments_job ON payments(job_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(payment_status);

-- =====================================================================
-- TABLE: payment_status_history
-- =====================================================================
CREATE TABLE IF NOT EXISTS payment_status_history (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  payment_id  BIGINT NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
  from_status TEXT NOT NULL,
  to_status   TEXT NOT NULL,
  changed_by  UUID,
  notes       TEXT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_psh_payment ON payment_status_history(payment_id);

-- =====================================================================
-- TABLE: notifications
-- =====================================================================
CREATE TABLE IF NOT EXISTS notifications (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  recipient_id    UUID NOT NULL,
  recipient_role  TEXT NOT NULL CHECK (recipient_role IN ('user', 'worker', 'admin')),
  title           TEXT NOT NULL,
  message         TEXT NOT NULL,
  type            TEXT NOT NULL CHECK (type IN ('job_alert', 'offer_received', 'booking_status', 'checkin', 'payment', 'system')),
  reference_id    TEXT,
  is_read         BOOLEAN DEFAULT false,
  idempotency_key TEXT UNIQUE,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_id, is_read);

-- =====================================================================
-- TABLE: job_reports (Disputes)
-- =====================================================================
CREATE TABLE IF NOT EXISTS job_reports (
  id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  reporter_id      UUID NOT NULL,
  reporter_role    TEXT NOT NULL CHECK (reporter_role IN ('user', 'worker')),
  reported_id      UUID NOT NULL,
  reported_role    TEXT NOT NULL CHECK (reported_role IN ('user', 'worker')),
  job_id           BIGINT REFERENCES jobs(id) ON DELETE SET NULL,
  booking_id       BIGINT REFERENCES bookings(id) ON DELETE SET NULL,
  reason           TEXT NOT NULL,
  description      TEXT NOT NULL,
  status           TEXT DEFAULT 'open' CHECK (status IN ('open', 'under_review', 'resolved', 'dismissed')),
  resolution_notes TEXT,
  resolved_by      UUID,
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reports_status ON job_reports(status);

-- =====================================================================
-- TABLE: audit_events
-- =====================================================================
CREATE TABLE IF NOT EXISTS audit_events (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_id      UUID,
  actor_role    TEXT,
  event_type    TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id   TEXT NOT NULL,
  action        TEXT NOT NULL,
  ip_address    TEXT,
  status        TEXT DEFAULT 'success',
  metadata      JSONB DEFAULT '{}'::jsonb,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_events(resource_type, resource_id);

