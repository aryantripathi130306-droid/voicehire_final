"""
VoiceHire — Automated Test Suite for Authoritative Payment Workflow
══════════════════════════════════════════════════════════════════════
Tests complete end-to-end payment requirements:
  1. Payment options evaluation (server-authoritative amount, permitted methods).
  2. Worker payout profile onboarding (validates UPI VPA, strictly rejects card numbers/CVVs).
  3. Cash on completion intent creation and explicit customer confirmation.
  4. Worker-only cash manual confirmation (role guard: only assigned worker can confirm).
  5. Customer cannot forge worker cash confirmation.
  6. Online Razorpay order creation (amount-bound in paisa, metadata binding).
  7. Dynamic amount-bound UPI QR generation (valid UPI URI & base64 QR).
  8. Cryptographic server-side signature verification (HMAC-SHA256).
  9. Tampered/fake signature rejection (remains unpaid, marks failure).
 10. Replay and idempotency protection (duplicate verification does not create duplicate payments).
 11. Payment failure and cancellation reporting.
 12. Authenticated server-side webhook with HMAC signature verification and deduplication.
 13. Cash payments strictly tagged 'cash_manual_confirmation' (never misrepresented as electronic).
 14. Invalid booking states (Cancelled/Disputed) reject payment attempts.
"""

import base64
import hashlib
import hmac
import json
import unittest
from unittest.mock import MagicMock, patch

from app import app
from backend_service import (
    PaymentManager,
    RazorpayGatewayService,
    VALID_BOOKING_TRANSITIONS,
)


class MockTableResponse:
    def __init__(self, data):
        self.data = data


class MockTableQuery:
    """In-memory PostgREST query builder for isolated payment workflow unit tests."""

    def __init__(self, data=None):
        self._data = data if data is not None else []
        self._filters = {}
        self._selected_cols = "*"
        self._last_inserted = None
        self._pending_updates = None
        self._pending_delete = False
        self._order_col = None
        self._desc = False
        self._limit = None

    def select(self, cols="*"):
        self._selected_cols = cols
        return self

    def insert(self, record):
        if isinstance(record, dict):
            new_rec = dict(record)
            if "id" not in new_rec:
                new_rec["id"] = len(self._data) + 1
            self._data.append(new_rec)
            self._last_inserted = [dict(new_rec)]
        elif isinstance(record, list):
            self._last_inserted = []
            for r in record:
                nr = dict(r)
                if "id" not in nr:
                    nr["id"] = len(self._data) + 1
                self._data.append(nr)
                self._last_inserted.append(dict(nr))
        return self

    def update(self, updates):
        self._pending_updates = dict(updates)
        return self

    def delete(self):
        self._pending_delete = True
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def neq(self, col, val):
        self._filters[f"{col}__neq"] = val
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._desc = desc
        return self

    def limit(self, count):
        self._limit = count
        return self

    def execute(self):
        if self._last_inserted is not None:
            res = list(self._last_inserted)
            self._last_inserted = None
            return MockTableResponse(res)

        matching = []
        for rec in self._data:
            match = True
            for k, v in self._filters.items():
                if k.endswith("__neq"):
                    col = k[:-5]
                    if rec.get(col) == v:
                        match = False
                        break
                else:
                    if str(rec.get(k)) != str(v):
                        match = False
                        break
            if match:
                matching.append(rec)

        if self._pending_delete:
            self._pending_delete = False
            for rec in list(matching):
                if rec in self._data:
                    self._data.remove(rec)
            return MockTableResponse([dict(r) for r in matching])

        if self._pending_updates is not None:
            updated = []
            for rec in matching:
                rec.update(self._pending_updates)
                updated.append(dict(rec))
            self._pending_updates = None
            return MockTableResponse(updated)

        if self._order_col:
            matching.sort(
                key=lambda r: str(r.get(self._order_col, "")), reverse=self._desc
            )

        res = [dict(r) for r in matching]
        if self._limit is not None:
            res = res[: self._limit]
        return MockTableResponse(res)


class MockSupabaseClient:
    def __init__(self, initial_tables=None):
        self.tables = initial_tables or {}

    def table(self, table_name):
        if table_name not in self.tables:
            self.tables[table_name] = []
        return MockTableQuery(self.tables[table_name])


class PaymentWorkflowTestCase(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test-secret-key-voicehire"
        self.client = app.test_client()

        # Seed mock database with users, workers, bookings
        self.mock_db = MockSupabaseClient(
            {
                "users": [
                    {
                        "id": "cust-1",
                        "email": "customer@example.com",
                        "name": "Jane Customer",
                        "phone": "9876543210",
                    },
                    {
                        "id": "cust-2",
                        "email": "other@example.com",
                        "name": "Other User",
                        "phone": "9123456789",
                    },
                ],
                "workers": [
                    {
                        "id": "worker-1",
                        "name": "Ramesh Sharma",
                        "phone": "9876500001",
                        "email": "ramesh@example.com",
                        "work": "Electrician",
                        "location": "Indirapuram, Ghaziabad",
                        "payout_vpa": "ramesh@oksbi",
                        "payout_account_id": "acc_ramesh123",
                        "payout_status": "active",
                    },
                    {
                        "id": "worker-2",
                        "name": "Suresh Kumar",
                        "phone": "9876500002",
                        "email": "suresh@example.com",
                        "work": "Plumber",
                        "location": "Noida Sector 62",
                        "payout_vpa": None,
                        "payout_account_id": None,
                        "payout_status": "pending",
                    },
                ],
                "bookings": [
                    {
                        "id": "book-100",
                        "user_id": "cust-1",
                        "worker_id": "worker-1",
                        "status": "Completed",
                        "total_price": 550.0,
                        "date": "2026-10-15",
                        "time_slot": "10:00 AM",
                    },
                    {
                        "id": "book-200",
                        "user_id": "cust-1",
                        "worker_id": "worker-2",
                        "status": "Completed",
                        "total_price": 400.0,
                        "date": "2026-10-15",
                        "time_slot": "02:00 PM",
                    },
                    {
                        "id": "book-300",
                        "user_id": "cust-1",
                        "worker_id": "worker-1",
                        "status": "Cancelled",
                        "total_price": 300.0,
                        "date": "2026-10-15",
                        "time_slot": "04:00 PM",
                    },
                ],
                "payments": [],
                "payment_webhooks": [],
                "notifications": [],
                "booking_status_history": [],
            }
        )

        self.supabase_patcher = patch("app.supabase", self.mock_db)
        self.supabase_patcher.start()

    def tearDown(self):
        self.supabase_patcher.stop()

    # ─────────────────────────────────────────────────────────────
    # 1. Gateway Configuration & VPA Validation Tests
    # ─────────────────────────────────────────────────────────────

    def test_vpa_validation_accepts_valid_vpa(self):
        """VPA validation passes for standard UPI addresses."""
        valid_vpas = [
            "ramesh@oksbi",
            "9876543210@paytm",
            "john.doe@axisbank",
            "service_pro@icici",
        ]
        for vpa in valid_vpas:
            valid, msg = RazorpayGatewayService.validate_vpa(vpa)
            self.assertTrue(valid, f"Expected {vpa} to be valid: {msg}")

    def test_vpa_validation_strictly_rejects_card_numbers_and_cvvs(self):
        """VPA validation strictly rejects raw credit/debit card numbers and sensitive data."""
        invalid_inputs = [
            "4111222233334444",  # Raw 16-digit Visa card
            "4111-2222-3333-4444",  # Formatted card
            "5500 0000 0000 0004",  # Mastercard
            "123",  # CVV
            "not_an_email_or_vpa",  # Missing @
            "@bank",  # Missing username
            "user@",  # Missing handle
            "",  # Empty
        ]
        for bad_input in invalid_inputs:
            valid, msg = RazorpayGatewayService.validate_vpa(bad_input)
            self.assertFalse(valid, f"Expected {bad_input} to be rejected")

    def test_worker_payout_onboarding_api_updates_vpa(self):
        """Worker can submit valid UPI VPA and updates eligibility."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "worker-2"
            sess["role"] = "worker"
            sess["name"] = "Suresh Kumar"

        # Submit valid VPA
        res = self.client.post(
            "/api/worker/payout-profile",
            json={
                "payout_vpa": "suresh@oksbi",
                "payout_account_id": "acc_suresh99",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["payout_status"], "active")

        # Verify in database
        worker_rec = [
            w for w in self.mock_db.tables["workers"] if w["id"] == "worker-2"
        ][0]
        self.assertEqual(worker_rec["payout_vpa"], "suresh@oksbi")
        self.assertEqual(worker_rec["payout_status"], "active")

    def test_worker_payout_onboarding_rejects_card_number(self):
        """Worker submitting credit card number is blocked with explicit security error."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "worker-2"
            sess["role"] = "worker"
            sess["name"] = "Suresh Kumar"

        res = self.client.post(
            "/api/worker/payout-profile",
            json={"payout_vpa": "4242 4242 4242 4242"},
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("card numbers or CVVs", data["error"])

    # ─────────────────────────────────────────────────────────────
    # 2. Payment Options & Server-Authoritative Amount
    # ─────────────────────────────────────────────────────────────

    def test_payment_options_returns_authoritative_booking_amount(self):
        """Payment options returns the server-stored amount and permitted methods."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"
            sess["name"] = "Jane Customer"

        res = self.client.get("/api/bookings/book-100/payment-options")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["amount"], 550.0)
        self.assertTrue(data["cash_allowed"])

    def test_payment_options_explains_when_worker_payout_disabled(self):
        """When worker has not configured payout, options explain why online payment is disabled."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"
            sess["name"] = "Jane Customer"

        # book-200 worker has payout_status = 'pending'
        res = self.client.get("/api/bookings/book-200/payment-options")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data["online_allowed"])
        self.assertIn("payout configuration", data["online_disabled_reason"])

    # ─────────────────────────────────────────────────────────────
    # 3. Cash on Completion Workflow & Worker Manual Confirmation
    # ─────────────────────────────────────────────────────────────

    def test_customer_can_create_cash_payment_intent(self):
        """Customer selecting Cash creates intent and transitions booking to Payment Pending."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"
            sess["name"] = "Jane Customer"

        res = self.client.post(
            "/api/payments/create-intent",
            json={"booking_id": "book-100", "payment_method": "cash"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["payment_method"], "cash")
        self.assertEqual(data["amount"], 550.0)

        # Booking transitioned to Payment Pending
        booking = [
            b for b in self.mock_db.tables["bookings"] if b["id"] == "book-100"
        ][0]
        self.assertEqual(booking["status"], "Payment Pending")

        # Payment record stored
        payment = [
            p
            for p in self.mock_db.tables["payments"]
            if p["booking_id"] == "book-100"
        ][0]
        self.assertEqual(payment["payment_method"], "cash")
        self.assertEqual(payment["status"], "pending")

    def test_worker_can_manually_confirm_cash_payment(self):
        """Assigned worker physically confirms cash receipt, finalizing booking as Paid."""
        # 1. First customer creates cash intent
        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"

        self.client.post(
            "/api/payments/create-intent",
            json={"booking_id": "book-100", "payment_method": "cash"},
        )

        # 2. Worker confirms cash payment
        with self.client.session_transaction() as sess:
            sess["user_id"] = "worker-1"
            sess["role"] = "worker"
            sess["name"] = "Ramesh Sharma"

        res = self.client.post("/api/bookings/book-100/confirm-cash-payment")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

        # Booking status is Paid
        booking = [
            b for b in self.mock_db.tables["bookings"] if b["id"] == "book-100"
        ][0]
        self.assertEqual(booking["status"], "Paid")

        # Verification type is explicitly cash_manual_confirmation (not electronic)
        payment = [
            p
            for p in self.mock_db.tables["payments"]
            if p["booking_id"] == "book-100"
        ][0]
        self.assertEqual(payment["status"], "completed")
        self.assertEqual(
            payment["verification_type"], "cash_manual_confirmation"
        )

        # Check status history records worker manual confirmation
        histories = [
            h
            for h in self.mock_db.tables["booking_status_history"]
            if h["booking_id"] == "book-100"
        ]
        self.assertTrue(
            any("Cash payment verified on-site" in h["reason"] for h in histories)
        )

    def test_customer_cannot_confirm_cash_payment_directly(self):
        """Customer cannot call worker cash confirmation endpoint (403 forbidden)."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"

        res = self.client.post("/api/bookings/book-100/confirm-cash-payment")
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertIn("Only the assigned worker", data["error"])

    def test_wrong_worker_cannot_confirm_cash_payment(self):
        """Unassigned worker cannot confirm cash receipt on someone else's booking."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "worker-2"
            sess["role"] = "worker"

        res = self.client.post("/api/bookings/book-100/confirm-cash-payment")
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertIn("Only the assigned worker", data["error"])

    # ─────────────────────────────────────────────────────────────
    # 4. Online Razorpay Order & Dynamic Amount-Bound UPI QR
    # ─────────────────────────────────────────────────────────────

    @patch("backend_service.RazorpayGatewayService.is_gateway_configured")
    @patch("backend_service.RazorpayGatewayService.get_credentials")
    @patch("backend_service.RazorpayGatewayService.create_order")
    def test_online_intent_creation_creates_razorpay_order(
        self, mock_create_order, mock_creds, mock_is_conf
    ):
        """Online payment intent creates server-side order with amount in paisa and metadata."""
        mock_is_conf.return_value = True
        mock_creds.return_value = {
            "key_id": "rzp_test_KEY123",
            "key_secret": "test_secret_abc",
            "webhook_secret": "test_wh_secret",
            "currency": "INR",
        }
        mock_create_order.return_value = {
            "order_id": "order_RZP987654321",
            "amount": 550.0,
            "amount_paisa": 55000,
            "currency": "INR",
            "key_id": "rzp_test_KEY123",
        }

        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"

        res = self.client.post(
            "/api/payments/create-intent",
            json={"booking_id": "book-100", "payment_method": "razorpay"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["order_id"], "order_RZP987654321")
        self.assertEqual(data["amount_paisa"], 55000)

        # Payment record created with gateway_order_id
        payment = [
            p
            for p in self.mock_db.tables["payments"]
            if p["booking_id"] == "book-100"
        ][0]
        self.assertEqual(payment["gateway_order_id"], "order_RZP987654321")
        self.assertEqual(payment["status"], "pending")

    @patch("backend_service.RazorpayGatewayService.is_gateway_configured")
    @patch("backend_service.RazorpayGatewayService.get_credentials")
    @patch("backend_service.RazorpayGatewayService.create_order")
    def test_upi_intent_creates_amount_bound_qr(
        self, mock_create_order, mock_creds, mock_is_conf
    ):
        """UPI intent generates dynamic QR image bound to exact amount and payee VPA."""
        mock_is_conf.return_value = True
        mock_creds.return_value = {
            "key_id": "rzp_test_KEY123",
            "key_secret": "test_secret_abc",
            "webhook_secret": "test_wh_secret",
            "currency": "INR",
        }
        mock_create_order.return_value = {
            "order_id": "order_UPI98765",
            "amount": 550.0,
            "amount_paisa": 55000,
            "currency": "INR",
            "key_id": "rzp_test_KEY123",
        }

        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"

        res = self.client.post(
            "/api/payments/create-intent",
            json={"booking_id": "book-100", "payment_method": "upi"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("qr_image_b64", data)
        self.assertIn("upi://pay", data["upi_intent_url"])
        self.assertIn("am=550.00", data["upi_intent_url"])
        self.assertIn("pa=ramesh@oksbi", data["upi_intent_url"])

    # ─────────────────────────────────────────────────────────────
    # 5. Cryptographic Verification & Anti-Tampering Tests
    # ─────────────────────────────────────────────────────────────

    @patch("backend_service.RazorpayGatewayService.is_gateway_configured")
    @patch("backend_service.RazorpayGatewayService.get_credentials")
    def test_payment_verification_succeeds_with_valid_hmac_signature(
        self, mock_creds, mock_is_conf
    ):
        """Payment transitions to Paid and electronic_signature when HMAC-SHA256 signature is valid."""
        mock_is_conf.return_value = True
        key_secret = "test_secret_key_12345"
        mock_creds.return_value = {
            "key_id": "rzp_test_KEY123",
            "key_secret": key_secret,
            "webhook_secret": "test_wh_secret",
            "currency": "INR",
        }

        order_id = "order_VALID123"
        payment_id = "pay_VALID999"

        # Compute authentic Razorpay signature: HMAC-SHA256(order_id + "|" + payment_id, key_secret)
        msg = f"{order_id}|{payment_id}".encode("utf-8")
        authentic_signature = hmac.new(
            key_secret.encode("utf-8"), msg, hashlib.sha256
        ).hexdigest()

        # Seed payment intent
        self.mock_db.tables["payments"].append(
            {
                "id": "pay-rec-1",
                "booking_id": "book-100",
                "user_id": "cust-1",
                "amount": 550.0,
                "payment_method": "razorpay",
                "status": "pending",
                "gateway_order_id": order_id,
            }
        )

        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"

        res = self.client.post(
            "/api/payments/verify",
            json={
                "booking_id": "book-100",
                "gateway_order_id": order_id,
                "gateway_payment_id": payment_id,
                "gateway_signature": authentic_signature,
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

        # Booking transitioned to Paid
        booking = [
            b for b in self.mock_db.tables["bookings"] if b["id"] == "book-100"
        ][0]
        self.assertEqual(booking["status"], "Paid")

        # Payment record finalized with electronic_signature
        pay_rec = [
            p
            for p in self.mock_db.tables["payments"]
            if p["gateway_order_id"] == order_id
        ][0]
        self.assertEqual(pay_rec["status"], "completed")
        self.assertEqual(
            pay_rec["verification_type"], "electronic_signature"
        )
        self.assertEqual(pay_rec["gateway_payment_id"], payment_id)

    @patch("backend_service.RazorpayGatewayService.is_gateway_configured")
    @patch("backend_service.RazorpayGatewayService.get_credentials")
    def test_payment_verification_rejects_tampered_signature(
        self, mock_creds, mock_is_conf
    ):
        """Tampered or invalid signature is rejected with 400 and booking remains unpaid."""
        mock_is_conf.return_value = True
        mock_creds.return_value = {
            "key_id": "rzp_test_KEY123",
            "key_secret": "authentic_secret",
            "webhook_secret": "wh_sec",
            "currency": "INR",
        }

        order_id = "order_FORGED123"
        payment_id = "pay_FORGED999"
        forged_signature = "bad_signature_0000000000000000000000000000000000000000"

        self.mock_db.tables["payments"].append(
            {
                "id": "pay-rec-2",
                "booking_id": "book-100",
                "user_id": "cust-1",
                "amount": 550.0,
                "payment_method": "razorpay",
                "status": "pending",
                "gateway_order_id": order_id,
            }
        )

        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"

        res = self.client.post(
            "/api/payments/verify",
            json={
                "booking_id": "book-100",
                "gateway_order_id": order_id,
                "gateway_payment_id": payment_id,
                "gateway_signature": forged_signature,
            },
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("rejected", data["error"])

        # Booking MUST NOT be marked Paid!
        booking = [
            b for b in self.mock_db.tables["bookings"] if b["id"] == "book-100"
        ][0]
        self.assertNotEqual(booking["status"], "Paid")

        # Payment record marked failed
        pay_rec = [
            p
            for p in self.mock_db.tables["payments"]
            if p["gateway_order_id"] == order_id
        ][0]
        self.assertEqual(pay_rec["status"], "failed")

    @patch("backend_service.RazorpayGatewayService.is_gateway_configured")
    @patch("backend_service.RazorpayGatewayService.get_credentials")
    def test_duplicate_verification_is_idempotent(
        self, mock_creds, mock_is_conf
    ):
        """Repeated verification calls return 200 idempotently without duplicate records."""
        mock_is_conf.return_value = True
        key_secret = "secret_idempotency_test"
        mock_creds.return_value = {
            "key_id": "rzp_key",
            "key_secret": key_secret,
            "webhook_secret": "wh_sec",
            "currency": "INR",
        }

        order_id = "order_IDEMP_1"
        payment_id = "pay_IDEMP_1"
        sig = hmac.new(
            key_secret.encode("utf-8"),
            f"{order_id}|{payment_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        self.mock_db.tables["payments"].append(
            {
                "id": "pay-rec-idem",
                "booking_id": "book-100",
                "user_id": "cust-1",
                "amount": 550.0,
                "payment_method": "razorpay",
                "status": "pending",
                "gateway_order_id": order_id,
            }
        )

        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"

        payload = {
            "booking_id": "book-100",
            "gateway_order_id": order_id,
            "gateway_payment_id": payment_id,
            "gateway_signature": sig,
        }

        # First verification
        res1 = self.client.post("/api/payments/verify", json=payload)
        self.assertEqual(res1.status_code, 200)

        # Second verification (replay / duplicate webhook)
        res2 = self.client.post("/api/payments/verify", json=payload)
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json()["already_settled"])

        # No duplicate payment records created
        matching = [
            p
            for p in self.mock_db.tables["payments"]
            if p["gateway_order_id"] == order_id
        ]
        self.assertEqual(len(matching), 1)

    # ─────────────────────────────────────────────────────────────
    # 6. Payment Failure Reporting
    # ─────────────────────────────────────────────────────────────

    def test_payment_failure_reporting(self):
        """Gateway failure reports record failure code and keep booking accessible for retry."""
        order_id = "order_FAIL_123"
        self.mock_db.tables["payments"].append(
            {
                "id": "pay-fail",
                "booking_id": "book-100",
                "user_id": "cust-1",
                "amount": 550.0,
                "payment_method": "razorpay",
                "status": "pending",
                "gateway_order_id": order_id,
            }
        )

        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"

        res = self.client.post(
            "/api/payments/fail",
            json={
                "booking_id": "book-100",
                "gateway_order_id": order_id,
                "error_code": "BAD_REQUEST_ERROR",
                "error_description": "Payment was cancelled by user on bank page",
            },
        )
        self.assertEqual(res.status_code, 200)
        pay_rec = [
            p
            for p in self.mock_db.tables["payments"]
            if p["gateway_order_id"] == order_id
        ][0]
        self.assertEqual(pay_rec["status"], "failed")
        self.assertEqual(pay_rec["error_code"], "BAD_REQUEST_ERROR")

    # ─────────────────────────────────────────────────────────────
    # 7. Server-Side Webhook & Signature Deduplication
    # ─────────────────────────────────────────────────────────────

    @patch("backend_service.RazorpayGatewayService.is_gateway_configured")
    @patch("backend_service.RazorpayGatewayService.get_credentials")
    def test_webhook_handler_verifies_signature_and_deduplicates(
        self, mock_creds, mock_is_conf
    ):
        """Webhook verifies HMAC signature and processes payment.captured event."""
        mock_is_conf.return_value = True
        wh_secret = "whsec_test_secret_abc"
        mock_creds.return_value = {
            "key_id": "rzp_key",
            "key_secret": "k_sec",
            "webhook_secret": wh_secret,
            "currency": "INR",
        }

        order_id = "order_WH_123"
        payment_id = "pay_WH_999"

        self.mock_db.tables["payments"].append(
            {
                "id": "pay-wh",
                "booking_id": "book-100",
                "user_id": "cust-1",
                "amount": 550.0,
                "payment_method": "razorpay",
                "status": "pending",
                "gateway_order_id": order_id,
            }
        )

        webhook_payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": 55000,
                        "status": "captured",
                        "notes": {"booking_id": "book-100"},
                    }
                }
            },
        }

        raw_body = json.dumps(webhook_payload).encode("utf-8")
        sig = hmac.new(wh_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

        # Send webhook
        res = self.client.post(
            "/api/payments/webhook",
            data=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )
        self.assertEqual(res.status_code, 200)

        # Booking marked Paid
        booking = [
            b for b in self.mock_db.tables["bookings"] if b["id"] == "book-100"
        ][0]
        self.assertEqual(booking["status"], "Paid")

        # Webhook event logged in payment_webhooks
        logged_events = self.mock_db.tables["payment_webhooks"]
        self.assertEqual(len(logged_events), 1)
        self.assertEqual(logged_events[0]["event"], "payment.captured")

        # Replaying the exact same webhook event -> deduplicated safely
        res2 = self.client.post(
            "/api/payments/webhook",
            data=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json()["duplicate"])

    # ─────────────────────────────────────────────────────────────
    # 8. Invalid Booking State Handling
    # ─────────────────────────────────────────────────────────────

    def test_payment_intent_rejected_on_cancelled_booking(self):
        """Payment intent creation is rejected if the booking is cancelled."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "cust-1"
            sess["role"] = "user"

        res = self.client.post(
            "/api/payments/create-intent",
            json={"booking_id": "book-300", "payment_method": "cash"},
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn("not eligible for payment", data["error"])


if __name__ == "__main__":
    unittest.main()
