-- =====================================================================
-- VOICEHIRE — SUPABASE POSTGRESQL MIGRATION: HARDENING & READINESS
-- Version: 2.2.0
-- Migration: 20261019000000_database_hardening_and_readiness.sql
-- All changes are strictly additive and non-destructive.
-- =====================================================================

-- ─────────────────────────────────────────────────────────────────────
-- 1. SYSTEM READINESS & AUDIT INTEGRITY
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_events (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  actor_id      TEXT,
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

CREATE INDEX IF NOT EXISTS idx_audit_events_event_type ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_events_actor ON audit_events(actor_id, actor_role);
CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at DESC);

-- ─────────────────────────────────────────────────────────────────────
-- 2. ENHANCE: payments (Gateway Failure Details & Idempotency)
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE payments ADD COLUMN IF NOT EXISTS gateway_name TEXT DEFAULT 'razorpay';
ALTER TABLE payments ADD COLUMN IF NOT EXISTS gateway_order_id TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS gateway_payment_id TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS gateway_signature TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS verification_type TEXT DEFAULT 'electronic_signature';
ALTER TABLE payments ADD COLUMN IF NOT EXISTS error_code TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS error_description TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_payments_idempotency ON payments(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_payments_order ON payments(gateway_order_id);
CREATE INDEX IF NOT EXISTS idx_payments_payment_id ON payments(gateway_payment_id);

-- ─────────────────────────────────────────────────────────────────────
-- 3. TABLE: payment_webhooks (Deduplication & Replay Protection)
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payment_webhooks (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id    TEXT NOT NULL,
  event       TEXT,
  event_type  TEXT NOT NULL,
  payload     JSONB,
  status      TEXT DEFAULT 'processed',
  created_at  TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT uq_payment_webhook_event UNIQUE (event_id)
);

CREATE INDEX IF NOT EXISTS idx_payment_webhooks_event_id ON payment_webhooks(event_id);
CREATE INDEX IF NOT EXISTS idx_payment_webhooks_type ON payment_webhooks(event_type);

-- ─────────────────────────────────────────────────────────────────────
-- 4. SYSTEM HEALTH VIEW (For Readiness Health Checks)
-- ─────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW vh_readiness_probe AS
SELECT
  now() AS checked_at,
  'healthy' AS status,
  (SELECT count(*) FROM users) AS user_count,
  (SELECT count(*) FROM workers) AS worker_count,
  (SELECT count(*) FROM jobs) AS job_count,
  (SELECT count(*) FROM bookings) AS booking_count;
