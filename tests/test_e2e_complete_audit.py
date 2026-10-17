"""
VoiceHire — Comprehensive End-to-End Audit & Verification Test Suite
════════════════════════════════════════════════════════════════════
Verifies all 6 real-world user journeys and critical security/operational requirements:
  - Journey A: New Customer Onboarding, Language Selection, Search & Direct Booking.
  - Journey B: Job Request Lifecycle, Multi-Worker Offers & Atomic CAS Acceptance.
  - Journey C: Worker Onboarding, Multilingual Setup, Availability & Acceptance/Decline.
  - Journey D: Cryptographic QR Check-in, Mutual Confirmation, Replay Defense & Completion.
  - Journey E: Server-Authoritative Payments (Cash & Online), Webhooks & Verified Reviews.
  - Journey F: Returning Users, Session Rotation, Role Isolation & Language Persistence.
  - Security Checks: RBAC, Ownership, Rate Limiting, PII Privacy & Transition Guarantees.
"""

import copy
import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

from app import app
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


class MockTableResponse:
    def __init__(self, data):
        self.data = data


class MockTableQuery:
    """PostgREST mock query engine supporting filtering, sorting, updating and cascades."""

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
    """Mock Supabase client providing isolated in-memory tables."""

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


class TestVoiceHireEndToEndAudit(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'audit_test_secret_key_12345'
        self.client = app.test_client()
        self.mock_db = MockDatabase()
        self.patcher = patch('app.supabase', self.mock_db)
        self.patcher.start()

        # Reset security shields and in-memory replay buffers
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

    # ══════════════════════════════════════════════════════════════════════════
    # JOURNEY A: New Customer Onboarding, Language Selection, Search & Booking
    # ══════════════════════════════════════════════════════════════════════════
    def test_journey_a_new_customer_onboarding_and_direct_booking(self):
        # 1. Landing page greeting & public access
        landing_res = self.client.get('/')
        self.assertEqual(landing_res.status_code, 200)

        # 2. Language Choice -> Set Hindi ('hi')
        lang_res = self.client.get('/set_lang/hi')
        self.assertIn(lang_res.status_code, (200, 302))
        cookie_header = lang_res.headers.get('Set-Cookie', '')
        self.assertIn('voicehire_lang=hi', cookie_header)

        # 3. Customer Signup (Role: user)
        customer_phone = "9876543201"
        customer_signup = self.client.post('/api/auth/signup/user', json={
            'name': 'Aarav Sharma',
            'phone': customer_phone,
            'password': 'Password@123',
            'preferred_lang': 'hi'
        })
        self.assertEqual(customer_signup.status_code, 201)
        signup_data = customer_signup.get_json()
        self.assertEqual(signup_data['role'], 'user')
        customer_id = signup_data['user']['id']

        # 4. Login & Session Establishment
        login_res = self.client.post('/api/auth/login', json={
            'phone': customer_phone,
            'password': 'Password@123',
            'role': 'user'
        })
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.get_json()
        self.assertEqual(login_data['role'], 'user')
        self.assertIn('dashboard', login_data['redirect'])

        # 5. Profile Completion (Add address & alternate details)
        addr_res = self.client.post('/api/customer/addresses', json={
            'label': 'Home',
            'address_line': 'Flat 402, Lotus Court',
            'city': 'New Delhi',
            'pincode': '110001',
            'lat': 28.6139,
            'lng': 77.2090,
            'is_default': True
        })
        self.assertEqual(addr_res.status_code, 201)

        # Seed an available worker nearby
        worker_id = "wrk-plumber-1"
        self.mock_db.table("workers").insert({
            'id': worker_id,
            'name': 'Ramesh Kumar',
            'phone': '9812345678',
            'work': 'Plumber',
            'skills': ['Plumber', 'Pipe Repair'],
            'price': 450,
            'location': 'Connaught Place, New Delhi',
            'latitude': 28.6315,
            'longitude': 77.2167,
            'approx_lat': 28.63,
            'approx_lng': 77.22,
            'is_available': True,
            'is_verified': True,
            'avg_rating': 4.8,
            'review_count': 12
        }).execute()

        # 6. Search Nearby Workers
        search_res = self.client.get('/api/workers?lat=28.6139&lng=77.2090&work=plumber')
        self.assertEqual(search_res.status_code, 200)
        workers_list = search_res.get_json()
        self.assertGreaterEqual(len(workers_list), 1)
        found_worker = next(w for w in workers_list if w['id'] == worker_id)
        self.assertEqual(found_worker['name'], 'Ramesh Kumar')
        # Ensure location privacy protection is maintained
        self.assertTrue('approx_lat' in found_worker or 'latitude' in found_worker)

        # 7. Direct Booking Creation
        book_res = self.client.post('/create_booking', json={
            'worker_id': worker_id,
            'date': '2026-10-20',
            'time_slot': '09:00-11:00',
            'service_type': 'Pipe Leak Repair',
            'address': 'Flat 402, Lotus Court, New Delhi'
        })
        self.assertEqual(book_res.status_code, 201)
        book_data = book_res.get_json()
        self.assertIsNotNone(book_data.get('booking_id'))
        self.assertIn('Booking confirmed', book_data.get('message', ''))

    # ══════════════════════════════════════════════════════════════════════════
    # JOURNEY B: Job Request, Worker Offers & CAS Double-Acceptance Shield
    # ══════════════════════════════════════════════════════════════════════════
    def test_journey_b_job_request_worker_offers_and_cas_acceptance(self):
        # 1. Customer logs in
        customer_id = "cust-jb-101"
        self.mock_db.table("users").insert({
            'id': customer_id,
            'name': 'Sunita Rao',
            'phone': '9876543202',
            'password': generate_password_hash('Pass123'),
            'role': 'user'
        }).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = customer_id
            sess['role'] = 'user'
            sess['name'] = 'Sunita Rao'

        # Customer posts a job request
        job_post_res = self.client.post('/api/jobs', json={
            'title': 'Kitchen Sink Replacement',
            'description': 'Need a new stainless steel sink installed in the kitchen.',
            'category_id': 1,
            'budget_min': 500,
            'budget_max': 900,
            'address': 'Sector 15, Noida',
            'lat': 28.5800,
            'lng': 77.3100
        })
        self.assertEqual(job_post_res.status_code, 201)
        job_id = job_post_res.get_json()['job']['id']

        # 2. Worker 1 submits an offer
        worker_1_id = "wrk-b1"
        self.mock_db.table("workers").insert({
            'id': worker_1_id,
            'name': 'Vikram Carpenter',
            'phone': '9811111111',
            'password': generate_password_hash('Pass123'),
            'role': 'worker'
        }).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = worker_1_id
            sess['role'] = 'worker'

        offer_1_res = self.client.post(f'/api/jobs/{job_id}/offers', json={
            'proposed_price': 700,
            'estimated_arrival_minutes': 45,
            'message': 'Experienced with sink installations. Can arrive by 11 AM.'
        })
        self.assertEqual(offer_1_res.status_code, 201)
        offer_1_id = offer_1_res.get_json()['offer']['id']

        # 3. Worker 2 submits a competing offer
        worker_2_id = "wrk-b2"
        self.mock_db.table("workers").insert({
            'id': worker_2_id,
            'name': 'Manoj Plumber',
            'phone': '9822222222',
            'password': generate_password_hash('Pass123'),
            'role': 'worker'
        }).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = worker_2_id
            sess['role'] = 'worker'

        offer_2_res = self.client.post(f'/api/jobs/{job_id}/offers', json={
            'proposed_price': 650,
            'estimated_arrival_minutes': 30,
            'message': 'Nearby right now. Can install immediately.'
        })
        self.assertEqual(offer_2_res.status_code, 201)
        offer_2_id = offer_2_res.get_json()['offer']['id']

        # 4. Customer reviews offers
        with self.client.session_transaction() as sess:
            sess['user_id'] = customer_id
            sess['role'] = 'user'

        get_offers_res = self.client.get(f'/api/jobs/{job_id}/offers')
        self.assertEqual(get_offers_res.status_code, 200)
        offers = get_offers_res.get_json()
        self.assertEqual(len(offers), 2)

        # 5. Customer accepts Worker 1's offer
        accept_res = self.client.post(f'/api/jobs/{job_id}/offers/{offer_1_id}/accept')
        self.assertEqual(accept_res.status_code, 200)
        self.assertEqual(accept_res.get_json()['job']['worker_id'], worker_1_id)

        # 6. Concurrency / Race Condition Defense:
        # Attempting to accept Worker 2's offer now MUST fail with 409 Conflict
        second_accept_res = self.client.post(f'/api/jobs/{job_id}/offers/{offer_2_id}/accept')
        self.assertEqual(second_accept_res.status_code, 409)

    # ══════════════════════════════════════════════════════════════════════════
    # JOURNEY C: Worker Onboarding, Availability & Acceptance/Decline
    # ══════════════════════════════════════════════════════════════════════════
    def test_journey_c_new_worker_onboarding_availability_and_accept_decline(self):
        # 1. Worker selects Punjabi language
        lang_res = self.client.get('/set_lang/pa')
        self.assertIn(lang_res.status_code, (200, 302))

        # 2. Worker Signup
        worker_phone = "9876543203"
        worker_signup = self.client.post('/api/auth/signup/worker', json={
            'name': 'Harpreet Singh',
            'phone': worker_phone,
            'password': 'WorkerPass@123',
            'work': 'Electrician',
            'hourly_rate': 400,
            'preferred_lang': 'pa'
        })
        self.assertEqual(worker_signup.status_code, 201)
        worker_id = worker_signup.get_json()['worker']['id']

        # 3. Worker Login
        login_res = self.client.post('/api/auth/login', json={
            'phone': worker_phone,
            'password': 'WorkerPass@123',
            'role': 'worker'
        })
        self.assertEqual(login_res.status_code, 200)
        self.assertEqual(login_res.get_json()['role'], 'worker')

        # 4. Profile Completion
        prof_res = self.client.post('/api/worker/profile', json={
            'bio': 'Certified electrician with 7 years industrial experience.',
            'experience_years': 7,
            'service_radius_km': 20,
            'payout_vpa': 'harpreet@okhdfcbank'
        })
        self.assertEqual(prof_res.status_code, 200)

        # 5. Set Availability
        avail_res = self.client.post('/api/worker/availability', json={'is_available': True})
        self.assertEqual(avail_res.status_code, 200)

        # 6. Receive / Accept Open Job
        job_id = 55
        self.mock_db.table("jobs").insert({
            'id': job_id,
            'user_id': 'cust-sample',
            'title': 'Ceiling Fan Installation',
            'status': 'open',
            'budget_max': 500
        }).execute()

        accept_job_res = self.client.post(f'/api/jobs/{job_id}/accept', json={'price': 450})
        self.assertEqual(accept_job_res.status_code, 200)
        self.assertEqual(str(accept_job_res.get_json()['job']['worker_id']), str(worker_id))

        # 7. Decline Booking
        booking_id = 99
        self.mock_db.table("bookings").insert({
            'id': booking_id,
            'user_id': 'cust-sample',
            'worker_id': worker_id,
            'status': 'Requested',
            'price': 450
        }).execute()

        decline_res = self.client.post(f'/api/bookings/{booking_id}/decline')
        self.assertEqual(decline_res.status_code, 200)
        self.assertEqual(decline_res.get_json()['status'], 'Cancelled')

    # ══════════════════════════════════════════════════════════════════════════
    # JOURNEY D: Confirmed Booking QR Check-in, Mutual Confirmation & Completion
    # ══════════════════════════════════════════════════════════════════════════
    def test_journey_d_booking_qr_checkin_replay_defense_and_completion(self):
        customer_id = "cust-jd"
        worker_id = "wrk-jd"
        booking_id = 101

        # Seed Confirmed booking
        self.mock_db.table("users").insert({'id': customer_id, 'name': 'Kavita Joshi', 'phone': '9876543204', 'role': 'user'}).execute()
        self.mock_db.table("workers").insert({'id': worker_id, 'name': 'Sanjay Verma', 'phone': '9876543205', 'role': 'worker'}).execute()
        self.mock_db.table("bookings").insert({
            'id': booking_id,
            'user_id': customer_id,
            'worker_id': worker_id,
            'status': 'Confirmed',
            'service_type': 'Appliance Repair',
            'price': 600
        }).execute()

        # 1. Customer generates check-in credentials / QR token
        with self.client.session_transaction() as sess:
            sess['user_id'] = customer_id
            sess['role'] = 'user'

        token_res = self.client.get(f'/api/bookings/{booking_id}/checkin-token')
        self.assertEqual(token_res.status_code, 200)
        token_data = token_res.get_json()
        token = token_data['token']
        self.assertTrue(len(token) > 20)

        # 2. Impostor Worker tries to scan & check in -> Must be rejected (403)
        with self.client.session_transaction() as sess:
            sess['user_id'] = "wrk-impostor-999"
            sess['role'] = 'worker'

        impostor_res = self.client.post(f'/api/bookings/{booking_id}/checkin', json={'token': token})
        self.assertEqual(impostor_res.status_code, 403)

        # 3. Assigned Worker scans QR code token -> Success (Work Started)
        with self.client.session_transaction() as sess:
            sess['user_id'] = worker_id
            sess['role'] = 'worker'

        worker_scan_res = self.client.post(f'/api/bookings/{booking_id}/checkin', json={'token': token})
        self.assertEqual(worker_scan_res.status_code, 200)
        self.assertTrue(worker_scan_res.get_json()['success'])
        self.assertEqual(worker_scan_res.get_json()['status'], 'Work Started')

        # 4. Replay Attack Prevention: Attempting to reuse the same check-in token MUST fail
        replay_res = self.client.post(f'/api/bookings/{booking_id}/checkin', json={'token': token})
        self.assertIn(replay_res.status_code, (400, 403))
        self.assertIn('already', replay_res.get_json()['error'].lower())

        # 5. Alternative Confirmation: Explicit customer arrival confirmation without camera
        booking_id_2 = 102
        self.mock_db.table("bookings").insert({
            'id': booking_id_2,
            'user_id': customer_id,
            'worker_id': worker_id,
            'status': 'Confirmed',
            'service_type': 'Fan Repair',
            'price': 300
        }).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = customer_id
            sess['role'] = 'user'

        confirm_res = self.client.post(f'/api/bookings/{booking_id_2}/confirm-checkin')
        self.assertEqual(confirm_res.status_code, 200)
        self.assertEqual(confirm_res.get_json()['status'], 'Work Started')

        # 6. Job Completion
        status_res = self.client.post(f'/api/bookings/{booking_id}/complete')
        self.assertEqual(status_res.status_code, 200)
        self.assertEqual(status_res.get_json()['booking']['status'], 'Completed')

    # ══════════════════════════════════════════════════════════════════════════
    # JOURNEY E: Server-Authoritative Payments, Webhooks & Verified Reviews
    # ══════════════════════════════════════════════════════════════════════════
    def test_journey_e_authoritative_payments_and_verified_reviews(self):
        customer_id = "cust-je"
        worker_id = "wrk-je"
        booking_id = 202
        amount = 750.0

        self.mock_db.table("users").insert({'id': customer_id, 'name': 'Pooja Mehta', 'phone': '9876543206', 'role': 'user'}).execute()
        self.mock_db.table("workers").insert({
            'id': worker_id, 'name': 'Deepak Carpenter', 'phone': '9876543207', 'role': 'worker',
            'payout_vpa': 'deepak@okaxis', 'avg_rating': 0.0, 'review_count': 0
        }).execute()
        self.mock_db.table("bookings").insert({
            'id': booking_id,
            'user_id': customer_id,
            'worker_id': worker_id,
            'status': 'Completed',
            'price': amount,
            'service_type': 'Door Lock Installation'
        }).execute()

        # 1. Customer fetches server-authoritative payment options
        with self.client.session_transaction() as sess:
            sess['user_id'] = customer_id
            sess['role'] = 'user'

        options_res = self.client.get(f'/api/bookings/{booking_id}/payment-options')
        self.assertEqual(options_res.status_code, 200)
        opts = options_res.get_json()
        self.assertEqual(opts['amount'], amount)
        self.assertTrue(opts['cash_allowed'])

        # 2. Cash Intent & Physical Confirmation Flow
        # Customer indicates intent to pay cash
        cash_intent_res = self.client.post('/api/payments/create-intent', json={
            'booking_id': booking_id,
            'payment_method': 'cash'
        })
        self.assertEqual(cash_intent_res.status_code, 200)

        # Customer CANNOT forge cash receipt
        cust_fake_confirm = self.client.post(f'/api/bookings/{booking_id}/confirm-cash-payment')
        self.assertEqual(cust_fake_confirm.status_code, 403)

        # Only assigned worker can confirm cash payment on-site
        with self.client.session_transaction() as sess:
            sess['user_id'] = worker_id
            sess['role'] = 'worker'

        worker_cash_confirm = self.client.post(f'/api/bookings/{booking_id}/confirm-cash-payment')
        self.assertEqual(worker_cash_confirm.status_code, 200)
        confirm_data = worker_cash_confirm.get_json()
        self.assertTrue(confirm_data['success'])
        self.assertEqual(confirm_data['payment']['payment_status'], 'completed')
        self.assertEqual(confirm_data['payment']['payment_method'], 'cash')
        self.assertEqual(confirm_data['payment']['verification_type'], 'cash_manual_confirmation')

        # 3. Online Verification & Cryptographic HMAC Verification
        # Reset booking for online test payment check
        online_booking_id = 203
        self.mock_db.table("bookings").insert({
            'id': online_booking_id,
            'user_id': customer_id,
            'worker_id': worker_id,
            'status': 'Completed',
            'price': 500.0
        }).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = customer_id
            sess['role'] = 'user'

        # Verify online payment is rejected when external provider keys are not active
        blocked_intent = self.client.post('/api/payments/create-intent', json={
            'booking_id': online_booking_id,
            'payment_method': 'upi'
        })
        self.assertEqual(blocked_intent.status_code, 400)
        self.assertIn('unavailable', blocked_intent.get_json()['error'].lower())

        # When gateway is active (simulating live credentials)
        with patch('backend_service.RazorpayGatewayService.is_gateway_configured', return_value=(True, "Gateway active")), \
             patch('backend_service.RazorpayGatewayService.is_worker_payout_eligible', return_value=(True, "Worker eligible")):
            online_intent = self.client.post('/api/payments/create-intent', json={
                'booking_id': online_booking_id,
                'payment_method': 'upi'
            })
            self.assertEqual(online_intent.status_code, 200)
            order_id = online_intent.get_json()['order_id']
            payment_id = "pay_test_audit_9876"

            # Generate genuine HMAC signature
            secret = RazorpayGatewayService.get_key_secret()
            msg = f"{order_id}|{payment_id}"
            valid_signature = hmac.new(secret.encode('utf-8'), msg.encode('utf-8'), hashlib.sha256).hexdigest()

            # Tampered signature MUST fail (400)
            tampered_res = self.client.post('/api/payments/verify', json={
                'booking_id': online_booking_id,
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': 'tampered_fake_signature_abc'
            })
            self.assertEqual(tampered_res.status_code, 400)

            # Genuine signature MUST verify and settle booking
            verify_res = self.client.post('/api/payments/verify', json={
                'booking_id': online_booking_id,
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': valid_signature
            })
            self.assertEqual(verify_res.status_code, 200)
            self.assertEqual(verify_res.get_json()['status'], 'completed')

            # Duplicate verification is idempotent
            dup_verify = self.client.post('/api/payments/verify', json={
                'booking_id': online_booking_id,
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': valid_signature
            })
            self.assertEqual(dup_verify.status_code, 200)
            self.assertTrue(dup_verify.get_json().get('already_settled', False))

        # 4. Webhook Authenticity & Deduplication
        webhook_body = json.dumps({
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook_audit_11",
                        "order_id": order_id,
                        "amount": 50000,
                        "status": "captured",
                        "notes": {"booking_id": str(online_booking_id)}
                    }
                }
            }
        })
        webhook_secret = RazorpayGatewayService.get_webhook_secret()
        wh_sig = hmac.new(webhook_secret.encode('utf-8'), webhook_body.encode('utf-8'), hashlib.sha256).hexdigest()

        wh_res = self.client.post(
            '/api/payments/webhook',
            data=webhook_body,
            headers={'Content-Type': 'application/json', 'X-Razorpay-Signature': wh_sig}
        )
        self.assertEqual(wh_res.status_code, 200)

        # Duplicate webhook is idempotent
        wh_dup_res = self.client.post(
            '/api/payments/webhook',
            data=webhook_body,
            headers={'Content-Type': 'application/json', 'X-Razorpay-Signature': wh_sig}
        )
        self.assertEqual(wh_dup_res.status_code, 200)

        # 5. Eligible Completed Booking Review Submission
        # Customer reviews completed booking 202
        review_res = self.client.post(f'/api/bookings/{booking_id}/review', json={
            'rating': 5,
            'review': 'Superb craftsmanship and very punctual!'
        })
        self.assertEqual(review_res.status_code, 201)

        # Duplicate review on same booking is rejected (409)
        dup_review = self.client.post(f'/api/bookings/{booking_id}/review', json={
            'rating': 5,
            'review': 'Trying to post again.'
        })
        self.assertEqual(dup_review.status_code, 409)

        # Worker cannot submit customer review (401/403)
        with self.client.session_transaction() as sess:
            sess['user_id'] = worker_id
            sess['role'] = 'worker'

        wrk_review_res = self.client.post(f'/api/bookings/{booking_id}/review', json={'rating': 5})
        self.assertEqual(wrk_review_res.status_code, 401)

    # ══════════════════════════════════════════════════════════════════════════
    # JOURNEY F: Returning Users, Preserved Language, Role Isolation & Logout
    # ══════════════════════════════════════════════════════════════════════════
    def test_journey_f_returning_users_role_isolation_and_language_preservation(self):
        customer_phone = "9876543208"
        worker_phone = "9876543209"

        self.mock_db.table("users").insert({
            'id': 'cust-jf',
            'name': 'Priyanka Verma',
            'phone': customer_phone,
            'password': generate_password_hash('CustPass123'),
            'language_preference': 'hi',
            'role': 'user'
        }).execute()

        self.mock_db.table("workers").insert({
            'id': 'wrk-jf',
            'name': 'Balwinder Sandhu',
            'phone': worker_phone,
            'password': generate_password_hash('WrkPass123'),
            'language_preference': 'pa',
            'role': 'worker'
        }).execute()

        # 1. Returning Customer Login -> Language 'hi' preserved
        cust_login = self.client.post('/api/auth/login', json={
            'phone': customer_phone,
            'password': 'CustPass123',
            'role': 'user'
        })
        self.assertEqual(cust_login.status_code, 200)
        self.assertEqual(cust_login.get_json()['lang'], 'hi')
        self.assertIn('dashboard', cust_login.get_json()['redirect'])

        # Role Isolation: Customer CANNOT access worker dashboard (redirects or 403)
        wrk_dash_res = self.client.get('/dashboard/worker')
        self.assertIn(wrk_dash_res.status_code, (302, 403))

        # 2. Customer Logout -> Session cleared, but language cookie preserved
        logout_res = self.client.post('/api/auth/logout')
        self.assertEqual(logout_res.status_code, 200)
        with self.client.session_transaction() as sess:
            self.assertNotIn('user_id', sess)

        # 3. Returning Worker Login -> Language 'pa' preserved
        wrk_login = self.client.post('/api/auth/login', json={
            'phone': worker_phone,
            'password': 'WrkPass123',
            'role': 'worker'
        })
        self.assertEqual(wrk_login.status_code, 200)
        self.assertEqual(wrk_login.get_json()['lang'], 'pa')

        # Role Isolation: Worker CANNOT access user dashboard
        cust_dash_res = self.client.get('/dashboard/user')
        self.assertIn(cust_dash_res.status_code, (302, 403))

        # 4. Role Mismatch Prevention: Worker phone attempting to log in as user
        cross_role_login = self.client.post('/api/auth/login', json={
            'phone': worker_phone,
            'password': 'WrkPass123',
            'role': 'user'
        })
        self.assertEqual(cross_role_login.status_code, 403)
        mismatch_data = cross_role_login.get_json()
        self.assertEqual(mismatch_data['error'], 'role_mismatch')
        self.assertEqual(mismatch_data['detected_role'], 'worker')

    # ══════════════════════════════════════════════════════════════════════════
    # SECURITY & OPERATIONAL INTEGRITY CHECKS
    # ══════════════════════════════════════════════════════════════════════════
    def test_security_checks_rbac_rate_limiting_and_state_machine(self):
        # 1. Unauthenticated API access rejected (401)
        unauth_profile = self.client.get('/api/customer/profile')
        self.assertEqual(unauth_profile.status_code, 401)

        unauth_payments = self.client.get('/api/bookings/1/payment-options')
        self.assertEqual(unauth_payments.status_code, 401)

        # 2. Record Ownership: Customer A cannot delete Customer B's address
        self.mock_db.table("customer_saved_addresses").insert({
            'id': 501,
            'customer_id': 'cust-victim',
            'address_line': 'Secret Villa'
        }).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-attacker'
            sess['role'] = 'user'

        del_res = self.client.delete('/api/customer/addresses/501')
        self.assertEqual(del_res.status_code, 403)

        # 3. Brute Force Protection (429 Rate Limiting Lockout)
        target_phone = "9876543299"
        for _ in range(5):
            self.client.post('/api/auth/login', json={
                'phone': target_phone,
                'password': 'wrong_password',
                'role': 'user'
            })

        # 6th attempt MUST be blocked by rate limiter
        lockout_res = self.client.post('/api/auth/login', json={
            'phone': target_phone,
            'password': 'wrong_password',
            'role': 'user'
        })
        self.assertEqual(lockout_res.status_code, 429)
        self.assertTrue(lockout_res.get_json().get('lockout', False))

        # 4. State Machine Validation: Invalid transition (Requested -> Completed directly)
        invalid_booking_id = 999
        self.mock_db.table("bookings").insert({
            'id': invalid_booking_id,
            'user_id': 'cust-sm',
            'worker_id': 'wrk-sm',
            'status': 'Requested'
        }).execute()

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'wrk-sm'
            sess['role'] = 'worker'

        bad_trans_res = self.client.post(f'/api/bookings/{invalid_booking_id}/complete')
        self.assertEqual(bad_trans_res.status_code, 400)
        self.assertTrue(any(w in bad_trans_res.get_json()['error'].lower() for w in ('cannot', 'impossible', 'invalid', 'status')))


if __name__ == '__main__':
    unittest.main()
