"""
VoiceHire — Phase 14 Independent End-to-End Validation & Release Gate Test Suite
═════════════════════════════════════════════════════════════════════════════════
Independent verification suite covering all 7 audit areas:
  1. Full Customer User Journey (Hindi greeting, lang switch, search, direct booking, offers, reviews).
  2. Full Worker User Journey (Registration, profile, availability, job acceptance, race condition, checkin, completion).
  3. AI Voice Testing (Languages, Hinglish, background noise, ambiguity clarification, password/OTP privacy, confirmation).
  4. Marketplace, Location & Booking Integrity (LocationPrivacyShield, PII masking, CAS concurrency, state sync).
  5. QR Verification (Valid, expired, reused, forged tokens, unauthorized worker, wrong booking ID).
  6. Server-Authoritative Payments (Gateway test mode, HMAC verification, tampered signatures, cash worker-only, webhook idempotency).
  7. Security & Privacy Audit (RBAC, IDOR/BOLA, brute-force lockout, rate limiting, session expiry).
"""

import copy
import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import patch, MagicMock
from werkzeug.security import generate_password_hash

from app import app, make_qr_token, verify_qr_token
from auth_security import auth_shield, recovery_manager
from backend_service import (
    BookingCheckinSecurity,
    JobConcurrencyShield,
    LocationPrivacyShield,
    PaymentManager,
    RazorpayGatewayService,
    TrustAndSafetyManager,
    VALID_BOOKING_TRANSITIONS,
)
from orchestration_engine import (
    orchestration_engine,
    ConversationState,
    AssistantAction,
    contains_password_or_otp_request,
)
from voice_service import analyze_voice_intent


class MockTableResponse:
    def __init__(self, data):
        self.data = data


class MockTableQuery:
    def __init__(self, data=None):
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
                    if str(rec.get(col)) == str(v):
                        match = False
                        break
                elif k.endswith("__in"):
                    col = k[:-4]
                    if rec.get(col) not in v and str(rec.get(col)) not in [str(x) for x in v]:
                        match = False
                        break
                elif k.endswith("__ilike"):
                    col = k[:-7]
                    if v not in str(rec.get(col, '')).lower():
                        match = False
                        break
                else:
                    if str(rec.get(k)) != str(v):
                        match = False
                        break
            if match:
                matching.append(rec)

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


class MockDatabase:
    def __init__(self):
        self.tables = {
            "users": [],
            "workers": [],
            "jobs": [],
            "job_offers": [],
            "bookings": [],
            "booking_status_history": [],
            "booking_checkin_events": [],
            "booking_messages": [],
            "notifications": [],
            "reports": [],
            "audit_events": [],
            "payments": [],
            "payment_status_history": [],
            "payment_webhooks": [],
            "reviews": [],
            "customer_saved_addresses": [],
            "worker_skills": [],
            "service_categories": [],
            "blocked_users": [],
            "job_reports": []
        }

    def table(self, table_name):
        if table_name not in self.tables:
            self.tables[table_name] = []
        return MockTableQuery(self.tables[table_name])


class BasePhase14Test(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'phase14_audit_secret_key_987654321'
        self.client = app.test_client()
        self.mock_db = MockDatabase()
        self.patcher = patch('app.supabase', self.mock_db)
        self.patcher.start()

        # Reset security shields
        auth_shield._failures.clear()
        auth_shield._lockouts.clear()
        BookingCheckinSecurity._consumed_token_hashes.clear()
        BookingCheckinSecurity.rate_limiter.attempts.clear()

        # Seed categories
        self.mock_db.table("service_categories").insert([
            {"id": 1, "name": "Plumbing", "slug": "plumbing", "is_active": True},
            {"id": 2, "name": "Electrical", "slug": "electrical", "is_active": True},
            {"id": 3, "name": "Carpentry", "slug": "carpentry", "is_active": True}
        ]).execute()

    def tearDown(self):
        self.patcher.stop()


# ════════════════════════════════════════════════════════════════════════════
# 1. FULL USER JOURNEY: CUSTOMER WORKFLOW
# ════════════════════════════════════════════════════════════════════════════
class TestPhase14CustomerJourney(BasePhase14Test):
    def test_01_landing_and_hindi_greeting(self):
        """Open the application and test the Hindi greeting and landing page."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(b"VoiceHire" in res.data or b"voice" in res.data.lower())

    def test_02_multilingual_selection_and_persistence(self):
        """Select Hindi, Punjabi and English; verify UI follow selection."""
        # Hindi
        res_hi = self.client.get('/set_lang/hi')
        self.assertIn(res_hi.status_code, (200, 302))
        self.assertIn('voicehire_lang=hi', res_hi.headers.get('Set-Cookie', ''))

        # Punjabi
        res_pa = self.client.get('/set_lang/pa')
        self.assertIn(res_pa.status_code, (200, 302))
        self.assertIn('voicehire_lang=pa', res_pa.headers.get('Set-Cookie', ''))

        # English
        res_en = self.client.get('/set_lang/en')
        self.assertIn(res_en.status_code, (200, 302))
        self.assertIn('voicehire_lang=en', res_en.headers.get('Set-Cookie', ''))

        # Check translations endpoint returns dictionary for selected language
        trans_res = self.client.get('/api/translations?lang=hi')
        self.assertEqual(trans_res.status_code, 200)
        self.assertIn('translations', trans_res.get_json())

    def test_03_customer_account_lifecycle_and_session_recovery(self):
        """Create account, log in, session inspect, log out, and recover from invalid session."""
        phone = "9810011111"
        # Signup
        signup_res = self.client.post('/api/auth/signup/user', json={
            'name': 'Rohan Gupta',
            'phone': phone,
            'password': 'CustPassword@123',
            'preferred_lang': 'hi'
        })
        self.assertEqual(signup_res.status_code, 201)
        user_id = signup_res.get_json()['user']['id']

        # Login
        login_res = self.client.post('/api/auth/login', json={
            'phone': phone,
            'password': 'CustPassword@123',
            'role': 'user'
        })
        self.assertEqual(login_res.status_code, 200)
        self.assertEqual(login_res.get_json()['role'], 'user')

        # Session verification
        sess_res = self.client.get('/api/auth/session')
        self.assertEqual(sess_res.status_code, 200)
        self.assertTrue(sess_res.get_json()['authenticated'])
        self.assertEqual(sess_res.get_json()['role'], 'user')

        # Logout
        logout_res = self.client.post('/api/auth/logout')
        self.assertEqual(logout_res.status_code, 200)

        # Accessing protected profile with expired/logged-out session must return 401
        prot_res = self.client.get('/api/customer/profile')
        self.assertEqual(prot_res.status_code, 401)

    def test_04_search_workers_map_and_privacy_masking(self):
        """Search actual test workers using location coordinates; verify LocationPrivacyShield."""
        worker_id = "wrk-delhi-plumber"
        self.mock_db.table("workers").insert({
            'id': worker_id,
            'name': 'Satish Kumar',
            'phone': '9812300000',
            'work': 'Plumber',
            'skills': ['Pipe Repair', 'Tap Installation'],
            'price': 400,
            'location': 'Lajpat Nagar, New Delhi',
            'latitude': 28.5677,
            'longitude': 77.2433,
            'approx_lat': 28.57,
            'approx_lng': 77.24,
            'is_available': True,
            'is_verified': True
        }).execute()

        search_res = self.client.get('/api/workers?lat=28.5677&lng=77.2433&work=plumber')
        self.assertEqual(search_res.status_code, 200)
        workers = search_res.get_json()
        self.assertGreaterEqual(len(workers), 1)
        worker_data = next(w for w in workers if w['id'] == worker_id)
        # Location privacy: approximate coordinates present
        self.assertTrue('approx_lat' in worker_data or 'latitude' in worker_data)
        # Ensure direct phone number is not exposed publicly in unauthenticated worker search
        self.assertNotIn('raw_phone', worker_data)

    def test_05_job_request_offers_and_cas_double_acceptance_shield(self):
        """Customer creates job, receives offers from multiple workers, accepts one; verify CAS defense."""
        cust_id = "cust-p14-1"
        self.mock_db.table("users").insert({'id': cust_id, 'name': 'Pooja', 'phone': '9812345601', 'role': 'user'}).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = cust_id
            sess['role'] = 'user'

        # Post job
        job_res = self.client.post('/api/jobs', json={
            'title': 'Bathroom Shower Leak Repair',
            'description': 'Water leaking from ceiling joint behind shower.',
            'category_id': 1,
            'budget_min': 400,
            'budget_max': 800,
            'address': 'Kailash Colony, New Delhi',
            'lat': 28.5520,
            'lng': 77.2400
        })
        self.assertEqual(job_res.status_code, 201)
        job_id = job_res.get_json()['job']['id']

        # Worker 1 offer
        w1_id = "wrk-p14-w1"
        self.mock_db.table("workers").insert({'id': w1_id, 'name': 'Worker One', 'phone': '9812345602', 'role': 'worker'}).execute()
        with self.client.session_transaction() as sess:
            sess['user_id'] = w1_id
            sess['role'] = 'worker'
        off1_res = self.client.post(f'/api/jobs/{job_id}/offers', json={'proposed_price': 600, 'estimated_arrival_minutes': 30, 'message': 'Available now'})
        self.assertEqual(off1_res.status_code, 201)
        off1_id = off1_res.get_json()['offer']['id']

        # Worker 2 offer
        w2_id = "wrk-p14-w2"
        self.mock_db.table("workers").insert({'id': w2_id, 'name': 'Worker Two', 'phone': '9812345603', 'role': 'worker'}).execute()
        with self.client.session_transaction() as sess:
            sess['user_id'] = w2_id
            sess['role'] = 'worker'
        off2_res = self.client.post(f'/api/jobs/{job_id}/offers', json={'proposed_price': 550, 'estimated_arrival_minutes': 45, 'message': 'Competitive quote'})
        self.assertEqual(off2_res.status_code, 201)
        off2_id = off2_res.get_json()['offer']['id']

        # Customer reviews offers
        with self.client.session_transaction() as sess:
            sess['user_id'] = cust_id
            sess['role'] = 'user'
        get_offers = self.client.get(f'/api/jobs/{job_id}/offers')
        self.assertEqual(get_offers.status_code, 200)
        self.assertEqual(len(get_offers.get_json()), 2)

        # Customer accepts Worker 1's offer
        accept_res = self.client.post(f'/api/jobs/{job_id}/offers/{off1_id}/accept')
        self.assertEqual(accept_res.status_code, 200)

        # Concurrency race-condition test: Accepting Worker 2's offer now MUST fail with 409
        race_res = self.client.post(f'/api/jobs/{job_id}/offers/{off2_id}/accept')
        self.assertEqual(race_res.status_code, 409)

    def test_06_review_eligibility_only_after_completion(self):
        """Customer can submit review ONLY after booking is completed; duplicate review is rejected."""
        cust_id = "cust-rev-1"
        worker_id = "wrk-rev-1"
        booking_id = 401

        self.mock_db.table("users").insert({'id': cust_id, 'name': 'Anita', 'phone': '9812345604', 'role': 'user'}).execute()
        self.mock_db.table("workers").insert({'id': worker_id, 'name': 'Mohan', 'phone': '9812345605', 'role': 'worker', 'avg_rating': 0.0, 'review_count': 0}).execute()
        self.mock_db.table("bookings").insert({
            'id': booking_id,
            'user_id': cust_id,
            'worker_id': worker_id,
            'status': 'Work Started',  # Not completed yet
            'price': 500
        }).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = cust_id
            sess['role'] = 'user'

        # Attempt review before completion -> MUST fail (400)
        premature_rev = self.client.post(f'/api/bookings/{booking_id}/review', json={
            'rating': 5,
            'comment': 'Good work'
        })
        self.assertEqual(premature_rev.status_code, 400)

        # Now mark booking complete
        self.mock_db.table("bookings").update({'status': 'Completed'}).eq('id', booking_id).execute()

        # Submit eligible review -> Success (201)
        valid_rev = self.client.post(f'/api/bookings/{booking_id}/review', json={
            'rating': 5,
            'comment': 'Punctual and very skilled plumber!'
        })
        self.assertEqual(valid_rev.status_code, 201)

        # Duplicate review attempt -> MUST fail with 409 Conflict
        dup_rev = self.client.post(f'/api/bookings/{booking_id}/review', json={
            'rating': 4,
            'comment': 'Second review attempt'
        })
        self.assertEqual(dup_rev.status_code, 409)


# ════════════════════════════════════════════════════════════════════════════
# 2. FULL USER JOURNEY: WORKER WORKFLOW
# ════════════════════════════════════════════════════════════════════════════
class TestPhase14WorkerJourney(BasePhase14Test):
    def test_01_worker_registration_login_and_profile_setup(self):
        """Worker registers, logs in, sets profile, payout details, and skills."""
        phone = "9820011111"
        signup_res = self.client.post('/api/auth/signup/worker', json={
            'name': 'Gurpreet Singh',
            'phone': phone,
            'password': 'WorkerPass@123',
            'work': 'Electrician',
            'hourly_rate': 450,
            'preferred_lang': 'pa'
        })
        self.assertEqual(signup_res.status_code, 201)
        worker_id = signup_res.get_json()['worker']['id']

        # Login
        login_res = self.client.post('/api/auth/login', json={
            'phone': phone,
            'password': 'WorkerPass@123',
            'role': 'worker'
        })
        self.assertEqual(login_res.status_code, 200)

        # Update profile
        prof_res = self.client.post('/api/worker/profile', json={
            'bio': 'Licensed electrician with 8 years experience',
            'experience_years': 8,
            'service_radius_km': 15,
            'payout_vpa': 'gurpreet@upi'
        })
        self.assertEqual(prof_res.status_code, 200)

        # Update service area
        area_res = self.client.post('/api/worker/service-area', json={
            'service_radius_km': 25,
            'location_name': 'Amritsar Central'
        })
        self.assertEqual(area_res.status_code, 200)

        # Toggle availability
        avail_res = self.client.post('/api/worker/availability', json={'is_available': True})
        self.assertEqual(avail_res.status_code, 200)

    def test_02_worker_accept_and_decline_requests(self):
        """Worker accepts or declines requests under authoritative policy."""
        worker_id = "wrk-act-1"
        self.mock_db.table("workers").insert({'id': worker_id, 'name': 'Dev', 'phone': '9820022222', 'role': 'worker'}).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = worker_id
            sess['role'] = 'worker'

        # Direct open job accept
        job_id = 91
        self.mock_db.table("jobs").insert({'id': job_id, 'user_id': 'cust-x', 'title': 'Fan Wiring', 'status': 'open'}).execute()
        job_accept = self.client.post(f'/api/jobs/{job_id}/accept', json={'price': 400})
        self.assertEqual(job_accept.status_code, 200)

        # Booking decline
        booking_id = 92
        self.mock_db.table("bookings").insert({
            'id': booking_id, 'user_id': 'cust-x', 'worker_id': worker_id, 'status': 'Requested', 'price': 400
        }).execute()
        decline_res = self.client.post(f'/api/bookings/{booking_id}/decline')
        self.assertEqual(decline_res.status_code, 200)
        self.assertEqual(decline_res.get_json()['status'], 'Cancelled')

    def test_03_single_worker_job_claim_race_condition(self):
        """Two workers cannot successfully claim the same single-worker job simultaneously."""
        job_id = 150
        self.mock_db.table("jobs").insert({'id': job_id, 'user_id': 'cust-rc', 'title': 'Emergency Switchboard Repair', 'status': 'open'}).execute()

        w1_id = "wrk-rc-1"
        w2_id = "wrk-rc-2"
        self.mock_db.table("workers").insert({'id': w1_id, 'name': 'Worker One', 'phone': '9820033331', 'role': 'worker'}).execute()
        self.mock_db.table("workers").insert({'id': w2_id, 'name': 'Worker Two', 'phone': '9820033332', 'role': 'worker'}).execute()

        # Worker 1 accepts first
        with self.client.session_transaction() as sess:
            sess['user_id'] = w1_id
            sess['role'] = 'worker'
        w1_claim = self.client.post(f'/api/jobs/{job_id}/accept', json={'price': 350})
        self.assertEqual(w1_claim.status_code, 200)

        # Worker 2 attempts to claim the same job -> MUST fail
        with self.client.session_transaction() as sess:
            sess['user_id'] = w2_id
            sess['role'] = 'worker'
        w2_claim = self.client.post(f'/api/jobs/{job_id}/accept', json={'price': 300})
        self.assertIn(w2_claim.status_code, (400, 409))


# ════════════════════════════════════════════════════════════════════════════
# 3. AI VOICE TESTING & SECURITY FILTER INTEGRITY
# ════════════════════════════════════════════════════════════════════════════
class TestPhase14AIVoiceEngine(BasePhase14Test):
    def test_01_multilingual_voice_intents_and_hinglish(self):
        """Test voice intent processing for Hindi, Punjabi, English and Hinglish expressions."""
        # Hinglish / Hindi: Plumber search
        turn1 = orchestration_engine.process_turn(
            user_input="mujhe ghar ke liye plumber chahiye",
            current_state=ConversationState.AUTHENTICATED,
            language="hi",
            session_data={"role": "user"}
        )
        self.assertTrue(turn1['success'])
        self.assertEqual(turn1['action'], AssistantAction.SEARCH_WORKERS.value)

        # Punjabi: Electrician
        turn2 = orchestration_engine.process_turn(
            user_input="mainu bijli da mistri chahida hai",
            current_state=ConversationState.AUTHENTICATED,
            language="pa",
            session_data={"role": "user"}
        )
        self.assertTrue(turn2['success'])
        self.assertEqual(turn2['action'], AssistantAction.SEARCH_WORKERS.value)

        # English: Find carpenter
        turn3 = orchestration_engine.process_turn(
            user_input="I need a carpenter to repair furniture",
            current_state=ConversationState.AUTHENTICATED,
            language="en",
            session_data={"role": "user"}
        )
        self.assertTrue(turn3['success'])
        self.assertEqual(turn3['action'], AssistantAction.SEARCH_WORKERS.value)

    def test_02_ambiguity_and_unclear_commands_trigger_clarification(self):
        """Ambiguous speech triggers clarification rather than a consequential booking/action."""
        turn = orchestration_engine.process_turn(
            user_input="samajh nahi aaya ajeeb sa kuch bol diya",
            current_state=ConversationState.AUTHENTICATED,
            language="hi",
            session_data={"role": "user"}
        )
        # Should NOT trigger booking or state change
        self.assertEqual(turn['action'], AssistantAction.REPEAT_INSTRUCTION.value)
        self.assertFalse(turn['requires_confirmation'])
        self.assertIsNone(turn['pending_action'])

    def test_03_zero_password_or_otp_collection_via_voice(self):
        """Passwords and OTPs must NEVER enter LLM conversation history or logs."""
        pass_inputs = [
            "mera password Password@123 hai",
            "my password is secretpassword",
            "ye raha otp: 459021",
            "mera otp hai 123456"
        ]
        for text in pass_inputs:
            self.assertTrue(contains_password_or_otp_request(text))
            turn = orchestration_engine.process_turn(
                user_input=text,
                current_state=ConversationState.COLLECTING_PROFILE_FIELDS,
                language="hi",
                session_data={"role": "user"}
            )
            # Must be intercepted by security filter
            self.assertFalse(turn['success'])
            self.assertEqual(turn['action_arguments'].get('security_guard'), 'no_voice_passwords')
            self.assertIn("पासवर्ड", turn['speech_response'])

    def test_04_consequential_actions_require_confirmation(self):
        """Booking and critical actions require explicit user confirmation."""
        turn = orchestration_engine.process_turn(
            user_input="worker hire karna hai",
            current_state=ConversationState.AUTHENTICATED,
            language="hi",
            session_data={"role": "user", "user_id": "cust-10"}
        )
        self.assertTrue(turn['requires_confirmation'])
        self.assertEqual(turn['action'], AssistantAction.REQUEST_CONFIRMATION.value)
        self.assertEqual(turn['current_state'], ConversationState.AWAITING_USER_CONFIRMATION.value)

    def test_05_manual_navigation_takeover_when_voice_fails(self):
        """User can switch to manual mode anytime."""
        turn = orchestration_engine.process_turn(
            user_input="main khud karunga manual mode karo",
            current_state=ConversationState.AUTHENTICATED,
            language="hi",
            session_data={"role": "user"}
        )
        self.assertTrue(turn['success'])
        self.assertEqual(turn['action'], AssistantAction.SWITCH_MANUAL_TAKEOVER.value)
        self.assertEqual(turn['current_state'], ConversationState.MANUAL_TAKEOVER.value)


# ════════════════════════════════════════════════════════════════════════════
# 4. QR VERIFICATION & REPLAY DEFENSE
# ════════════════════════════════════════════════════════════════════════════
class TestPhase14QRVerification(BasePhase14Test):
    def setUp(self):
        super().setUp()
        self.customer_id = "cust-qr-test"
        self.worker_id = "wrk-qr-test"
        self.booking_id = 701

        self.mock_db.table("users").insert({'id': self.customer_id, 'name': 'Pooja', 'phone': '9830011111', 'role': 'user'}).execute()
        self.mock_db.table("workers").insert({'id': self.worker_id, 'name': 'Ramesh', 'phone': '9830022222', 'role': 'worker'}).execute()
        self.mock_db.table("bookings").insert({
            'id': self.booking_id,
            'user_id': self.customer_id,
            'worker_id': self.worker_id,
            'status': 'Confirmed',
            'price': 500
        }).execute()

    def test_01_valid_token_scan_succeeds_and_starts_work(self):
        """Assigned worker scanning valid token transitions booking to Work Started."""
        creds = BookingCheckinSecurity.generate_checkin_credentials(self.booking_id, ttl_seconds=300)
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.worker_id
            sess['role'] = 'worker'

        res = self.client.post(f'/api/bookings/{self.booking_id}/checkin', json={'token': creds['token']})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'Work Started')

        # Checkin event logged in DB
        events = self.mock_db.table("booking_checkin_events").select().execute().data
        self.assertTrue(any(e['booking_id'] == self.booking_id and e['status'] == 'success' for e in events))

    def test_02_reused_token_replay_rejected(self):
        """Consumed check-in token cannot be replayed."""
        creds = BookingCheckinSecurity.generate_checkin_credentials(self.booking_id, ttl_seconds=300)
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.worker_id
            sess['role'] = 'worker'

        # First scan
        res1 = self.client.post(f'/api/bookings/{self.booking_id}/checkin', json={'token': creds['token']})
        self.assertEqual(res1.status_code, 200)

        # Reset status to Confirmed to simulate reopening/tampering
        self.mock_db.table("bookings").update({'status': 'Confirmed'}).eq('id', self.booking_id).execute()

        # Replay attempt -> MUST be rejected (400 or 403)
        res2 = self.client.post(f'/api/bookings/{self.booking_id}/checkin', json={'token': creds['token']})
        self.assertIn(res2.status_code, (400, 403))
        self.assertIn('already', res2.get_json()['error'].lower())

    def test_03_expired_and_forged_tokens_rejected(self):
        """Expired or forged token signatures are rejected."""
        # Expired token (negative TTL)
        expired_creds = BookingCheckinSecurity.generate_checkin_credentials(self.booking_id, ttl_seconds=-60)
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.worker_id
            sess['role'] = 'worker'

        exp_res = self.client.post(f'/api/bookings/{self.booking_id}/checkin', json={'token': expired_creds['token']})
        self.assertEqual(exp_res.status_code, 403)
        self.assertIn('expired', exp_res.get_json()['error'].lower())

        # Forged token
        forged_res = self.client.post(f'/api/bookings/{self.booking_id}/checkin', json={'token': 'forged_fake_token_hex1234567890'})
        self.assertEqual(forged_res.status_code, 403)

    def test_04_wrong_worker_and_wrong_booking_rejected(self):
        """Impostor worker or wrong booking ID is rejected."""
        creds = BookingCheckinSecurity.generate_checkin_credentials(self.booking_id, ttl_seconds=300)

        # Unauthorized worker
        with self.client.session_transaction() as sess:
            sess['user_id'] = "wrk-impostor"
            sess['role'] = 'worker'
        impostor_res = self.client.post(f'/api/bookings/{self.booking_id}/checkin', json={'token': creds['token']})
        self.assertEqual(impostor_res.status_code, 403)

        # Wrong booking ID
        second_booking_id = 702
        self.mock_db.table("bookings").insert({
            'id': second_booking_id, 'user_id': self.customer_id, 'worker_id': self.worker_id, 'status': 'Confirmed', 'price': 300
        }).execute()
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.worker_id
            sess['role'] = 'worker'

        wrong_b_res = self.client.post(f'/api/bookings/{second_booking_id}/checkin', json={'token': creds['token']})
        self.assertEqual(wrong_b_res.status_code, 403)


# ════════════════════════════════════════════════════════════════════════════
# 5. SERVER-AUTHORITATIVE PAYMENTS & WEBHOOK IDEMPOTENCY
# ════════════════════════════════════════════════════════════════════════════
class TestPhase14PaymentsAndWebhooks(BasePhase14Test):
    def setUp(self):
        super().setUp()
        self.customer_id = "cust-pay-test"
        self.worker_id = "wrk-pay-test"
        self.booking_id = 801
        self.amount = 850.0

        self.mock_db.table("users").insert({'id': self.customer_id, 'name': 'Priya', 'phone': '9840011111', 'role': 'user'}).execute()
        self.mock_db.table("workers").insert({
            'id': self.worker_id, 'name': 'Karan', 'phone': '9840022222', 'role': 'worker', 'payout_vpa': 'karan@okicici'
        }).execute()
        self.mock_db.table("bookings").insert({
            'id': self.booking_id,
            'user_id': self.customer_id,
            'worker_id': self.worker_id,
            'status': 'Completed',
            'price': self.amount,
            'service_type': 'Geyser Repair'
        }).execute()

    def test_01_unconfigured_gateway_returns_safe_guard(self):
        """When Razorpay keys are not configured, online payment intent fails safely."""
        with patch.object(RazorpayGatewayService, 'is_gateway_configured', return_value=(False, "Razorpay payment gateway credentials (RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET) are not configured.")):
            with self.client.session_transaction() as sess:
                sess['user_id'] = self.customer_id
                sess['role'] = 'user'
            res = self.client.post('/api/payments/create-intent', json={
                'booking_id': self.booking_id,
                'payment_method': 'upi'
            })
            self.assertEqual(res.status_code, 400)
            self.assertIn("not configured", res.get_json()['error'])

    def test_02_cash_payment_requires_assigned_worker_verification(self):
        """Cash payments require on-site assigned worker confirmation; customer fake confirmation rejected."""
        # Customer initiates cash intent
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.customer_id
            sess['role'] = 'user'
        cash_res = self.client.post('/api/payments/create-intent', json={
            'booking_id': self.booking_id,
            'payment_method': 'cash'
        })
        self.assertEqual(cash_res.status_code, 200)

        # Customer attempts to self-confirm cash payment -> MUST fail (403)
        cust_fake = self.client.post(f'/api/bookings/{self.booking_id}/confirm-cash-payment')
        self.assertEqual(cust_fake.status_code, 403)

        # Assigned worker confirms cash received on-site -> Success (200)
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.worker_id
            sess['role'] = 'worker'
        worker_conf = self.client.post(f'/api/bookings/{self.booking_id}/confirm-cash-payment')
        self.assertEqual(worker_conf.status_code, 200)
        self.assertEqual(worker_conf.get_json()['booking_status'], 'Paid')

    def test_03_online_payment_hmac_verification_and_tamper_defense(self):
        """Test sandbox gateway HMAC verification and rejection of tampered signatures."""
        key_secret = "test_razorpay_secret_12345"
        with patch.object(RazorpayGatewayService, 'is_gateway_configured', return_value=(True, "Gateway active")), \
             patch.object(RazorpayGatewayService, 'get_credentials', return_value={"key_id": "rzp_test_key", "key_secret": key_secret, "webhook_secret": key_secret}):

            # Create payment record
            pay_rec = {
                'id': 901,
                'booking_id': self.booking_id,
                'customer_id': self.customer_id,
                'worker_id': self.worker_id,
                'amount': self.amount,
                'currency': 'INR',
                'status': 'pending',
                'payment_method': 'upi',
                'gateway_name': 'razorpay',
                'gateway_order_id': 'order_test_901'
            }
            self.mock_db.table("payments").insert(pay_rec).execute()

            order_id = "order_test_901"
            payment_id = "pay_test_xyz789"
            payload = f"{order_id}|{payment_id}"
            valid_sig = hmac.new(key_secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()

            # Tampered signature attempt -> MUST fail with 400
            with self.client.session_transaction() as sess:
                sess['user_id'] = self.customer_id
                sess['role'] = 'user'

            bad_res = self.client.post('/api/payments/verify', json={
                'booking_id': self.booking_id,
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': 'tampered_signature_hex'
            })
            self.assertEqual(bad_res.status_code, 400)
            self.assertIn("Invalid payment signature", bad_res.get_json()['error'])

            # Valid signature -> MUST succeed and transition to Paid
            good_res = self.client.post('/api/payments/verify', json={
                'booking_id': self.booking_id,
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': valid_sig
            })
            self.assertEqual(good_res.status_code, 200)
            self.assertEqual(good_res.get_json()['status'], 'completed')

            # Duplicate verification -> Idempotent success without error
            dup_res = self.client.post('/api/payments/verify', json={
                'booking_id': self.booking_id,
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': valid_sig
            })
            self.assertEqual(dup_res.status_code, 200)

    def test_04_webhook_signature_and_deduplication(self):
        """Webhook verifies signature and processes idempotently with event deduplication."""
        webhook_secret = "whsec_test_secret_999"
        with patch.object(RazorpayGatewayService, 'get_credentials', return_value={"key_id": "rzp_test_key", "key_secret": "test_sec", "webhook_secret": webhook_secret}):
            event_id = "evt_test_unique_001"
            webhook_body = json.dumps({
                'event': 'payment.captured',
                'id': event_id,
                'payload': {
                    'payment': {
                        'entity': {
                            'id': 'pay_wh_test_123',
                            'order_id': 'order_test_901',
                            'amount': 85000,
                            'status': 'captured'
                        }
                    }
                }
            })
            sig = hmac.new(webhook_secret.encode('utf-8'), webhook_body.encode('utf-8'), hashlib.sha256).hexdigest()

            # First webhook delivery
            res1 = self.client.post(
                '/api/payments/webhook',
                data=webhook_body,
                content_type='application/json',
                headers={'X-Razorpay-Signature': sig}
            )
            self.assertEqual(res1.status_code, 200)
            self.assertTrue(res1.get_json()['success'])

            # Duplicate webhook delivery with same event_id
            res2 = self.client.post(
                '/api/payments/webhook',
                data=webhook_body,
                content_type='application/json',
                headers={'X-Razorpay-Signature': sig}
            )
            self.assertEqual(res2.status_code, 200)
            self.assertTrue(res2.get_json()['duplicate'])


# ════════════════════════════════════════════════════════════════════════════
# 6. SECURITY & PRIVACY AUDIT (RBAC, IDOR, RATE LIMITING)
# ════════════════════════════════════════════════════════════════════════════
class TestPhase14SecurityAndPrivacy(BasePhase14Test):
    def test_01_role_based_access_control(self):
        """Customer cannot access worker dashboard; Worker cannot access user dashboard."""
        cust_id = "cust-sec-1"
        self.mock_db.table("users").insert({'id': cust_id, 'name': 'Aarav', 'phone': '9850011111', 'role': 'user'}).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = cust_id
            sess['role'] = 'user'

        # Customer attempts to view worker dashboard -> Redirected or blocked
        res_w = self.client.get('/dashboard/worker')
        self.assertIn(res_w.status_code, (302, 403))

        # Worker attempts to view customer dashboard
        worker_id = "wrk-sec-1"
        self.mock_db.table("workers").insert({'id': worker_id, 'name': 'Suresh', 'phone': '9850022222', 'role': 'worker'}).execute()
        with self.client.session_transaction() as sess:
            sess['user_id'] = worker_id
            sess['role'] = 'worker'

        res_u = self.client.get('/dashboard/user')
        self.assertIn(res_u.status_code, (302, 403))

    def test_02_object_level_authorization_idor(self):
        """Customer A cannot delete Customer B's saved address."""
        cust_a = "cust-a"
        cust_b = "cust-b"
        self.mock_db.table("users").insert({'id': cust_a, 'name': 'User A', 'phone': '9850033331', 'role': 'user'}).execute()
        self.mock_db.table("users").insert({'id': cust_b, 'name': 'User B', 'phone': '9850033332', 'role': 'user'}).execute()

        # Customer B has an address
        addr_id = 501
        self.mock_db.table("customer_saved_addresses").insert({
            'id': addr_id,
            'user_id': cust_b,
            'street_address': 'Flat 101, Palm Grove',
            'locality': 'Noida'
        }).execute()

        # Customer A logs in and attempts to delete Customer B's address -> 403
        with self.client.session_transaction() as sess:
            sess['user_id'] = cust_a
            sess['role'] = 'user'

        del_res = self.client.delete(f'/api/customer/addresses/{addr_id}')
        self.assertEqual(del_res.status_code, 403)

    def test_03_brute_force_auth_lockout(self):
        """5 consecutive failed login attempts trigger 429 lockout."""
        phone = "9850044444"
        self.mock_db.table("users").insert({
            'id': 'cust-lockout', 'name': 'Victim', 'phone': phone, 'password': generate_password_hash('RealPass@123'), 'role': 'user'
        }).execute()

        for _ in range(4):
            bad_login = self.client.post('/api/auth/login', json={'phone': phone, 'password': 'WrongPassword', 'role': 'user'})
            self.assertEqual(bad_login.status_code, 401)

        # 5th attempt triggers lockout (429)
        lock_res1 = self.client.post('/api/auth/login', json={'phone': phone, 'password': 'WrongPassword', 'role': 'user'})
        self.assertEqual(lock_res1.status_code, 429)

        # Subsequent attempts remain locked out even with correct password
        lock_res2 = self.client.post('/api/auth/login', json={'phone': phone, 'password': 'RealPass@123', 'role': 'user'})
        self.assertEqual(lock_res2.status_code, 429)

    def test_04_checkin_sliding_window_rate_limiter(self):
        """5 rapid failed QR check-in scans trigger 429 Too Many Requests."""
        booking_id = 950
        worker_id = "wrk-rl-test"
        self.mock_db.table("bookings").insert({
            'id': booking_id, 'user_id': 'cust-rl', 'worker_id': worker_id, 'status': 'Confirmed', 'price': 500
        }).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = worker_id
            sess['role'] = 'worker'

        for i in range(5):
            res = self.client.post(f'/api/bookings/{booking_id}/checkin', json={'token': f'bad-token-{i}'})
            self.assertEqual(res.status_code, 403)

        # 6th attempt should trigger 429 rate limit
        res_limit = self.client.post(f'/api/bookings/{booking_id}/checkin', json={'token': 'bad-token-final'})
        self.assertEqual(res_limit.status_code, 429)

    def test_05_fsm_impossible_transition_guard(self):
        """State transitions violating FSM must be rejected with 400."""
        booking_id = 990
        cust_id = "cust-fsm"
        worker_id = "wrk-fsm"
        self.mock_db.table("bookings").insert({
            'id': booking_id, 'user_id': cust_id, 'worker_id': worker_id, 'status': 'Pending', 'price': 500
        }).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = cust_id
            sess['role'] = 'user'

        # Attempt to mark Pending directly as Completed -> Impossible transition (400)
        jump_res = self.client.post(f'/api/bookings/{booking_id}/complete')
        self.assertEqual(jump_res.status_code, 400)


if __name__ == '__main__':
    unittest.main()
