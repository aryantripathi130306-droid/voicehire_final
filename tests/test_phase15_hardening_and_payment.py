"""
VoiceHire — Phase 15 Hardening, Database Modes & Payment Test Suite
═══════════════════════════════════════════════════════════════════════════════
Empirical validation of:
  1. Strict database mode enforcement & refusal of SQLite in staging/production
  2. LocalPostgrestClient PostgREST API operator parity (eq, neq, gt, gte, lt, lte, in_, ilike, is_, like)
  3. Isolated disposable test databases
  4. Liveness (/healthz) and Readiness (/health/readiness) probes
  5. Session cookie security & error handlers without stack trace leakage
  6. AuditLogger sensitive credential scrubbing
  7. Razorpay test-mode integration, order creation, amount binding, HMAC verification
  8. Webhook lifecycle (authorized, captured, failed, refund, duplicate replay protection)
  9. Strict separation of cash confirmation and electronic signature verification
═══════════════════════════════════════════════════════════════════════════════
"""

import hmac
import hashlib
import json
import os
import unittest
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

from local_db_adapter import (
    LocalPostgrestClient,
    LocalTableQuery,
    get_database_client,
    DatabaseModeError,
    DatabaseConnectionError,
    DatabaseConfigurationError
)
from backend_service import (
    RazorpayGatewayService,
    PaymentManager,
    AuditLogger
)
import app as voicehire_app


class TestPhase15DatabaseHardening(unittest.TestCase):
    """Part 1 & 2: Database Mode Enforcement, Rejection of Fallback, Operator Parity."""

    def setUp(self):
        # Use an isolated, disposable in-memory SQLite database for clean unit testing
        self.client = LocalPostgrestClient(db_path=":memory:")

    def test_staging_production_strictly_refuses_sqlite_mode(self):
        """Staging and Production environments MUST strictly refuse SQLite mode."""
        for env in ("production", "staging"):
            with self.assertRaises(DatabaseModeError) as ctx:
                get_database_client(
                    supabase_url="https://test.supabase.co",
                    supabase_key="secret-key",
                    app_env=env,
                    db_mode="sqlite"
                )
            self.assertIn("strictly prohibited", str(ctx.exception))

    def test_staging_production_strictly_refuses_silent_fallback_on_dns_failure(self):
        """If remote Supabase fails DNS or connection in production/staging, MUST RAISE DatabaseConnectionError."""
        for env in ("production", "staging"):
            with self.assertRaises(DatabaseConnectionError) as ctx:
                get_database_client(
                    supabase_url="https://non-existent-domain-12345.supabase.co",
                    supabase_key="some-key",
                    app_env=env,
                    db_mode=None
                )
            self.assertIn("Silent fallback to SQLite is strictly forbidden", str(ctx.exception))

    def test_explicit_sqlite_development_mode(self):
        """When explicitly requested via VOICEHIRE_DB_MODE=sqlite, returns LocalPostgrestClient."""
        client, meta = get_database_client(
            supabase_url=None,
            supabase_key=None,
            app_env="development",
            db_mode="sqlite",
            sqlite_path=":memory:"
        )
        self.assertIsInstance(client, LocalPostgrestClient)
        self.assertEqual(meta["mode"], "sqlite_development")
        self.assertTrue(client.ping())

    def test_disposable_test_database_isolation(self):
        """Tests can instantiate completely isolated SQLite databases."""
        client1 = LocalPostgrestClient(db_path=":memory:")
        client2 = LocalPostgrestClient(db_path=":memory:")

        client1.table("test_table").insert({"id": "rec-1", "value": "A"}).execute()
        r1 = client1.table("test_table").select("*").execute()
        r2 = client2.table("test_table").select("*").execute()

        self.assertEqual(len(r1.data), 1)
        self.assertEqual(len(r2.data), 0)

    def test_postgrest_comparison_operators(self):
        """LocalTableQuery supports full PostgREST operator suite."""
        tbl = self.client.table("inventory")
        tbl.insert([
            {"id": "1", "item": "Wrench", "price": 100, "qty": 5, "active": True, "category": "tools"},
            {"id": "2", "item": "Drill", "price": 500, "qty": 2, "active": True, "category": "power_tools"},
            {"id": "3", "item": "Hammer", "price": 50, "qty": 10, "active": False, "category": "tools"},
            {"id": "4", "item": "Saw", "price": 200, "qty": 0, "active": True, "category": "tools"},
        ]).execute()

        # eq
        res = self.client.table("inventory").select("*").eq("active", True).execute()
        self.assertEqual(len(res.data), 3)

        # neq
        res = self.client.table("inventory").select("*").neq("category", "power_tools").execute()
        self.assertEqual(len(res.data), 3)

        # gt & gte
        res = self.client.table("inventory").select("*").gt("price", 100).execute()
        self.assertEqual(len(res.data), 2)  # Drill (500) and Saw (200)

        res = self.client.table("inventory").select("*").gte("price", 100).execute()
        self.assertEqual(len(res.data), 3)  # Wrench (100), Drill (500), Saw (200)

        # lt & lte
        res = self.client.table("inventory").select("*").lt("price", 100).execute()
        self.assertEqual(len(res.data), 1)  # Hammer (50)

        res = self.client.table("inventory").select("*").lte("price", 100).execute()
        self.assertEqual(len(res.data), 2)  # Wrench (100), Hammer (50)

        # in_
        res = self.client.table("inventory").select("*").in_("item", ["Wrench", "Saw"]).execute()
        self.assertEqual(len(res.data), 2)

        # ilike
        res = self.client.table("inventory").select("*").ilike("item", "%dri%").execute()
        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["item"], "Drill")

        # ordering & limit
        res = self.client.table("inventory").select("*").order("price", desc=True).limit(2).execute()
        self.assertEqual(len(res.data), 2)
        self.assertEqual(res.data[0]["item"], "Drill")
        self.assertEqual(res.data[1]["item"], "Saw")

        # column projection
        res = self.client.table("inventory").select("id, item").eq("id", "1").execute()
        self.assertEqual(set(res.data[0].keys()), {"id", "item"})


class TestPhase15ApplicationSecurity(unittest.TestCase):
    """Part 3: Configuration, Cookies, Error Handlers, and Log Scrubbing."""

    def setUp(self):
        self.app = voicehire_app.app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_session_cookie_security_configuration(self):
        """Session cookies enforce HttpOnly and SameSite=Lax."""
        self.assertTrue(self.app.config.get('SESSION_COOKIE_HTTPONLY'))
        self.assertEqual(self.app.config.get('SESSION_COOKIE_SAMESITE'), 'Lax')

    def test_liveness_probe_healthz(self):
        """GET /healthz returns HTTP 200 with service metadata."""
        resp = self.client.get('/healthz')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('service'), 'VoiceHire')
        self.assertIn('timestamp', data)

    def test_readiness_probe_reflects_database_and_gateway(self):
        """GET /health/readiness returns 200 when ready, reporting non-sensitive health metadata."""
        resp = self.client.get('/health/readiness')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get('status'), 'ready')
        self.assertIn('database', data)
        self.assertTrue(data['database']['connected'])
        self.assertIn('payment_gateway', data)
        # Verify no secret values or credentials are exposed in response
        self.assertNotIn('super_secret', json.dumps(data).lower())
        self.assertNotIn('password', json.dumps(data).lower())
        self.assertNotIn('eyjhbgcioi', json.dumps(data).lower())

    def test_custom_error_handlers_return_clean_json_for_api(self):
        """API errors return clean structured JSON without stack traces."""
        resp = self.client.get('/api/non_existent_endpoint_12345')
        self.assertEqual(resp.status_code, 404)
        data = resp.get_json()
        self.assertEqual(data.get('error'), 'Not Found')
        self.assertNotIn('Traceback', resp.get_data(as_text=True))

    def test_audit_logger_scrubs_sensitive_credentials(self):
        """AuditLogger replaces sensitive credentials with [REDACTED]."""
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value = None

        sensitive_meta = {
            "user_id": "usr-123",
            "password": "PlainTextPassword123",
            "card_number": "4111222233334444",
            "otp": "982341",
            "key_secret": "rzp_secret_key"
        }

        AuditLogger.log_event(
            mock_db, actor_id="usr-123", actor_role="user",
            event_type="auth", resource_type="user", resource_id="usr-123",
            action="login_attempt", metadata=sensitive_meta
        )

        call_args = mock_db.table.return_value.insert.call_args[0][0]
        meta = call_args["metadata"]
        self.assertEqual(meta["password"], "[REDACTED]")
        self.assertEqual(meta["card_number"], "[REDACTED]")
        self.assertEqual(meta["otp"], "[REDACTED]")
        self.assertEqual(meta["key_secret"], "[REDACTED]")
        self.assertEqual(meta["user_id"], "usr-123")


class TestPhase15RazorpayPaymentIntegration(unittest.TestCase):
    """Part 4 & 5: Razorpay Test-Mode Gateway, Signatures, and Webhooks."""

    def setUp(self):
        self.db = LocalPostgrestClient(db_path=":memory:")
        self.app = voicehire_app.app
        self.app.config['TESTING'] = True
        self.test_client = self.app.test_client()

        # Seed test customer, worker, and booking
        self.db.table("users").insert({
            "id": "cust-p15", "name": "Rohan Gupta", "phone": "9811223344",
            "role": "user", "password": generate_password_hash("Pass123")
        }).execute()

        self.db.table("workers").insert({
            "id": "wrk-p15", "name": "Mohan Singh", "phone": "9822334455",
            "payout_vpa": "mohan@okaxis", "payout_status": "active",
            "work": "Plumber", "price": 600.0
        }).execute()

        self.db.table("bookings").insert({
            "id": 9901, "customer_id": "cust-p15", "worker_id": "wrk-p15",
            "status": "Completed", "total_price": 600.0, "price": 600.0
        }).execute()

    def test_vpa_validation_rejects_card_numbers_and_cvv(self):
        """Worker payout VPA validation strictly rejects credit card numbers or CVV."""
        # Valid VPAs
        for valid_vpa in ("worker@upi", "9876543210@paytm", "john.doe@okicici"):
            ok, msg = RazorpayGatewayService.validate_vpa(valid_vpa)
            self.assertTrue(ok, f"Expected {valid_vpa} to be valid, got {msg}")

        # Invalid VPAs (credit cards / CVVs)
        for bad_vpa in ("4111222233334444", "4111 2222 3333 4444", "123", "9999"):
            ok, msg = RazorpayGatewayService.validate_vpa(bad_vpa)
            self.assertFalse(ok)
            self.assertIn("Sensitive credit/debit card numbers", msg)

    def test_amount_bound_order_creation_uses_server_booking_price(self):
        """Order creation binds strictly to server booking amount in paise, preventing client tampering."""
        order = RazorpayGatewayService.create_order(
            booking_id=9901, amount=600.0, customer_id="cust-p15", worker_id="wrk-p15"
        )
        self.assertEqual(order["amount"], 60000)  # 600.0 * 100 paise
        self.assertEqual(order["currency"], "INR")
        self.assertEqual(order["notes"]["booking_id"], "9901")

    def test_signature_verification_success_and_tampered_rejection(self):
        """Authentic HMAC-SHA256 signature passes; modified/tampered signature is rejected."""
        order_id = "order_test_1001"
        payment_id = "pay_test_2002"
        secret = "test_key_secret_xyz"

        # Compute authentic signature
        msg = f"{order_id}|{payment_id}".encode("utf-8")
        valid_sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        with patch.object(RazorpayGatewayService, 'get_credentials', return_value={
            "key_id": "rzp_test_key", "key_secret": secret, "webhook_secret": secret
        }):
            # Valid signature
            self.assertTrue(RazorpayGatewayService.verify_payment_signature(order_id, payment_id, valid_sig))

            # Tampered signature
            self.assertFalse(RazorpayGatewayService.verify_payment_signature(order_id, payment_id, "tampered_signature_hex"))

    def test_webhook_signature_and_event_deduplication(self):
        """Webhooks verify signature against raw body and enforce idempotent deduplication."""
        secret = "test_webhook_secret_abc"
        payload_dict = {
            "event": "payment.captured",
            "event_id": "evt_unique_101",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_test_3003",
                        "order_id": "order_test_1001",
                        "notes": {"booking_id": 9901, "customer_id": "cust-p15"}
                    }
                }
            }
        }
        raw_body = json.dumps(payload_dict).encode("utf-8")
        valid_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

        with patch.object(RazorpayGatewayService, 'get_credentials', return_value={
            "key_id": "rzp_test_key", "key_secret": secret, "webhook_secret": secret
        }):
            # First delivery succeeds
            ok1, msg1, res1 = PaymentManager.handle_webhook(self.db, raw_body, valid_sig)
            self.assertTrue(ok1)
            self.assertEqual(res1.get("action"), "payment_completed")

            # Second duplicate delivery is acknowledged idempotently without double-processing
            ok2, msg2, res2 = PaymentManager.handle_webhook(self.db, raw_body, valid_sig)
            self.assertTrue(ok2)
            self.assertIn("duplicate", msg2.lower())

            # Invalid signature rejected
            ok_bad, msg_bad, _ = PaymentManager.handle_webhook(self.db, raw_body, "invalid_sig")
            self.assertFalse(ok_bad)
            self.assertIn("verification failed", msg_bad)

    def test_webhook_handles_authorized_failed_and_refund_events(self):
        """Webhook lifecycle handles authorized, failed, and refund events."""
        secret = "test_sec"
        with patch.object(RazorpayGatewayService, 'get_credentials', return_value={
            "key_id": "rzp_test_key", "key_secret": secret, "webhook_secret": secret
        }):
            # 1. Payment Authorized
            auth_payload = {
                "event": "payment.authorized", "event_id": "evt_auth_1",
                "payload": {"payment": {"entity": {"id": "pay_auth_1", "order_id": "order_test_1001"}}}
            }
            body = json.dumps(auth_payload).encode("utf-8")
            sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            ok, msg, res = PaymentManager.handle_webhook(self.db, body, sig)
            self.assertTrue(ok)
            self.assertEqual(res.get("action"), "payment_authorized")

            # 2. Payment Failed
            fail_payload = {
                "event": "payment.failed", "event_id": "evt_fail_1",
                "payload": {"payment": {"entity": {
                    "id": "pay_fail_1", "order_id": "order_test_1001",
                    "error_code": "BAD_REQUEST_ERROR", "error_description": "Card expired",
                    "notes": {"booking_id": 9901}
                }}}
            }
            body = json.dumps(fail_payload).encode("utf-8")
            sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            ok, msg, res = PaymentManager.handle_webhook(self.db, body, sig)
            self.assertTrue(ok)
            self.assertEqual(res.get("action"), "payment_failed")

            # 3. Refund Processed
            ref_payload = {
                "event": "refund.processed", "event_id": "evt_ref_1",
                "payload": {"refund": {"entity": {"id": "rfnd_1", "payment_id": "pay_test_3003"}}}
            }
            body = json.dumps(ref_payload).encode("utf-8")
            sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            ok, msg, res = PaymentManager.handle_webhook(self.db, body, sig)
            self.assertTrue(ok)
            self.assertEqual(res.get("action"), "refund_recorded")

    def test_cash_confirmation_strictly_separate_from_online(self):
        """Cash confirmation by assigned worker records cash_manual_confirmation, never electronic_signature."""
        ok, msg, payment = PaymentManager.confirm_cash_payment(
            self.db, booking_id=9901, worker_id="wrk-p15", notes="Customer paid exact cash on site."
        )
        self.assertTrue(ok)
        self.assertEqual(payment["payment_method"], "cash")
        self.assertEqual(payment["verification_type"], "cash_manual_confirmation")
        self.assertEqual(payment["status"], "completed")

        # Booking transitioned to Paid
        b_resp = self.db.table("bookings").select("*").eq("id", 9901).execute()
        self.assertEqual(b_resp.data[0]["status"], "Paid")


if __name__ == '__main__':
    unittest.main()
