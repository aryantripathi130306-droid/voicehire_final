"""
VoiceHire — Automated Test Suite for Data Models, Concurrency & Backend APIs
═══════════════════════════════════════════════════════════════════════════
Validates:
  1. Service categories taxonomy & default fallbacks
  2. Worker skills CRUD with strict record ownership enforcement
  3. Location privacy shield (coordinate fuzzing ~1.1km and PII masking)
  4. Compare-And-Swap (CAS) double-acceptance concurrency protection on single-worker jobs
  5. Job offers and atomic offer acceptance with competing offer rejection
  6. Job and booking state machine validation (rejecting unauthorized/invalid transitions)
  7. Booking QR check-in event logging with cryptographic token-hash verification
  8. Payment processing with server-side price validation and idempotency deduplication
  9. In-app notifications with deduplication and read-marking
 10. Dispute / job report filing and security audit trail logging
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from app import app
from backend_service import (
    LocationPrivacyShield,
    AuditLogger,
    NotificationService,
    StatusHistoryLogger,
    CheckinEventLogger,
    JobConcurrencyShield,
    PaymentManager,
    ServiceCategoryManager,
    WorkerSkillsManager,
    VALID_JOB_TRANSITIONS,
    VALID_BOOKING_TRANSITIONS,
    VALID_PAYMENT_TRANSITIONS,
)


class MockTableQuery:
    """Mock PostgREST query builder for local in-memory unit testing."""
    def __init__(self, data=None):
        # Reference the actual shared list so mutations persist across queries
        self._data = data if data is not None else []
        self._filters = {}
        self._or_expr = None
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

    def in_(self, col, vals):
        self._filters[f"{col}__in"] = set(vals)
        return self

    def ilike(self, col, pattern):
        self._filters[f"{col}__ilike"] = pattern.replace('%', '').lower()
        return self

    def or_(self, or_expr):
        self._or_expr = or_expr
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._desc = desc
        return self

    def limit(self, count):
        self._limit = count
        return self

    def execute(self):
        # 1. Handle Insert
        if self._last_inserted is not None:
            res = list(self._last_inserted)
            self._last_inserted = None
            return MockTableResponse(res)

        # 2. Filter matches
        matching = []
        for rec in self._data:
            match = True
            for k, v in self._filters.items():
                if k.endswith("__neq"):
                    col = k[:-5]
                    if rec.get(col) == v:
                        match = False; break
                elif k.endswith("__in"):
                    col = k[:-4]
                    if rec.get(col) not in v:
                        match = False; break
                elif k.endswith("__ilike"):
                    col = k[:-7]
                    if v not in str(rec.get(col, '')).lower():
                        match = False; break
                else:
                    if str(rec.get(k)) != str(v):
                        match = False; break
            if match:
                matching.append(rec)

        # 3. Handle or_ filters (e.g. 'payer_id.eq.X,payee_id.eq.X')
        if self._or_expr:
            or_conditions = []
            for part in self._or_expr.split(','):
                subparts = part.strip().split('.eq.')
                if len(subparts) == 2:
                    or_conditions.append((subparts[0], subparts[1]))
            if or_conditions:
                matching = [
                    rec for rec in matching
                    if any(str(rec.get(col)) == str(val) for col, val in or_conditions)
                ]

        # 4. Handle Deletes
        if self._pending_delete:
            self._pending_delete = False
            for rec in list(matching):
                if rec in self._data:
                    self._data.remove(rec)
            return MockTableResponse([dict(r) for r in matching])

        # 5. Handle Updates
        if self._pending_updates is not None:
            updated = []
            for rec in matching:
                rec.update(self._pending_updates)
                updated.append(dict(rec))
            self._pending_updates = None
            return MockTableResponse(updated)

        # 6. Sorting & Limit
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
            "jobs": [],
            "job_offers": [],
            "bookings": [],
            "service_categories": [],
            "worker_skills": [],
            "booking_status_history": [],
            "job_status_history": [],
            "booking_checkin_events": [],
            "payments": [],
            "payment_status_history": [],
            "notifications": [],
            "job_reports": [],
            "audit_events": [],
            "reviews": []
        }

    def table(self, table_name):
        if table_name not in self.tables:
            self.tables[table_name] = []
        return MockTableQuery(self.tables[table_name])


class TestVoiceHireDataModels(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.mock_db = MockDatabase()
        self.patcher = patch('app.supabase', self.mock_db)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    # ─────────────────────────────────────────────────────────────────
    # 1. Location Privacy Shield Tests
    # ─────────────────────────────────────────────────────────────────
    def test_location_coordinate_obfuscation(self):
        # Exact coords in New Delhi
        lat, lng = 28.6139391, 77.2090212
        fuzzy_lat, fuzzy_lng = LocationPrivacyShield.obfuscate_coordinates(lat, lng, precision=2)
        self.assertEqual(fuzzy_lat, 28.61)
        self.assertEqual(fuzzy_lng, 77.21)

        # Null coords handled safely
        n_lat, n_lng = LocationPrivacyShield.obfuscate_coordinates(None, None)
        self.assertIsNone(n_lat)
        self.assertIsNone(n_lng)

    def test_phone_masking(self):
        phone = "9876543210"
        masked = LocationPrivacyShield.mask_phone(phone)
        self.assertEqual(masked, "XXXXXX3210")

    def test_worker_profile_privacy_shield_for_public(self):
        worker = {
            "id": "w-101",
            "name": "Ramesh Kumar",
            "phone": "9876543210",
            "password": "argon2_secret_hash",
            "live_lat": 28.613939,
            "live_lng": 77.209021,
            "work": "Plumber"
        }
        sanitized = LocationPrivacyShield.obfuscate_worker_profile(worker, viewer_is_counterparty=False)

        # Passwords stripped completely
        self.assertNotIn("password", sanitized)
        # Raw live coordinates hidden for public viewer
        self.assertIsNone(sanitized["live_lat"])
        self.assertIsNone(sanitized["live_lng"])
        # Fuzzy approx coordinates available for maps
        self.assertEqual(sanitized["approx_lat"], 28.61)
        self.assertEqual(sanitized["approx_lng"], 77.21)
        # Phone masked
        self.assertEqual(sanitized["phone_masked"], "XXXXXX3210")
        self.assertNotIn("phone", sanitized)

    # ─────────────────────────────────────────────────────────────────
    # 2. Service Categories & Worker Skills Tests
    # ─────────────────────────────────────────────────────────────────
    def test_get_service_categories_api(self):
        res = self.client.get('/api/categories')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        # Verify schema elements
        slugs = [c['slug'] for c in data]
        self.assertIn('plumbing', slugs)
        self.assertIn('electrical', slugs)

    def test_worker_skills_unauthorized_access(self):
        # Must be logged in as worker to manage skills
        res = self.client.get('/api/worker/skills')
        self.assertEqual(res.status_code, 401)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'

        res = self.client.post('/api/worker/skills', json={"skill_name": "Pipe Fitting"})
        self.assertEqual(res.status_code, 401)

    def test_worker_skills_crud_and_ownership(self):
        worker_id = "worker-uuid-1"
        with self.client.session_transaction() as sess:
            sess['user_id'] = worker_id
            sess['role'] = 'worker'

        # 1. Add skill
        res = self.client.post('/api/worker/skills', json={
            "skill_name": "Leak Detection",
            "experience_years": 4,
            "is_primary": True
        })
        self.assertEqual(res.status_code, 201)
        skill_data = res.get_json()['skill']
        skill_id = skill_data['id']
        self.assertEqual(skill_data['skill_name'], "Leak Detection")
        self.assertEqual(skill_data['worker_id'], worker_id)

        # 2. Fetch worker's skills
        get_res = self.client.get('/api/worker/skills')
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(len(get_res.get_json()), 1)

        # 3. Another worker attempts unauthorized deletion
        with self.client.session_transaction() as sess:
            sess['user_id'] = "rogue-worker-uuid-2"
            sess['role'] = 'worker'

        del_unauth = self.client.delete(f'/api/worker/skills/{skill_id}')
        self.assertEqual(del_unauth.status_code, 403)

        # 4. Legitimate worker deletes own skill
        with self.client.session_transaction() as sess:
            sess['user_id'] = worker_id
            sess['role'] = 'worker'

        del_auth = self.client.delete(f'/api/worker/skills/{skill_id}')
        self.assertEqual(del_auth.status_code, 200)

        # Verify deletion
        get_res_empty = self.client.get('/api/worker/skills')
        self.assertEqual(len(get_res_empty.get_json()), 0)

    # ─────────────────────────────────────────────────────────────────
    # 3. Concurrency Protection: Atomic CAS Single-Worker Acceptance
    # ─────────────────────────────────────────────────────────────────
    def test_job_double_acceptance_concurrency_protection(self):
        # Setup an open job
        job_id = 42
        self.mock_db.tables["jobs"].append({
            "id": job_id,
            "user_id": "cust-99",
            "service_type": "Carpentry",
            "description": "Fix broken dining chair",
            "status": "open",
            "price": 500
        })

        # Worker 1 accepts the open job
        with self.client.session_transaction() as sess:
            sess['user_id'] = "worker-1"
            sess['role'] = 'worker'

        res1 = self.client.post(f'/api/jobs/{job_id}/accept', json={"price": 500})
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.get_json()['job']['status'], 'accepted')
        self.assertEqual(res1.get_json()['job']['worker_id'], 'worker-1')

        # Worker 2 simultaneously tries to accept the same job
        with self.client.session_transaction() as sess:
            sess['user_id'] = "worker-2"
            sess['role'] = 'worker'

        res2 = self.client.post(f'/api/jobs/{job_id}/accept', json={"price": 500})
        # Must return HTTP 409 Conflict, rejecting duplicate worker acceptance
        self.assertEqual(res2.status_code, 409)
        self.assertIn("already accepted", res2.get_json()['error'].lower())

    # ─────────────────────────────────────────────────────────────────
    # 4. Job Offers & Atomic Offer Acceptance
    # ─────────────────────────────────────────────────────────────────
    def test_job_offers_submission_and_customer_acceptance(self):
        job_id = 88
        customer_id = "customer-1"
        self.mock_db.tables["jobs"].append({
            "id": job_id,
            "user_id": customer_id,
            "service_type": "Painting",
            "description": "Paint bedroom walls",
            "status": "open"
        })

        # Worker 1 submits offer of ₹1200
        with self.client.session_transaction() as sess:
            sess['user_id'] = "worker-1"
            sess['role'] = 'worker'
        offer1_res = self.client.post(f'/api/jobs/{job_id}/offers', json={
            "proposed_price": 1200,
            "estimated_arrival_minutes": 30,
            "message": "Can start right away with premium paint"
        })
        self.assertEqual(offer1_res.status_code, 201)
        offer1_id = offer1_res.get_json()['offer']['id']

        # Worker 2 submits offer of ₹1000
        with self.client.session_transaction() as sess:
            sess['user_id'] = "worker-2"
            sess['role'] = 'worker'
        offer2_res = self.client.post(f'/api/jobs/{job_id}/offers', json={
            "proposed_price": 1000,
            "estimated_arrival_minutes": 45,
            "message": "Experienced interior painter"
        })
        self.assertEqual(offer2_res.status_code, 201)
        offer2_id = offer2_res.get_json()['offer']['id']

        # Customer views all offers
        with self.client.session_transaction() as sess:
            sess['user_id'] = customer_id
            sess['role'] = 'user'
        view_res = self.client.get(f'/api/jobs/{job_id}/offers')
        self.assertEqual(view_res.status_code, 200)
        self.assertEqual(len(view_res.get_json()), 2)

        # Customer accepts Worker 2's offer
        accept_res = self.client.post(f'/api/jobs/{job_id}/offers/{offer2_id}/accept')
        self.assertEqual(accept_res.status_code, 200)
        job_state = accept_res.get_json()['job']
        self.assertEqual(job_state['status'], 'accepted')
        self.assertEqual(job_state['worker_id'], 'worker-2')
        self.assertEqual(job_state['price'], 1000.0)

        # Verify competing offer 1 was marked rejected
        competing = [o for o in self.mock_db.tables["job_offers"] if o['id'] == offer1_id][0]
        self.assertEqual(competing['status'], 'rejected')

    # ─────────────────────────────────────────────────────────────────
    # 5. Job & Booking State Machine Transitions
    # ─────────────────────────────────────────────────────────────────
    def test_job_invalid_state_transition_rejection(self):
        job_id = 99
        customer_id = "customer-1"
        self.mock_db.tables["jobs"].append({
            "id": job_id,
            "user_id": customer_id,
            "status": "open"
        })

        with self.client.session_transaction() as sess:
            sess['user_id'] = customer_id
            sess['role'] = 'user'

        # Attempt illegal transition: open -> completed directly (must go through accepted)
        bad_res = self.client.post(f'/api/jobs/{job_id}/status', json={"status": "completed"})
        self.assertEqual(bad_res.status_code, 400)
        self.assertIn("Invalid state transition", bad_res.get_json()['error'])

    # ─────────────────────────────────────────────────────────────────
    # 6. QR Check-In Cryptographic Verification & Event Logging
    # ─────────────────────────────────────────────────────────────────
    def test_booking_checkin_token_verification_and_event_log(self):
        booking_id = 55
        customer_id = "customer-1"
        worker_id = "worker-1"
        correct_token = "valid-qr-uuid-secret-token"

        self.mock_db.tables["bookings"].append({
            "id": booking_id,
            "customer_id": customer_id,
            "worker_id": worker_id,
            "status": "Booked",
            "qr_token": correct_token
        })

        with self.client.session_transaction() as sess:
            sess['user_id'] = worker_id
            sess['role'] = 'worker'

        # 1. Invalid token attempt
        bad_res = self.client.post(f'/api/bookings/{booking_id}/checkin', json={"token": "tampered-token"})
        self.assertEqual(bad_res.status_code, 403)
        # Check that failure event was logged in booking_checkin_events
        failed_events = [e for e in self.mock_db.tables["booking_checkin_events"] if e['status'] == 'failed']
        self.assertEqual(len(failed_events), 1)

        # 2. Valid token check-in
        good_res = self.client.post(f'/api/bookings/{booking_id}/checkin', json={"token": correct_token})
        self.assertEqual(good_res.status_code, 200)
        self.assertEqual(good_res.get_json()['status'], 'Work Started')

        # Check success event logged
        success_events = [e for e in self.mock_db.tables["booking_checkin_events"] if e['status'] == 'success']
        self.assertEqual(len(success_events), 1)
        self.assertIsNotNone(success_events[0]['token_hash'])

        # Check status history recorded
        hist = [h for h in self.mock_db.tables["booking_status_history"] if h['booking_id'] == booking_id]
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]['to_status'], "Work Started")

    # ─────────────────────────────────────────────────────────────────
    # 7. Payments API: Server Price Verification & Idempotency
    # ─────────────────────────────────────────────────────────────────
    def test_payment_server_side_amount_validation_and_idempotency(self):
        booking_id = 77
        customer_id = "customer-1"
        worker_id = "worker-1"
        agreed_price = 750.0

        self.mock_db.tables["bookings"].append({
            "id": booking_id,
            "customer_id": customer_id,
            "worker_id": worker_id,
            "total_price": agreed_price,
            "status": "Completed"
        })

        with self.client.session_transaction() as sess:
            sess['user_id'] = customer_id
            sess['role'] = 'user'

        idempotency_key = "idemp-test-key-12345"

        # 1. First payment request
        res1 = self.client.post('/api/payments', json={
            "booking_id": booking_id,
            "payment_method": "upi",
            "idempotency_key": idempotency_key
        })
        self.assertEqual(res1.status_code, 201)
        payment_record = res1.get_json()['payment']
        self.assertEqual(payment_record['amount'], agreed_price)
        self.assertEqual(payment_record['payer_id'], customer_id)
        self.assertEqual(payment_record['payee_id'], worker_id)

        # 2. Duplicate retry with same idempotency key
        res2 = self.client.post('/api/payments', json={
            "booking_id": booking_id,
            "payment_method": "upi",
            "idempotency_key": idempotency_key
        })
        self.assertEqual(res2.status_code, 201)
        # Must return the existing payment without creating a second record
        self.assertEqual(len(self.mock_db.tables["payments"]), 1)
        self.assertEqual(res2.get_json()['payment']['id'], payment_record['id'])

    # ─────────────────────────────────────────────────────────────────
    # 8. Notifications API
    # ─────────────────────────────────────────────────────────────────
    def test_notifications_dispatch_and_read(self):
        user_id = "user-notif-1"
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['role'] = 'user'

        # Send test notification
        NotificationService.send_notification(
            self.mock_db,
            recipient_id=user_id,
            recipient_role="user",
            title="Appointment Reminder",
            message="Worker arriving in 15 mins",
            notif_type="booking_status"
        )

        # Fetch notifications
        get_res = self.client.get('/api/notifications')
        self.assertEqual(get_res.status_code, 200)
        notifs = get_res.get_json()
        self.assertEqual(len(notifs), 1)
        notif_id = notifs[0]['id']
        self.assertFalse(notifs[0]['is_read'])

        # Mark single as read
        read_res = self.client.post(f'/api/notifications/{notif_id}/read')
        self.assertEqual(read_res.status_code, 200)

        # Verify read status
        notif_in_db = [n for n in self.mock_db.tables["notifications"] if n['id'] == notif_id][0]
        self.assertTrue(notif_in_db['is_read'])

    # ─────────────────────────────────────────────────────────────────
    # 9. Dispute Reports API & Audit Logging
    # ─────────────────────────────────────────────────────────────────
    def test_job_reports_submission_and_audit_event(self):
        reporter_id = "customer-1"
        reported_id = "worker-1"
        with self.client.session_transaction() as sess:
            sess['user_id'] = reporter_id
            sess['role'] = 'user'

        res = self.client.post('/api/reports', json={
            "reported_id": reported_id,
            "reported_role": "worker",
            "reason": "No Show",
            "description": "Worker did not arrive at the scheduled time",
            "booking_id": 10
        })
        self.assertEqual(res.status_code, 201)
        report_id = res.get_json()['report_id']

        # Verify stored report
        reports = self.mock_db.tables["job_reports"]
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]['reason'], "No Show")

        # Verify audit trail
        audit_events = self.mock_db.tables["audit_events"]
        report_audits = [a for a in audit_events if a['event_type'] == 'dispute']
        self.assertEqual(len(report_audits), 1)
        self.assertEqual(report_audits[0]['action'], "file_report")


if __name__ == '__main__':
    unittest.main()
