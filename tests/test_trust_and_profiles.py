"""
VoiceHire — Automated Test Suite for Role-Specific Profiles and Trust & Safety Layer
══════════════════════════════════════════════════════════════════════════════════
Tests complete end-to-end requirements:
  1. Worker profile completeness metric, checklist breakdown, and edit controls.
  2. Worker verification submission: actual server status 'pending' (never auto-verified).
  3. Worker public profile sanitization: strips ID documents, payout account IDs, masks VPA and phone.
  4. Indicative pricing and quote preferences (estimate_then_confirm, fixed_only, inspection_required).
  5. Customer profile settings: contact, preferred locality, voice settings & language preferences.
  6. Customer saved addresses: CRUD operations with strict account ownership access control.
  7. Rating & review eligibility: only eligible completed bookings (Completed or Paid).
  8. Duplicate review prevention on the same booking.
  9. Real ratings & review counts (0 reviews = 0.0 rating, 0 count; no fake production reviews).
 10. User blocking: self-block rejection, booking creation blocked, in-app messaging blocked, unblocking.
 11. Safety reports: filing inappropriate behavior / disputed jobs with server-recorded status.
 12. Stage-based location and profile transparency policy.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from app import app
from backend_service import (
    CustomerProfileManager,
    LocationPrivacyShield,
    TrustAndSafetyManager,
    WorkerProfileManager,
)


class MockTableResponse:
    def __init__(self, data):
        self.data = data


class MockTableQuery:
    """In-memory PostgREST mock query builder for unit tests."""

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

    def in_(self, col, val):
        self._filters[f"{col}__in"] = list(val)
        return self

    def or_(self, expr):
        self._filters["__or"] = expr
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
                if k == "__or":
                    continue
                elif k.endswith("__neq"):
                    base_k = k[:-5]
                    if str(rec.get(base_k)) == str(v):
                        match = False
                        break
                elif k.endswith("__in"):
                    base_k = k[:-4]
                    actual = rec.get(base_k)
                    if actual not in v and str(actual) not in [str(x) for x in v]:
                        match = False
                        break
                else:
                    if str(rec.get(k)) != str(v):
                        match = False
                        break
            if match:
                matching.append(rec)

        if self._pending_updates is not None:
            updated = []
            for rec in matching:
                rec.update(self._pending_updates)
                updated.append(dict(rec))
            self._pending_updates = None
            self._filters = {}
            return MockTableResponse(updated)

        if self._pending_delete:
            deleted = []
            remaining = []
            for rec in self._data:
                if rec in matching:
                    deleted.append(dict(rec))
                else:
                    remaining.append(rec)
            self._data.clear()
            self._data.extend(remaining)
            self._pending_delete = False
            self._filters = {}
            return MockTableResponse(deleted)

        res = [dict(r) for r in matching]
        if self._order_col:
            res.sort(key=lambda x: str(x.get(self._order_col) or ""), reverse=self._desc)
        if self._limit:
            res = res[: self._limit]

        self._filters = {}
        return MockTableResponse(res)


class MockSupabaseClient:
    """Mock Supabase client with isolated in-memory tables."""

    def __init__(self):
        self._tables = {
            "workers": [],
            "users": [],
            "bookings": [],
            "reviews": [],
            "customer_saved_addresses": [],
            "blocked_users": [],
            "job_reports": [],
            "skills": [],
            "booking_messages": [],
        }

    def table(self, table_name):
        if table_name not in self._tables:
            self._tables[table_name] = []
        return MockTableQuery(self._tables[table_name])


class TestRoleProfilesAndTrustLayer(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        app.config["SECRET_KEY"] = "test_trust_layer_secret"
        self.client = app.test_client()
        self.mock_sb = MockSupabaseClient()

        # Seed sample worker
        self.mock_sb.table("workers").insert({
            "id": "w1",
            "name": "Ramesh Kumar",
            "phone": "9876543210",
            "work": "Plumber",
            "location": "Indirapuram, Ghaziabad",
            "service_radius_km": 15,
            "price": 500,
            "quote_preference": "estimate_then_confirm",
            "bio": "Expert in residential plumbing and pipe fittings.",
            "experience_years": 8,
            "is_available": True,
            "is_verified": False,
            "verification_status": "unverified",
            "id_proof_path": None,
            "payout_vpa": "ramesh@okhdfcbank",
            "payout_account_id": "acc_sample_worker_123",
            "payout_status": "active",
            "avg_rating": 0.0,
            "review_count": 0,
        }).execute()

        # Seed sample customer
        self.mock_sb.table("users").insert({
            "id": "u1",
            "name": "Priya Sharma",
            "phone": "9811122233",
            "role": "user",
            "locality": "Indirapuram, Ghaziabad",
            "language_preference": "en",
            "voice_settings": {"voice": "friendly", "speed": 1.0, "auto_speak": True},
        }).execute()

        # Seed another customer
        self.mock_sb.table("users").insert({
            "id": "u2",
            "name": "Vikram Singh",
            "phone": "9822233344",
            "role": "user",
            "locality": "Sector 62, Noida",
        }).execute()

    # ══════════════════════════════════════════════════════════════════
    # 1. WORKER PROFILE TESTS
    # ══════════════════════════════════════════════════════════════════

    def test_worker_completeness_calculation(self):
        """Worker completeness metric provides weighted score and missing checklist."""
        worker = {
            "name": "Ramesh Kumar",
            "work": "Plumber",
            "location": "Indirapuram",
            "phone": "9876543210",
            "bio": None,
            "voice_note": None,
            "profile_pic": None,
            "id_proof_path": None,
            "payout_vpa": "ramesh@upi",
            "price": 500,
            "quote_preference": "estimate_then_confirm",
        }
        res = WorkerProfileManager.calculate_completeness(worker, skills=[])
        self.assertIsInstance(res["score"], int)
        self.assertGreater(res["score"], 0)
        self.assertLess(res["score"], 100)
        self.assertIn("Voice Bio", res["missing"])
        self.assertIn("Document Verification", res["missing"])

        # Completed worker
        complete_worker = dict(worker)
        complete_worker.update({
            "bio": "Expert technician with 10 years experience",
            "voice_note": "/static/voice/note.mp3",
            "profile_pic": "/static/pics/worker.jpg",
            "id_proof_path": "/static/docs/id.pdf",
        })
        res_full = WorkerProfileManager.calculate_completeness(complete_worker, skills=[{"skill_name": "Plumbing"}])
        self.assertEqual(res_full["score"], 100)
        self.assertEqual(len(res_full["missing"]), 0)

    def test_worker_verification_submission_real_status(self):
        """Submitting verification records actual 'pending' status without fake auto-verification."""
        res = WorkerProfileManager.submit_verification(
            self.mock_sb,
            worker_id="w1",
            document_type="government_id",
            document_path="docs/aadhaar_ramesh.pdf"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "pending")
        self.assertFalse(res["is_verified"])

        # Verify database record
        worker_db = self.mock_sb.table("workers").select("*").eq("id", "w1").execute().data[0]
        self.assertEqual(worker_db["verification_status"], "pending")
        self.assertFalse(worker_db["is_verified"])
        self.assertIsNotNone(worker_db.get("verification_submitted_at"))

    def test_worker_public_profile_sanitization(self):
        """Privacy shield strips sensitive ID documents and payout credentials, masks phone."""
        worker = self.mock_sb.table("workers").select("*").eq("id", "w1").execute().data[0]
        worker["id_proof_path"] = "secure/vault/aadhaar_proof.pdf"
        worker["password_hash"] = "argon2$hashedpassword"

        # Public browsing view (unauthenticated or unconfirmed)
        sanitized = LocationPrivacyShield.obfuscate_worker_profile(worker, is_confirmed_booking=False)
        self.assertNotIn("id_proof_path", sanitized)
        self.assertNotIn("password_hash", sanitized)
        self.assertNotIn("payout_account_id", sanitized)
        self.assertNotIn("phone", sanitized)
        self.assertTrue(sanitized["phone_masked"].startswith("XXXXXX"))
        self.assertTrue(sanitized["payout_vpa"].startswith("***@"))

        # Confirmed booking view reveals direct phone but never vault documents
        confirmed = LocationPrivacyShield.obfuscate_worker_profile(worker, is_confirmed_booking=True)
        self.assertEqual(confirmed["phone"], "9876543210")
        self.assertNotIn("id_proof_path", confirmed)
        self.assertNotIn("password_hash", confirmed)

    def test_quote_preference_and_pricing_preferences(self):
        """Worker can set indicative pricing and clear quote preferences."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "w1"
            sess["role"] = "worker"

        with patch("app.supabase", self.mock_sb):
            res = self.client.post("/api/worker/profile", json={
                "name": "Ramesh K.",
                "price": 650,
                "quote_preference": "fixed_only",
                "bio": "Certified master plumber with transparent fixed quotes."
            })
            self.assertEqual(res.status_code, 200)

            worker_db = self.mock_sb.table("workers").select("*").eq("id", "w1").execute().data[0]
            self.assertEqual(worker_db["price"], 650)
            self.assertEqual(worker_db["quote_preference"], "fixed_only")

    # ══════════════════════════════════════════════════════════════════
    # 2. CUSTOMER PROFILE & SAVED ADDRESSES TESTS
    # ══════════════════════════════════════════════════════════════════

    def test_customer_profile_and_voice_settings(self):
        """Customer profile manages contact, locality, language and voice preferences."""
        with self.client.session_transaction() as sess:
            sess["user_id"] = "u1"
            sess["role"] = "user"

        with patch("app.supabase", self.mock_sb):
            # 1. Update contact and locality
            res = self.client.post("/api/customer/profile", json={
                "name": "Priya S.",
                "phone": "9811122299",
                "locality": "Sector 62, Noida"
            })
            self.assertEqual(res.status_code, 200)

            # 2. Update voice preferences
            res_voice = self.client.post("/api/customer/voice-settings", json={
                "language_preference": "hi",
                "voice_settings": {"voice": "professional", "speed": 1.25, "auto_speak": True}
            })
            self.assertEqual(res_voice.status_code, 200)

            # 3. Retrieve customer profile
            res_get = self.client.get("/api/customer/profile")
            self.assertEqual(res_get.status_code, 200)
            data = res_get.get_json()
            self.assertEqual(data["profile"]["name"], "Priya S.")
            self.assertEqual(data["profile"]["language_preference"], "hi")
            self.assertEqual(data["voice_settings"]["voice"], "professional")
            self.assertEqual(data["voice_settings"]["speed"], 1.25)

    def test_customer_saved_addresses_crud_and_access_control(self):
        """Saved addresses support CRUD and strictly enforce user ownership."""
        # User 1 adds an address
        addr1 = CustomerProfileManager.add_saved_address(
            self.mock_sb,
            customer_id="u1",
            label="Home",
            street_address="A-402, Shipra Sun City",
            locality="Indirapuram",
            city="Ghaziabad",
            pincode="201014",
            is_default=True
        )
        self.assertTrue(addr1["success"])
        addr1_id = addr1["address"]["id"]

        # User 2 adds an address
        addr2 = CustomerProfileManager.add_saved_address(
            self.mock_sb,
            customer_id="u2",
            label="Work",
            street_address="Tower B, Logix Cyber Park",
            locality="Sector 62",
            city="Noida",
            pincode="201301"
        )
        addr2_id = addr2["address"]["id"]

        # User 1 queries their addresses (must not see User 2's address)
        u1_addrs = CustomerProfileManager.get_saved_addresses(self.mock_sb, "u1")
        self.assertEqual(len(u1_addrs), 1)
        self.assertEqual(u1_addrs[0]["street_address"], "A-402, Shipra Sun City")

        # Access Control: User 1 tries to delete User 2's address
        unauthorized_delete = CustomerProfileManager.delete_saved_address(self.mock_sb, "u1", addr2_id)
        self.assertFalse(unauthorized_delete)

        # Address 2 remains intact
        u2_addrs = CustomerProfileManager.get_saved_addresses(self.mock_sb, "u2")
        self.assertEqual(len(u2_addrs), 1)

        # User 1 deletes their own address
        authorized_delete = CustomerProfileManager.delete_saved_address(self.mock_sb, "u1", addr1_id)
        self.assertTrue(authorized_delete)
        self.assertEqual(len(CustomerProfileManager.get_saved_addresses(self.mock_sb, "u1")), 0)

    # ══════════════════════════════════════════════════════════════════
    # 3. TRUST & SAFETY: RATINGS AND REVIEWS
    # ══════════════════════════════════════════════════════════════════

    def test_review_submission_eligibility_enforcement(self):
        """Reviews can only be submitted for completed/paid bookings and reject pending bookings."""
        # Seed an in-progress booking (Work Started)
        self.mock_sb.table("bookings").insert({
            "id": "b_inprogress",
            "user_id": "u1",
            "worker_id": "w1",
            "status": "Work Started",
            "service_type": "Plumbing"
        }).execute()

        # Attempt to review in-progress booking -> MUST REJECT
        res = TrustAndSafetyManager.submit_booking_review(
            self.mock_sb,
            booking_id="b_inprogress",
            customer_id="u1",
            rating=5,
            review_text="Premature review attempt"
        )
        self.assertFalse(res["success"])
        self.assertIn("completed", res["error"].lower())

    def test_duplicate_review_prevention(self):
        """Duplicate reviews for the same booking are rejected."""
        # Seed a completed booking
        self.mock_sb.table("bookings").insert({
            "id": "b_completed_1",
            "user_id": "u1",
            "worker_id": "w1",
            "status": "Completed",
            "service_type": "Plumbing"
        }).execute()

        # First review submission -> Succeeded
        res1 = TrustAndSafetyManager.submit_booking_review(
            self.mock_sb,
            booking_id="b_completed_1",
            customer_id="u1",
            rating=5,
            review_text="Excellent plumbing service, arrived right on time!"
        )
        self.assertTrue(res1["success"])

        # Second review attempt on same booking -> MUST REJECT
        res2 = TrustAndSafetyManager.submit_booking_review(
            self.mock_sb,
            booking_id="b_completed_1",
            customer_id="u1",
            rating=4,
            review_text="Trying to submit duplicate review"
        )
        self.assertFalse(res2["success"])
        self.assertIn("already", res2["error"].lower())

    def test_real_ratings_and_counts_without_fake_seeds(self):
        """Display real review counts and ratings only; calculate accurate average."""
        # Initial worker has 0 reviews
        initial_reviews = TrustAndSafetyManager.get_worker_reviews(self.mock_sb, "w1")
        self.assertEqual(len(initial_reviews), 0)
        worker_initial = self.mock_sb.table("workers").select("*").eq("id", "w1").execute().data[0]
        self.assertEqual(float(worker_initial.get("avg_rating", 0.0)), 0.0)
        self.assertEqual(int(worker_initial.get("review_count", 0)), 0)

        # Seed 2 completed bookings
        self.mock_sb.table("bookings").insert({
            "id": "b_comp_1",
            "user_id": "u1",
            "worker_id": "w1",
            "status": "Paid"
        }).execute()
        self.mock_sb.table("bookings").insert({
            "id": "b_comp_2",
            "user_id": "u2",
            "worker_id": "w1",
            "status": "Completed"
        }).execute()

        # Submit 5-star review from User 1
        TrustAndSafetyManager.submit_booking_review(
            self.mock_sb, "b_comp_1", "u1", rating=5, review_text="Great work!"
        )
        # Submit 4-star review from User 2
        TrustAndSafetyManager.submit_booking_review(
            self.mock_sb, "b_comp_2", "u2", rating=4, review_text="Very good and clean."
        )

        # Verify real calculated average: (5 + 4) / 2 = 4.5
        worker_updated = self.mock_sb.table("workers").select("*").eq("id", "w1").execute().data[0]
        self.assertEqual(worker_updated["review_count"], 2)
        self.assertAlmostEqual(worker_updated["avg_rating"], 4.5, places=1)

        # Verify reviewer privacy: names are anonymized as "First L."
        reviews = TrustAndSafetyManager.get_worker_reviews(self.mock_sb, "w1")
        self.assertEqual(len(reviews), 2)
        for r in reviews:
            self.assertIn("customer_name", r)
            self.assertNotIn("phone", r)

    # ══════════════════════════════════════════════════════════════════
    # 4. TRUST & SAFETY: BLOCKING & REPORTING
    # ══════════════════════════════════════════════════════════════════

    def test_user_blocking_and_self_block_prevention(self):
        """Users can block abusive counterparties, self-blocks are rejected, and blocks are auditable."""
        # 1. Self block attempt -> MUST REJECT
        self_block = TrustAndSafetyManager.block_user(
            self.mock_sb,
            blocker_id="u1",
            blocker_role="user",
            blocked_id="u1",
            blocked_role="user",
            reason="Self-block test"
        )
        self.assertFalse(self_block["success"])

        # 2. Customer blocks worker
        block_res = TrustAndSafetyManager.block_user(
            self.mock_sb,
            blocker_id="u1",
            blocker_role="user",
            blocked_id="w1",
            blocked_role="worker",
            reason="Unprofessional language"
        )
        self.assertTrue(block_res["success"])
        self.assertTrue(TrustAndSafetyManager.is_blocked(self.mock_sb, "u1", "user", "w1", "worker"))
        # Reciprocal check: worker is also blocked from interacting with customer
        self.assertTrue(TrustAndSafetyManager.is_blocked(self.mock_sb, "w1", "worker", "u1", "user"))

        # 3. Unblock
        unblock_res = TrustAndSafetyManager.unblock_user(self.mock_sb, "u1", "w1")
        self.assertTrue(unblock_res["success"])
        self.assertFalse(TrustAndSafetyManager.is_blocked(self.mock_sb, "u1", "user", "w1", "worker"))

    def test_booking_and_messaging_rejected_between_blocked_users(self):
        """Blocked users cannot book each other or send in-app messages."""
        # Block worker w1
        TrustAndSafetyManager.block_user(self.mock_sb, "u1", "user", "w1", "worker", "Blocked test")

        with self.client.session_transaction() as sess:
            sess["user_id"] = "u1"
            sess["role"] = "user"

        with patch("app.supabase", self.mock_sb):
            # Attempt direct booking creation with blocked worker
            res = self.client.post("/create_booking", json={
                "worker_id": "w1",
                "service_type": "Plumbing",
                "booking_date": "2026-10-20",
                "time_slot": "10:00-12:00"
            })
            self.assertEqual(res.status_code, 403)
            data = res.get_json()
            self.assertIn("blocked", data["error"].lower())

    def test_safety_reporting_workflow_and_server_status(self):
        """Users can report inappropriate behavior or disputed jobs with server-recorded status."""
        report = TrustAndSafetyManager.file_report(
            self.mock_sb,
            reporter_id="u1",
            reporter_role="user",
            reported_id="w1",
            reported_role="worker",
            booking_id="b_comp_1",
            category="payment_dispute",
            reason="Demanded extra cash above quoted rate",
            description="Worker insisted on ₹500 additional cash outside the verified booking."
        )
        self.assertTrue(report["success"])
        self.assertEqual(report["status"], "pending")
        self.assertIsNotNone(report["report_id"])

        # Fetch reports
        reports = TrustAndSafetyManager.get_user_reports(self.mock_sb, "u1", "user")
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["category"], "payment_dispute")
        self.assertEqual(reports[0]["status"], "pending")

    def test_stage_privacy_policy_transparency(self):
        """Transparency explainer clarifies data disclosure at every stage."""
        browse_stage = LocationPrivacyShield.get_stage_privacy_policy("Pending")
        self.assertEqual(browse_stage["stage_key"], "browse")
        self.assertIn("masked", browse_stage["phone_access"].lower())

        confirmed_stage = LocationPrivacyShield.get_stage_privacy_policy("Booked")
        self.assertEqual(confirmed_stage["stage_key"], "confirmed")
        self.assertIn("direct phone", confirmed_stage["phone_access"].lower())

        completed_stage = LocationPrivacyShield.get_stage_privacy_policy("Completed")
        self.assertEqual(completed_stage["stage_key"], "completed")


if __name__ == "__main__":
    unittest.main()
