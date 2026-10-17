-- Migration: 20261015010000_payment_gateway_and_worker_payouts.sql
-- Description: Additive schema updates for Razorpay payment gateway, worker payout onboarding, and webhook idempotency.

-- 1. Worker Payout Onboarding Fields (no raw banking credentials or cards stored)
ALTER TABLE workers ADD COLUMN IF NOT EXISTS payout_vpa TEXT;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS payout_account_id TEXT;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS payout_status TEXT DEFAULT 'unconfigured';

-- 2. Enhanced Payment Tracking on payments
ALTER TABLE payments ADD COLUMN IF NOT EXISTS gateway_order_id TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS gateway_payment_id TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS gateway_signature TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS verification_type TEXT DEFAULT 'electronic_signature';
ALTER TABLE payments ADD COLUMN IF NOT EXISTS gateway_name TEXT DEFAULT 'razorpay';
ALTER TABLE payments ADD COLUMN IF NOT EXISTS error_code TEXT;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS error_description TEXT;

CREATE INDEX IF NOT EXISTS idx_payments_gateway_order ON payments(gateway_order_id);
CREATE INDEX IF NOT EXISTS idx_payments_gateway_payment ON payments(gateway_payment_id);

-- 3. Webhook Deduplication and Idempotency Table
CREATE TABLE IF NOT EXISTS payment_webhooks (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id    TEXT UNIQUE NOT NULL,
  event_type  TEXT NOT NULL,
  payload     JSONB,
  status      TEXT DEFAULT 'processed',
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_pw_event_id ON payment_webhooks(event_id);
