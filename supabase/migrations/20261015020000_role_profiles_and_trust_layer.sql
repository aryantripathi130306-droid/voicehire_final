-- =====================================================================
-- VOICEHIRE — SUPABASE POSTGRESQL MIGRATION: ROLE PROFILES & TRUST LAYER
-- Version: 2.1.0
-- Migration: 20261015020000_role_profiles_and_trust_layer.sql
-- All changes are strictly additive and non-destructive.
-- =====================================================================

-- ─────────────────────────────────────────────────────────────────────
-- 1. ENHANCE: workers (Role-Specific Profile & Verification Fields)
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE workers ADD COLUMN IF NOT EXISTS quote_preference TEXT DEFAULT 'estimate_then_confirm';
-- quote_preference: 'fixed_only' | 'estimate_then_confirm' | 'inspection_required'
ALTER TABLE workers ADD COLUMN IF NOT EXISTS verification_status TEXT DEFAULT 'unsubmitted';
-- verification_status: 'unsubmitted' | 'pending' | 'under_review' | 'verified' | 'rejected'
ALTER TABLE workers ADD COLUMN IF NOT EXISTS verification_type TEXT;
-- verification_type: 'aadhaar' | 'pan' | 'trade_license' | 'skill_certificate'
ALTER TABLE workers ADD COLUMN IF NOT EXISTS verification_notes TEXT;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS verification_submitted_at TIMESTAMPTZ;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS verification_reviewed_at TIMESTAMPTZ;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS profile_completeness INT DEFAULT 40;

CREATE INDEX IF NOT EXISTS idx_workers_verification_status ON workers(verification_status);

-- ─────────────────────────────────────────────────────────────────────
-- 2. ENHANCE: users (Customer Profile & Voice Assistant Settings)
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS locality TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS voice_settings JSONB DEFAULT '{"voice": "alloy", "speed": 1.0, "auto_speak": true}'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS language_preference TEXT DEFAULT 'hi';

-- ─────────────────────────────────────────────────────────────────────
-- 3. TABLE: customer_saved_addresses (Saved Addresses with User Ownership)
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customer_saved_addresses (
  id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  label           TEXT NOT NULL DEFAULT 'Home', -- 'Home' | 'Work' | 'Other'
  street_address  TEXT NOT NULL,
  landmark        TEXT,
  locality        TEXT NOT NULL,
  city            TEXT NOT NULL DEFAULT 'Delhi NCR',
  pincode         TEXT,
  latitude        FLOAT,
  longitude       FLOAT,
  is_default      BOOLEAN DEFAULT false,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saved_addresses_user ON customer_saved_addresses(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_addresses_default ON customer_saved_addresses(user_id, is_default);

-- ─────────────────────────────────────────────────────────────────────
-- 4. ENHANCE: reviews (Strict Booking Uniqueness & Eligibility Guard)
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS booking_id BIGINT REFERENCES bookings(id) ON DELETE CASCADE;

-- Ensure only one review per booking (prevent duplicate reviews)
CREATE UNIQUE INDEX IF NOT EXISTS uq_reviews_booking
  ON reviews (booking_id)
  WHERE booking_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reviews_booking_id ON reviews(booking_id);

-- ─────────────────────────────────────────────────────────────────────
-- 5. TABLE: blocked_users (Safety & Abuse Protection)
-- ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS blocked_users (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  blocker_id   UUID NOT NULL,
  blocker_role TEXT NOT NULL CHECK (blocker_role IN ('user', 'worker')),
  blocked_id   UUID NOT NULL,
  blocked_role TEXT NOT NULL CHECK (blocked_role IN ('user', 'worker')),
  reason       TEXT,
  created_at   TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT uq_blocker_blocked UNIQUE (blocker_id, blocked_id)
);

CREATE INDEX IF NOT EXISTS idx_blocked_blocker ON blocked_users(blocker_id);
CREATE INDEX IF NOT EXISTS idx_blocked_blocked ON blocked_users(blocked_id);

-- ─────────────────────────────────────────────────────────────────────
-- 6. ENHANCE: job_reports (Dispute & Incident Categorization)
-- ─────────────────────────────────────────────────────────────────────
ALTER TABLE job_reports ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'other';
-- category: 'inappropriate_behavior' | 'payment_dispute' | 'no_show' | 'safety_concern' | 'fraud' | 'other'

CREATE INDEX IF NOT EXISTS idx_job_reports_category ON job_reports(category);
