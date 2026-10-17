"""
VoiceHire — Automated Test Suite for Booking-Bound QR Check-In
═══════════════════════════════════════════════════════════════════
Validates all requirements for booking-bound QR and PIN check-in:
  1. Cryptographic token generation and zero-PII security in QR payload.
  2. Successful worker scan and server-confirmed transition to Work Started.
  3. Replay attack rejection (tokens single-use only).
  4. Expired token rejection.
  5. Wrong booking token rejection (booking ID bound cryptographically).
  6. Wrong worker rejection (only assigned worker can check in).
  7. Unauthorized and unauthenticated access rejection.
  8. Customer cannot execute worker QR check-in endpoint.
  9. Repeated scans on already-started booking rejected.
 10. Check-in on cancelled booking rejected.
 11. Sliding window rate limiter (429 Too Many Requests after threshold).
 12. Camera-less alternative: 6-digit dynamic PIN verification and replay rejection.
 13. Camera-less alternative: Explicit customer arrival confirmation endpoint.
 14. Check-in token dynamic refresh endpoint security.
 15. Check-in event logging and status history audit trail.
"""

import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import patch

from app import app
from backend_service import (
    BookingCheckinSecurity,
    CheckinEventLogger,
    CheckinRateLimiter,
)


class MockTableQuery:
    """In-memory PostgREST query builder for isolated QR check-in unit tests."""
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
            if 'id' not in new_rec:
                new_rec['id'] = len(self._data) + 1
            self._data.append(new_rec)
            self._last_inserted = [dict(new_rec)]
        elif isinstance(record, list):
            self._last_inserted = []
            for r in record:
                nr = dict(r)
                if 'id' not in nr:
                    nr['id'] = len(self._data) + 1
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
            matching.sort(key=lambda r: str(r.get(self._order_col, '')), reverse=self._desc)

        res = [dict(r) for r in matching]
        if self._limit is not None:
            res = res[:self._limit]
        return MockTableResponse(res)


class MockTableResponse:
    def __init__(self, data):
        self.data = data


class MockDatabase:
    """Mock Supabase client providing isolated in-memory tables."""
    def __init__(self):
        self.tables = {
            "users": [],
            "workers": [],
            "bookings": [],
            "booking_status_history": [],
            "booking_checkin_events": [],
            "notifications": [],
            "audit_logs": []
        }

    def table(self, table_name):
        if table_name not in self.tables:
            self.tables[table_name] = []
        return MockTableQuery(self.tables[table_name])


class TestBookingBoundQRCheckin(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key-voicehire-123'
        self.client = app.test_client()
        self.mock_db = MockDatabase()

        # Seed users and workers
        self.customer = {
            "id": 101,
            "name": "Ananya Roy",
            "email": "ananya@example.com",
            "phone": "9876543210",
            "role": "user"
        }
        self.worker1 = {
            "id": 501,
            "name": "Ramesh Kumar",
            "phone": "9123456780",
            "work": "Electrician",
            "role": "worker"
        }
        self.worker2 = {
            "id": 502,
            "name": "Suresh Verma",
            "phone": "9123456789",
            "work": "Plumber",
            "role": "worker"
        }
        self.mock_db.tables["users"].append(self.customer)
        self.mock_db.tables["workers"].extend([self.worker1, self.worker2])

        # Seed confirmed booking
        self.booking = {
            "id": 1,
            "customer_id": 101,
            "worker_id": 501,
            "status": "Booked",
            "date": "2026-10-16",
            "time_slot": "10:00 AM",
            "service_category": "Electrical",
            "total_price": 500,
            "created_at": "2026-10-15T10:00:00Z"
        }
        self.mock_db.tables["bookings"].append(self.booking)

        # Patch Supabase client globally in app
        self.patcher_app = patch('app.supabase', self.mock_db)
        self.patcher_app.start()

        # Reset security rate limiter and consumed hashes
        BookingCheckinSecurity.reset_for_testing()

    def tearDown(self):
        self.patcher_app.stop()
        BookingCheckinSecurity.reset_for_testing()

    def test_01_qr_payload_security_zero_pii(self):
        """Security: Verify QR credentials and payload contain zero sensitive PII."""
        creds = BookingCheckinSecurity.generate_checkin_credentials(booking_id=1, ttl_seconds=300)

        # 1. Structure assertions
        self.assertIn("token", creds)
        self.assertIn("code", creds)
        self.assertIn("expires_at", creds)
        self.assertIn("qr_payload", creds)
        self.assertEqual(creds["ttl_seconds"], 300)

        # 2. Token format: nonce.exp.sig
        parts = creds["token"].split(".")
        self.assertEqual(len(parts), 3, "Token must be composed of nonce.exp.sig")

        # 3. Numeric fallback PIN format: exactly 6 digits
        self.assertEqual(len(creds["code"]), 6)
        self.assertTrue(creds["code"].isdigit())

        # 4. Zero sensitive PII check
        qr_str = json.dumps(creds["qr_payload"])
        for forbidden in ["Ananya", "Roy", "9876543210", "Ramesh", "Kumar", "9123456780", "password", "email", "address"]:
            self.assertNotIn(forbidden, qr_str.lower(), f"Forbidden PII '{forbidden}' found in QR payload")
            self.assertNotIn(forbidden, creds["token"].lower(), f"Forbidden PII '{forbidden}' found in QR token")

    def test_02_valid_worker_qr_checkin_success(self):
        """Workflow: Assigned worker successfully scans customer QR and starts job."""
        creds = BookingCheckinSecurity.generate_checkin_credentials(booking_id=1, ttl_seconds=300)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 501
            sess['role'] = 'worker'

        res = self.client.post("/api/bookings/1/checkin", json={
            "token": creds["token"],
            "lat": 28.6139,
            "lng": 77.2090
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "Work Started")
        self.assertIn("Check-in verified successfully", data["message"])

        # Verify booking status updated in DB
        b = self.mock_db.tables["bookings"][0]
        self.assertEqual(b["status"], "Work Started")

        # Verify check-in event logged
        events = self.mock_db.tables["booking_checkin_events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "success")
        self.assertEqual(events[0]["event_type"], "checkin_verified")
        self.assertIsNotNone(events[0]["token_hash"])

        # Verify status history audit trail
        history = self.mock_db.tables["booking_status_history"]
        self.assertTrue(any(h["new_status"] == "Work Started" for h in history))

    def test_03_replay_attack_rejected(self):
        """Security: Same QR token cannot be consumed twice (replay prevention)."""
        creds = BookingCheckinSecurity.generate_checkin_credentials(booking_id=1, ttl_seconds=300)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 501
            sess['role'] = 'worker'

        # First consumption
        res1 = self.client.post("/api/bookings/1/checkin", json={"token": creds["token"]})
        self.assertEqual(res1.status_code, 200)

        # Attempt to reset status to Booked to simulate replay on another/reopened booking
        self.mock_db.tables["bookings"][0]["status"] = "Booked"

        # Replay attempt
        res2 = self.client.post("/api/bookings/1/checkin", json={"token": creds["token"]})
        self.assertEqual(res2.status_code, 403)
        self.assertIn("already been consumed", res2.get_json()["error"])

    def test_04_expired_token_rejected(self):
        """Security: Expired QR token is rejected."""
        # Generate token with negative TTL (already expired)
        creds = BookingCheckinSecurity.generate_checkin_credentials(booking_id=1, ttl_seconds=-60)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 501
            sess['role'] = 'worker'

        res = self.client.post("/api/bookings/1/checkin", json={"token": creds["token"]})
        self.assertEqual(res.status_code, 403)
        self.assertIn("expired", res.get_json()["error"].lower())

        # Verify failed check-in event logged
        failed_events = [e for e in self.mock_db.tables["booking_checkin_events"] if e["status"] == "failed"]
        self.assertEqual(len(failed_events), 1)

    def test_05_wrong_booking_token_rejected(self):
        """Security: Token generated for Booking 1 cannot be used to check into Booking 2."""
        # Create second booking assigned to worker 501
        booking2 = {
            "id": 2,
            "customer_id": 101,
            "worker_id": 501,
            "status": "Booked",
            "date": "2026-10-16",
            "time_slot": "02:00 PM",
            "service_category": "Electrical",
            "total_price": 600,
            "created_at": "2026-10-15T10:00:00Z"
        }
        self.mock_db.tables["bookings"].append(booking2)

        # Token created for booking 1
        creds_for_booking_1 = BookingCheckinSecurity.generate_checkin_credentials(booking_id=1, ttl_seconds=300)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 501
            sess['role'] = 'worker'

        # Attempt to scan for booking 2 using token from booking 1
        res = self.client.post("/api/bookings/2/checkin", json={"token": creds_for_booking_1["token"]})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Invalid check-in QR code signature or wrong booking", res.get_json()["error"])

    def test_06_wrong_worker_rejected(self):
        """Security: Worker 2 cannot check in for Worker 1's assigned booking."""
        creds = BookingCheckinSecurity.generate_checkin_credentials(booking_id=1, ttl_seconds=300)

        # Worker 502 signs in (not assigned to booking 1)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 502
            sess['role'] = 'worker'

        res = self.client.post("/api/bookings/1/checkin", json={"token": creds["token"]})
        self.assertEqual(res.status_code, 403)
        self.assertIn("Unauthorized: Only the assigned worker", res.get_json()["error"])

        # Status must remain Booked
        self.assertEqual(self.mock_db.tables["bookings"][0]["status"], "Booked")

    def test_07_unauthenticated_and_customer_scan_rejected(self):
        """Security: Unauthenticated users and customers cannot invoke the worker scan endpoint."""
        creds = BookingCheckinSecurity.generate_checkin_credentials(booking_id=1, ttl_seconds=300)

        # 1. Unauthenticated (no session)
        res_anon = self.client.post("/api/bookings/1/checkin", json={"token": creds["token"]})
        self.assertEqual(res_anon.status_code, 401)

        # 2. Customer signs in (customer cannot check themselves in via worker scan)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 101
            sess['role'] = 'user'

        res_cust = self.client.post("/api/bookings/1/checkin", json={"token": creds["token"]})
        self.assertEqual(res_cust.status_code, 403)
        self.assertIn("Unauthorized: Only the assigned worker", res_cust.get_json()["error"])

    def test_08_repeated_scans_after_work_started_rejected(self):
        """Workflow: Attempting check-in when work has already started is rejected."""
        self.mock_db.tables["bookings"][0]["status"] = "Work Started"

        creds = BookingCheckinSecurity.generate_checkin_credentials(booking_id=1, ttl_seconds=300)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 501
            sess['role'] = 'worker'

        res = self.client.post("/api/bookings/1/checkin", json={"token": creds["token"]})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Work has already started", res.get_json()["error"])

    def test_09_checkin_on_cancelled_booking_rejected(self):
        """Workflow: Attempting check-in on a cancelled booking is rejected."""
        self.mock_db.tables["bookings"][0]["status"] = "Cancelled"

        creds = BookingCheckinSecurity.generate_checkin_credentials(booking_id=1, ttl_seconds=300)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 501
            sess['role'] = 'worker'

        res = self.client.post("/api/bookings/1/checkin", json={"token": creds["token"]})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Booking has been cancelled", res.get_json()["error"])

    def test_10_rate_limiter_blocks_brute_force(self):
        """Security: 5 rapid failed scans trigger 429 rate limit."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 501
            sess['role'] = 'worker'

        # Send 5 invalid scan attempts
        for i in range(5):
            res = self.client.post("/api/bookings/1/checkin", json={"token": f"invalid-token-{i}"})
            self.assertEqual(res.status_code, 403)

        # 6th attempt should be blocked by rate limiter
        res_blocked = self.client.post("/api/bookings/1/checkin", json={"token": "another-token"})
        self.assertEqual(res_blocked.status_code, 429)
        self.assertIn("Too many check-in attempts", res_blocked.get_json()["error"])

    def test_11_camera_less_fallback_6digit_pin_success_and_replay(self):
        """Fallback: 6-digit numeric PIN verification for devices without camera."""
        creds = BookingCheckinSecurity.generate_checkin_credentials(booking_id=1, ttl_seconds=300)
        valid_pin = creds["code"]

        with self.client.session_transaction() as sess:
            sess['user_id'] = 501
            sess['role'] = 'worker'

        # 1. Invalid PIN rejected
        res_bad = self.client.post("/api/bookings/1/checkin", json={"code": "000000"})
        self.assertEqual(res_bad.status_code, 403)
        self.assertIn("Invalid or expired 6-digit check-in code", res_bad.get_json()["error"])

        # 2. Malformed PIN rejected
        res_malformed = self.client.post("/api/bookings/1/checkin", json={"code": "123"})
        self.assertEqual(res_malformed.status_code, 403)
        self.assertIn("Verification code must be exactly 6 digits", res_malformed.get_json()["error"])

        # 3. Valid PIN succeeds
        res_good = self.client.post("/api/bookings/1/checkin", json={"code": valid_pin})
        self.assertEqual(res_good.status_code, 200)
        self.assertEqual(res_good.get_json()["status"], "Work Started")

        # 4. PIN replay rejected
        self.mock_db.tables["bookings"][0]["status"] = "Booked"
        res_replay = self.client.post("/api/bookings/1/checkin", json={"code": valid_pin})
        self.assertEqual(res_replay.status_code, 403)
        self.assertIn("already been consumed", res_replay.get_json()["error"])

    def test_12_explicit_customer_arrival_confirmation(self):
        """Fallback: Explicit customer arrival confirmation endpoint without camera."""
        # 1. Non-customer cannot confirm
        with self.client.session_transaction() as sess:
            sess['user_id'] = 501
            sess['role'] = 'worker'

        res_worker = self.client.post("/api/bookings/1/confirm-checkin")
        self.assertEqual(res_worker.status_code, 403)
        self.assertIn("Only the assigned customer", res_worker.get_json()["error"])

        # 2. Assigned customer confirms arrival directly
        with self.client.session_transaction() as sess:
            sess['user_id'] = 101
            sess['role'] = 'user'

        res_cust = self.client.post("/api/bookings/1/confirm-checkin")
        self.assertEqual(res_cust.status_code, 200)
        self.assertEqual(res_cust.get_json()["status"], "Work Started")
        self.assertEqual(self.mock_db.tables["bookings"][0]["status"], "Work Started")

        # Verify check-in event logged
        events = self.mock_db.tables["booking_checkin_events"]
        self.assertTrue(any(e["status"] == "success" for e in events))

    def test_13_dynamic_checkin_token_refresh(self):
        """Security: Participants can refresh token; non-participants are rejected."""
        # 1. Non-participant rejected
        with self.client.session_transaction() as sess:
            sess['user_id'] = 999
            sess['role'] = 'user'

        res_unauth = self.client.get("/api/bookings/1/checkin-token")
        self.assertEqual(res_unauth.status_code, 403)

        # 2. Assigned customer can refresh
        with self.client.session_transaction() as sess:
            sess['user_id'] = 101
            sess['role'] = 'user'

        res_refresh = self.client.get("/api/bookings/1/checkin-token")
        self.assertEqual(res_refresh.status_code, 200)
        data = res_refresh.get_json()
        self.assertIn("token", data)
        self.assertIn("code", data)
        self.assertIn("qr_b64", data)
        self.assertIn("expires_at", data)


if __name__ == '__main__':
    unittest.main()
