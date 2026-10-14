-- =====================================================================
-- VOICEHIRE — SUPABASE POSTGRESQL MIGRATION: CORE DATA MODELS
-- Version: 2.0.0
-- Migration: 20261015000000_core_data_models.sql
-- All changes are strictly additive and non-destructive.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─────────────────────────────────────────────────────────────────────
-- 1. ENHANCE: users (Customers / Employers)
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_lang TEXT DEFAULT 'hi';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

-- ─────────────────────────────────────────────────────────────────────
-- 2. ENHANCE: workers (Service Providers)
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE workers ADD COLUMN IF NOT EXISTS service_radius_km INT DEFAULT 15;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS experience_years INT DEFAULT 1;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS bio TEXT;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS avg_rating NUMERIC(3, 2) DEFAULT 0.00;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS review_count INT DEFAULT 0;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS approx_lat FLOAT;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS approx_lng FLOAT;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

-- ─────────────────────────────────────────────────────────────────────
-- 3. TABLE: service_categories
-- ─────────────────────────────────────────────────────────────────────
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

-- ─────────────────────────────────────────────────────────────────────
-- 4. TABLE: worker_skills
-- ─────────────────────────────────────────────────────────────────────
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

-- ─────────────────────────────────────────────────────────────────────
-- 5. ENHANCE: jobs (Customer on-demand service requests)
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS category_id BIGINT REFERENCES service_categories(id) ON DELETE SET NULL;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS budget_min NUMERIC DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS budget_max NUMERIC DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

-- ─────────────────────────────────────────────────────────────────────
-- 6. TABLE: job_offers (Worker bids / proposals on open jobs)
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS job_offers (
  id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id                   BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  worker_id                UUID NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
  proposed_price           NUMERIC NOT NULL CHECK (proposed_price >= 0),
  estimated_arrival_minutes INT,
  message                  TEXT,
  status                   TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'withdrawn')),
  created_at               TIMESTAMPTZ DEFAULT now(),
  updated_at               TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT uq_job_worker_offer UNIQUE (job_id, worker_id)
);

CREATE INDEX IF NOT EXISTS idx_job_offers_job ON job_offers(job_id);
CREATE INDEX IF NOT EXISTS idx_job_offers_worker ON job_offers(worker_id);
CREATE INDEX IF NOT EXISTS idx_job_offers_status ON job_offers(status);

-- Concurrency protection: At most one offer can be accepted per job
CREATE UNIQUE INDEX IF NOT EXISTS uq_job_offers_accepted
  ON job_offers (job_id)
  WHERE status = 'accepted';

-- ─────────────────────────────────────────────────────────────────────
-- 7. ENHANCE: bookings (Scheduled Appointments)
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS service_category TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS address TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancellation_reason TEXT;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cancelled_by UUID;

-- ─────────────────────────────────────────────────────────────────────
-- 8. TABLE: booking_status_history
-- ─────────────────────────────────────────────────────────────────────
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
CREATE INDEX IF NOT EXISTS idx_bsh_created ON booking_status_history(created_at);

-- ─────────────────────────────────────────────────────────────────────
-- 9. TABLE: job_status_history
-- ─────────────────────────────────────────────────────────────────────
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
CREATE INDEX IF NOT EXISTS idx_jsh_created ON job_status_history(created_at);

-- ─────────────────────────────────────────────────────────────────────
-- 10. TABLE: booking_checkin_events
-- ─────────────────────────────────────────────────────────────────────
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
CREATE INDEX IF NOT EXISTS idx_bce_status ON booking_checkin_events(status);

-- ─────────────────────────────────────────────────────────────────────
-- 11. TABLE: payments
-- ─────────────────────────────────────────────────────────────────────
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
CREATE INDEX IF NOT EXISTS idx_payments_payer ON payments(payer_id);
CREATE INDEX IF NOT EXISTS idx_payments_payee ON payments(payee_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(payment_status);
CREATE INDEX IF NOT EXISTS idx_payments_idemp ON payments(idempotency_key);

-- ─────────────────────────────────────────────────────────────────────
-- 12. TABLE: payment_status_history
-- ─────────────────────────────────────────────────────────────────────
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

-- ─────────────────────────────────────────────────────────────────────
-- 13. TABLE: notifications
-- ─────────────────────────────────────────────────────────────────────
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
CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at);

-- ─────────────────────────────────────────────────────────────────────
-- 14. TABLE: job_reports (Disputes & Moderation Reports)
-- ─────────────────────────────────────────────────────────────────────
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
CREATE INDEX IF NOT EXISTS idx_reports_reporter ON job_reports(reporter_id);

-- ─────────────────────────────────────────────────────────────────────
-- 15. TABLE: audit_events (Security & Audit Trail)
-- ─────────────────────────────────────────────────────────────────────
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
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at);

-- ─────────────────────────────────────────────────────────────────────
-- 16. SEED ESSENTIAL SERVICE CATEGORIES (Idempotent)
-- ─────────────────────────────────────────────────────────────────────
INSERT INTO service_categories (name, slug, description, icon)
VALUES
  ('Plumbing', 'plumbing', 'Pipes, leaks, taps and bathroom fixtures', 'fa-solid fa-wrench'),
  ('Electrical', 'electrical', 'Wiring, switches, appliances and lighting', 'fa-solid fa-bolt'),
  ('Carpentry', 'carpentry', 'Furniture repair, doors, windows and woodwork', 'fa-solid fa-hammer'),
  ('Cleaning', 'cleaning', 'Home deep cleaning, sanitation and floor cleaning', 'fa-solid fa-broom'),
  ('Painting', 'painting', 'Interior & exterior wall painting and touchups', 'fa-solid fa-paint-roller'),
  ('Construction Helper', 'construction', 'Manual labor, loading and building support', 'fa-solid fa-trowel'),
  ('Driver & Transport', 'driver', 'Vehicle driving, goods delivery and hauling', 'fa-solid fa-truck'),
  ('Appliance Repair', 'appliance', 'AC, refrigerator, washing machine repair', 'fa-solid fa-tv')
ON CONFLICT (name) DO NOTHING;
