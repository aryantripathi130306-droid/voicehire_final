"""
VoiceHire — Automated Test Suite for Customer Dashboard & Worker Discovery
═══════════════════════════════════════════════════════════════════════════
Validates:
  1. Customer authentication and role enforcement on dashboard and endpoints
  2. Multi-criteria worker discovery (category, skill, location, distance radius, availability, rating)
  3. No matching workers returns clean empty list without synthetic fabrication
  4. Real worker profile details (skills, completed jobs count, verified reviews, privacy shield)
  5. Inaccessible worker profiles return HTTP 404 Not Found
  6. Direct booking creation with date/slot validation and HTTP 409 double-booking prevention
  7. Post a Job flow with description, location, timing, budget validation, and nearby worker discovery
  8. Job offers retrieval with distance and price comparison
  9. Atomic offer acceptance with competing offer rejection and HTTP 409 conflict guard
  10. Customer privacy protection (shielding exact street address and phone prior to confirmation)
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from app import app
from backend_service import LocationPrivacyShield, JobConcurrencyShield


class MockPostgresQuery:
    """Mock PostgREST query builder for customer dashboard testing."""
    def __init__(self, data=None):
        self._data = [dict(d) for d in data] if data is not None else []
        self._filters = {}
        self._neq_filters = {}
        self._selected_cols = "*"
        self._pending_updates = None
        self._order_col = None
        self._order_desc = False
        self._limit_n = None
        self._or_expr = None

    def select(self, cols="*"):
        self._selected_cols = cols
        return self

    def eq(self, key, val):
        self._filters[key] = val
        return self

    def neq(self, key, val):
        self._neq_filters[key] = val
        return self

    def in_(self, key, values):
        self._filters[f"{key}__in"] = list(values)
        return self

    def ilike(self, key, val):
        clean = val.replace("%", "").lower()
        self._filters[f"{key}__ilike"] = clean
        return self

    def or_(self, expr):
        self._or_expr = expr
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n):
        self._limit_n = n
        return self

    def update(self, updates):
        self._pending_updates = dict(updates)
        return self

    def insert(self, record):
        if isinstance(record, dict):
            new_r = dict(record)
            if 'id' not in new_r:
                new_r['id'] = len(self._data) + 101
            self._data.append(new_r)
            self._last_inserted = [new_r]
        elif isinstance(record, list):
            self._last_inserted = []
            for r in record:
                new_r = dict(r)
                if 'id' not in new_r:
                    new_r['id'] = len(self._data) + 101
                self._data.append(new_r)
                self._last_inserted.append(new_r)
        return self

    def execute(self):
        resp = MagicMock()

        if hasattr(self, '_last_inserted'):
            resp.data = [dict(r) for r in self._last_inserted]
            del self._last_inserted
            return resp

        filtered = list(self._data)

        # Standard filters
        for k, v in self._filters.items():
            if k.endswith("__in"):
                field = k[:-4]
                filtered = [r for r in filtered if r.get(field) in v or str(r.get(field)) in [str(x) for x in v]]
            elif k.endswith("__ilike"):
                field = k[:-7]
                filtered = [r for r in filtered if v in str(r.get(field, "")).lower()]
            else:
                filtered = [r for r in filtered if str(r.get(k)) == str(v)]

        # Neq filters
        for k, v in self._neq_filters.items():
            filtered = [r for r in filtered if str(r.get(k)) != str(v)]

        # OR expression filter
        if self._or_expr:
            parts = [p.strip() for p in self._or_expr.split(",")]
            or_matches = []
            for r in filtered:
                matched = False
                for p in parts:
                    if ".eq." in p:
                        field, val = p.split(".eq.")
                        if str(r.get(field)) == str(val):
                            matched = True
                            break
                if matched:
                    or_matches.append(r)
            filtered = or_matches

        # Updates
        if self._pending_updates is not None:
            for r in filtered:
                r.update(self._pending_updates)
            resp.data = [dict(r) for r in filtered]
            self._pending_updates = None
            return resp

        # Ordering
        if self._order_col:
            filtered.sort(
                key=lambda x: x.get(self._order_col) or "",
                reverse=self._order_desc
            )

        # Limit
        if self._limit_n is not None:
            filtered = filtered[:self._limit_n]

        resp.data = [dict(r) for r in filtered]
        return resp


class TestCustomerDashboard(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-customer-secret-key'
        self.client = app.test_client()

        # Database state for workers
        self.workers_data = [
            {
                "id": "w-elec-1",
                "name": "Amit Sharma",
                "phone": "9876543210",
                "work": "Electrical",
                "experience": 6,
                "price": 550,
                "bio": "Certified commercial and domestic electrician",
                "location": "Connaught Place, New Delhi",
                "latitude": 28.6315,
                "longitude": 77.2167,
                "approx_lat": 28.632,
                "approx_lng": 77.217,
                "is_available": True,
                "is_verified": True,
                "avg_rating": 4.8,
                "review_count": 14,
                "service_area_radius_km": 15
            },
            {
                "id": "w-plumb-2",
                "name": "Suresh Patel",
                "phone": "9811223344",
                "work": "Plumbing",
                "experience": 4,
                "price": 450,
                "bio": "Experienced in pipe repair, leak fixing and sanitary fittings",
                "location": "Karol Bagh, New Delhi",
                "latitude": 28.6514,
                "longitude": 77.1907,
                "approx_lat": 28.652,
                "approx_lng": 77.191,
                "is_available": True,
                "is_verified": True,
                "avg_rating": 4.2,
                "review_count": 8,
                "service_area_radius_km": 12
            },
            {
                "id": "w-carp-3",
                "name": "Harpreet Singh",
                "phone": "9855112233",
                "work": "Carpentry",
                "experience": 9,
                "price": 700,
                "bio": "Expert furniture repair, door and cabinet installation",
                "location": "Noida Sector 62",
                "latitude": 28.6280,
                "longitude": 77.3649,  # ~15 km away from CP
                "approx_lat": 28.629,
                "approx_lng": 77.365,
                "is_available": False,  # Off duty
                "is_verified": True,
                "avg_rating": 4.9,
                "review_count": 22,
                "service_area_radius_km": 20
            }
        ]

        # Worker skills table
        self.worker_skills_data = [
            {"id": 1, "worker_id": "w-elec-1", "skill_name": "Ceiling Fan Repair", "category_id": 2, "experience_years": 5, "is_primary": True},
            {"id": 2, "worker_id": "w-elec-1", "skill_name": "Short Circuit Fixing", "category_id": 2, "experience_years": 6, "is_primary": False},
            {"id": 3, "worker_id": "w-plumb-2", "skill_name": "Pipe Leakage Fixing", "category_id": 1, "experience_years": 4, "is_primary": True},
            {"id": 4, "worker_id": "w-carp-3", "skill_name": "Door Lock Repair", "category_id": 3, "experience_years": 8, "is_primary": True}
        ]

        # Reviews table (verified bookings)
        self.reviews_data = [
            {
                "id": 1,
                "worker_id": "w-elec-1",
                "customer_id": "cust-1",
                "customer_name": "Rahul Verma",
                "rating": 5.0,
                "comment": "Quick and professional electrical work. Fixed my main switchboard in 30 minutes.",
                "created_at": "2026-10-10T14:00:00Z"
            },
            {
                "id": 2,
                "worker_id": "w-elec-1",
                "customer_id": "cust-2",
                "customer_name": "Priya Sharma",
                "rating": 4.6,
                "comment": "Punctual and polite. Fair rates.",
                "created_at": "2026-10-12T10:00:00Z"
            }
        ]

        # Bookings table
        self.bookings_data = [
            {
                "id": 101,
                "customer_id": "cust-1",
                "worker_id": "w-elec-1",
                "date": "2026-10-10",
                "time_slot": "10:00 AM - 12:00 PM",
                "notes": "Main switchboard repair",
                "status": "Completed",
                "total_price": 550,
                "qr_token": "token-completed-1"
            },
            {
                "id": 102,
                "customer_id": "cust-2",
                "worker_id": "w-elec-1",
                "date": "2026-10-20",
                "time_slot": "13:00-15:00",
                "notes": "Fan installation",
                "status": "Booked",
                "total_price": 550,
                "qr_token": "token-booked-2"
            }
        ]

        # Jobs table
        self.jobs_data = [
            {
                "id": 501,
                "user_id": "cust-1",
                "service_type": "Electrical Repair",
                "description": "Geyser not heating and power tripping in bathroom",
                "location": "Connaught Place, New Delhi",
                "lat": 28.6315,
                "lng": 77.2167,
                "latitude": 28.6315,
                "longitude": 77.2167,
                "budget_min": 400,
                "budget_max": 800,
                "is_urgent": True,
                "status": "open",
                "created_at": "2026-10-15T09:00:00Z"
            }
        ]

        # Job offers table
        self.job_offers_data = [
            {
                "id": 801,
                "job_id": 501,
                "worker_id": "w-elec-1",
                "proposed_price": 500.0,
                "estimated_arrival_minutes": 25,
                "message": "I am 2 km away in CP. Can reach within 25 minutes with testing tools.",
                "status": "pending",
                "created_at": "2026-10-15T09:15:00Z"
            },
            {
                "id": 802,
                "job_id": 501,
                "worker_id": "w-plumb-2",
                "proposed_price": 600.0,
                "estimated_arrival_minutes": 40,
                "message": "Available in Karol Bagh, can inspect plumbing and electrical connection.",
                "status": "pending",
                "created_at": "2026-10-15T09:20:00Z"
            }
        ]

        # Users table
        self.users_data = [
            {
                "id": "cust-1",
                "name": "Rahul Verma",
                "phone": "9998887771",
                "locality": "Connaught Place"
            },
            {
                "id": "cust-2",
                "name": "Priya Sharma",
                "phone": "9998887772",
                "locality": "Lajpat Nagar"
            }
        ]

    def _mock_supabase(self, mock_client):
        """Configure mock supabase client with data tables."""
        def table_side_effect(table_name):
            if table_name == "workers":
                return MockPostgresQuery(self.workers_data)
            elif table_name == "worker_skills":
                return MockPostgresQuery(self.worker_skills_data)
            elif table_name == "reviews":
                return MockPostgresQuery(self.reviews_data)
            elif table_name == "bookings":
                return MockPostgresQuery(self.bookings_data)
            elif table_name == "jobs":
                return MockPostgresQuery(self.jobs_data)
            elif table_name == "job_offers":
                return MockPostgresQuery(self.job_offers_data)
            elif table_name == "users":
                return MockPostgresQuery(self.users_data)
            return MockPostgresQuery([])

        mock_client.table.side_effect = table_side_effect

    # ─────────────────────────────────────────────────────────────────────────
    # 1. AUTHENTICATION & ROLE ENFORCEMENT
    # ─────────────────────────────────────────────────────────────────────────

    def test_customer_dashboard_unauthenticated_redirects(self):
        """Unauthenticated visitor trying to access /dashboard/user is redirected to login."""
        res = self.client.get('/dashboard/user')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    def test_worker_cannot_access_customer_dashboard(self):
        """Worker role attempting to access customer dashboard is redirected."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'worker-1'
            sess['role'] = 'worker'
            sess['name'] = 'Worker User'

        res = self.client.get('/dashboard/user')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers.get('Location', ''))

    @patch('app.supabase')
    def test_customer_dashboard_authenticated_success(self, mock_sb):
        """Authenticated customer can access customer dashboard."""
        self._mock_supabase(mock_sb)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'
            sess['name'] = 'Rahul Verma'

        res = self.client.get('/dashboard/user')
        self.assertEqual(res.status_code, 200)
        content = res.get_data(as_text=True)
        self.assertIn('Customer Dashboard', content)
        self.assertIn('Available Service Professionals', content)
        self.assertIn('Post a Job Request', content)

    # ─────────────────────────────────────────────────────────────────────────
    # 2. WORKER DISCOVERY & MULTI-CRITERIA FILTERING
    # ─────────────────────────────────────────────────────────────────────────

    @patch('app.supabase')
    def test_filter_workers_by_category(self, mock_sb):
        """Filter workers by service category."""
        self._mock_supabase(mock_sb)
        res = self.client.get('/api/workers?category=Electrical')
        self.assertEqual(res.status_code, 200)
        workers = json.loads(res.data)
        self.assertEqual(len(workers), 1)
        self.assertEqual(workers[0]['work'], 'Electrical')
        self.assertEqual(workers[0]['name'], 'Amit Sharma')

    @patch('app.supabase')
    def test_filter_workers_by_skill_keyword(self, mock_sb):
        """Filter workers by specialized skill from worker_skills table."""
        self._mock_supabase(mock_sb)
        res = self.client.get('/api/workers?skill=Pipe')
        self.assertEqual(res.status_code, 200)
        workers = json.loads(res.data)
        self.assertEqual(len(workers), 1)
        self.assertEqual(workers[0]['name'], 'Suresh Patel')
        self.assertEqual(workers[0]['work'], 'Plumbing')

    @patch('app.supabase')
    def test_filter_workers_by_distance_radius(self, mock_sb):
        """Filter workers by coordinates and radius: Connaught Place to Noida ~15km."""
        self._mock_supabase(mock_sb)
        # Search within 5km of Connaught Place (28.6315, 77.2167)
        # Amit Sharma is at CP (~0.1 km)
        # Suresh Patel is at Karol Bagh (~3 km)
        # Harpreet Singh is at Noida Sector 62 (~15 km)
        res = self.client.get('/api/workers?lat=28.6315&lng=77.2167&radius_km=5')
        self.assertEqual(res.status_code, 200)
        workers = json.loads(res.data)
        names = [w['name'] for w in workers]
        self.assertIn('Amit Sharma', names)
        self.assertIn('Suresh Patel', names)
        self.assertNotIn('Harpreet Singh', names)  # Beyond 5 km

    @patch('app.supabase')
    def test_filter_workers_available_only(self, mock_sb):
        """Filter by availability excludes off-duty workers."""
        self._mock_supabase(mock_sb)
        res = self.client.get('/api/workers?available_only=true')
        self.assertEqual(res.status_code, 200)
        workers = json.loads(res.data)
        for w in workers:
            self.assertTrue(w.get('is_available'))
        names = [w['name'] for w in workers]
        self.assertNotIn('Harpreet Singh', names)  # Harpreet has is_available=False

    @patch('app.supabase')
    def test_filter_workers_by_min_rating(self, mock_sb):
        """Filter by minimum rating (e.g. 4.5+)."""
        self._mock_supabase(mock_sb)
        res = self.client.get('/api/workers?min_rating=4.5')
        self.assertEqual(res.status_code, 200)
        workers = json.loads(res.data)
        names = [w['name'] for w in workers]
        self.assertIn('Amit Sharma', names)    # 4.8
        self.assertNotIn('Suresh Patel', names) # 4.2

    @patch('app.supabase')
    def test_sort_workers_by_price_asc(self, mock_sb):
        """Sort workers by lowest indicative rate first."""
        self._mock_supabase(mock_sb)
        res = self.client.get('/api/workers?sort_by=price_asc')
        self.assertEqual(res.status_code, 200)
        workers = json.loads(res.data)
        prices = [w['price'] for w in workers if w.get('price')]
        self.assertEqual(prices, sorted(prices))

    @patch('app.supabase')
    def test_no_matching_workers_returns_empty_list(self, mock_sb):
        """Searching for non-existent service returns empty list without inventing fake workers."""
        self._mock_supabase(mock_sb)
        res = self.client.get('/api/workers?category=AerospaceEngineering')
        self.assertEqual(res.status_code, 200)
        workers = json.loads(res.data)
        self.assertEqual(workers, [])

    # ─────────────────────────────────────────────────────────────────────────
    # 3. REAL WORKER PROFILES & PRIVACY SHIELD
    # ─────────────────────────────────────────────────────────────────────────

    @patch('app.supabase')
    def test_get_worker_profile_detail_with_skills_and_reviews(self, mock_sb):
        """Profile detail endpoint returns verified reviews, skills, completed job counts."""
        self._mock_supabase(mock_sb)
        res = self.client.get('/api/workers/w-elec-1')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)

        self.assertEqual(data['name'], 'Amit Sharma')
        self.assertEqual(data['work'], 'Electrical')
        self.assertEqual(data['price'], 550)
        self.assertEqual(data['completed_jobs_count'], 1)  # 1 completed booking in mock data
        self.assertEqual(len(data['skills']), 2)
        self.assertEqual(len(data['reviews']), 2)
        cust_names = [r['customer_name'] for r in data['reviews']]
        self.assertIn('Rahul Verma', cust_names)
        self.assertIn('Priya Sharma', cust_names)

        # Privacy Shield: Password must NOT be present, raw phone stripped and masked for general browser
        self.assertNotIn('password', data)
        self.assertNotIn('password_hash', data)
        self.assertNotIn('phone', data)
        self.assertEqual(data.get('phone_masked'), 'XXXXXX3210')

    @patch('app.supabase')
    def test_inaccessible_worker_profile_returns_404(self, mock_sb):
        """Non-existent worker ID returns HTTP 404 Not Found."""
        self._mock_supabase(mock_sb)
        res = self.client.get('/api/workers/non-existent-worker-999')
        self.assertEqual(res.status_code, 404)
        data = json.loads(res.data)
        self.assertIn('Worker not found', data.get('error', ''))

    # ─────────────────────────────────────────────────────────────────────────
    # 4. DIRECT BOOKING CREATION & CONCURRENCY GUARD
    # ─────────────────────────────────────────────────────────────────────────

    @patch('app.supabase')
    def test_direct_booking_successful(self, mock_sb):
        """Customer successfully creates a direct booking for an available worker."""
        self._mock_supabase(mock_sb)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'
            sess['name'] = 'Rahul Verma'

        payload = {
            "worker_id": "w-elec-1",
            "date": "2026-10-25",
            "time_slot": "09:00-11:00",
            "notes": "Install three new 16A wall sockets in study room"
        }
        res = self.client.post('/api/bookings', json=payload)
        self.assertEqual(res.status_code, 201)
        data = json.loads(res.data)
        self.assertIn('Booking confirmed', data.get('message', ''))
        self.assertIn('booking_id', data)

    @patch('app.supabase')
    def test_direct_booking_slot_conflict_returns_409(self, mock_sb):
        """Attempting to book an already occupied slot returns HTTP 409 Conflict."""
        self._mock_supabase(mock_sb)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'
            sess['name'] = 'Rahul Verma'

        # Already booked in setUp: 2026-10-20, 13:00-15:00
        conflict_payload = {
            "worker_id": "w-elec-1",
            "date": "2026-10-20",
            "time_slot": "13:00-15:00",
            "notes": "Need urgent electrical wiring"
        }
        res = self.client.post('/api/bookings', json=conflict_payload)
        self.assertEqual(res.status_code, 409)
        data = json.loads(res.data)
        self.assertIn('already booked', data.get('error', '').lower())

    @patch('app.supabase')
    def test_direct_booking_invalid_slot_or_date(self, mock_sb):
        """Invalid time slot or malformed date returns HTTP 400 Bad Request."""
        self._mock_supabase(mock_sb)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'
            sess['name'] = 'Rahul Verma'

        # Invalid slot
        res1 = self.client.post('/api/bookings', json={
            "worker_id": "w-elec-1",
            "date": "2026-10-25",
            "time_slot": "Midnight 3 AM",
            "notes": "Test"
        })
        self.assertEqual(res1.status_code, 400)

        # Invalid date format
        res2 = self.client.post('/api/bookings', json={
            "worker_id": "w-elec-1",
            "date": "25-10-2026",  # Not YYYY-MM-DD
            "time_slot": "10:00 AM - 12:00 PM",
            "notes": "Test"
        })
        self.assertEqual(res2.status_code, 400)

    # ─────────────────────────────────────────────────────────────────────────
    # 5. POST A JOB REQUEST FLOW
    # ─────────────────────────────────────────────────────────────────────────

    @patch('app.supabase')
    def test_post_job_request_successful(self, mock_sb):
        """Customer successfully posts a job request."""
        self._mock_supabase(mock_sb)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'
            sess['name'] = 'Rahul Verma'

        payload = {
            "service_type": "Plumbing",
            "description": "Bathroom sink drain pipe is completely blocked and leaking underneath",
            "location": "Connaught Place, New Delhi",
            "is_urgent": True,
            "budget_min": 300,
            "budget_max": 600
        }
        res = self.client.post('/api/jobs', json=payload)
        self.assertEqual(res.status_code, 201)
        data = json.loads(res.data)
        self.assertIn('Job posted successfully', data.get('message', ''))
        self.assertEqual(data['job']['service_type'], 'Plumbing')
        self.assertEqual(data['job']['status'], 'open')

    @patch('app.supabase')
    def test_post_job_budget_validation(self, mock_sb):
        """Posting a job with budget_min > budget_max returns HTTP 400."""
        self._mock_supabase(mock_sb)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'
            sess['name'] = 'Rahul Verma'

        payload = {
            "service_type": "Carpentry",
            "description": "Fix wooden wardrobe door hinges",
            "location": "Delhi",
            "budget_min": 800,
            "budget_max": 400  # Invalid min > max
        }
        res = self.client.post('/api/jobs', json=payload)
        self.assertEqual(res.status_code, 400)
        data = json.loads(res.data)
        self.assertIn('Minimum budget cannot be greater', data.get('error', ''))

    @patch('app.supabase')
    def test_post_job_missing_fields_validation(self, mock_sb):
        """Posting a job without required service_type, description or location returns HTTP 400."""
        self._mock_supabase(mock_sb)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'
            sess['name'] = 'Rahul Verma'

        payload = {
            "service_type": "",
            "description": "",
            "location": ""
        }
        res = self.client.post('/api/jobs', json=payload)
        self.assertEqual(res.status_code, 400)

    # ─────────────────────────────────────────────────────────────────────────
    # 6. OFFERS COMPARISON & ATOMIC ACCEPTANCE
    # ─────────────────────────────────────────────────────────────────────────

    @patch('app.supabase')
    def test_get_customer_jobs_with_offers_count(self, mock_sb):
        """Customer retrieves their jobs with pending offers count attached."""
        self._mock_supabase(mock_sb)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'
            sess['name'] = 'Rahul Verma'

        res = self.client.get('/api/jobs/customer')
        self.assertEqual(res.status_code, 200)
        jobs = json.loads(res.data)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['id'], 501)
        self.assertEqual(jobs[0]['offers_count'], 2)  # Two offers submitted in mock data

    @patch('app.supabase')
    def test_get_job_offers_enriched_with_worker_details(self, mock_sb):
        """Job owner retrieves proposals enriched with worker stats, rating and distance."""
        self._mock_supabase(mock_sb)
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'
            sess['name'] = 'Rahul Verma'

        res = self.client.get('/api/jobs/501/offers')
        self.assertEqual(res.status_code, 200)
        offers = json.loads(res.data)
        self.assertEqual(len(offers), 2)

        # First offer by Amit Sharma (CP - distance ~0km)
        o1 = next(o for o in offers if o['id'] == 801)
        self.assertEqual(o1['proposed_price'], 500.0)
        self.assertEqual(o1['estimated_arrival_minutes'], 25)
        self.assertEqual(o1['worker']['name'], 'Amit Sharma')
        self.assertEqual(o1['worker']['work'], 'Electrical')
        self.assertIn('distance_km', o1['worker'])

    @patch('backend_service.JobConcurrencyShield.atomic_accept_offer')
    @patch('app.supabase')
    def test_accept_job_offer_successful(self, mock_sb, mock_accept_offer):
        """Customer accepts one offer; job is assigned and competing offers resolved."""
        self._mock_supabase(mock_sb)
        mock_accept_offer.return_value = (
            True,
            "success",
            {"id": 501, "worker_id": "w-elec-1", "price": 500.0, "status": "assigned"}
        )

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'
            sess['name'] = 'Rahul Verma'

        res = self.client.post('/api/jobs/501/offers/801/accept')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertIn('Offer accepted', data.get('message', ''))
        self.assertEqual(data['job']['status'], 'assigned')

    @patch('backend_service.JobConcurrencyShield.atomic_accept_offer')
    @patch('app.supabase')
    def test_accept_job_offer_conflict_already_taken(self, mock_sb, mock_accept_offer):
        """Accepting an offer on a job that is already closed returns HTTP 409 Conflict."""
        self._mock_supabase(mock_sb)
        mock_accept_offer.return_value = (False, "already_taken", None)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-1'
            sess['role'] = 'user'
            sess['name'] = 'Rahul Verma'

        res = self.client.post('/api/jobs/501/offers/801/accept')
        self.assertEqual(res.status_code, 409)
        data = json.loads(res.data)
        self.assertIn('no longer open', data.get('error', '').lower())

    # ─────────────────────────────────────────────────────────────────────────
    # 7. PRIVACY SHIELD FOR CUSTOMER AND WORKER
    # ─────────────────────────────────────────────────────────────────────────

    def test_customer_privacy_shield_masks_exact_address_for_unassigned_workers(self):
        """Customer phone and exact address are hidden until worker is assigned."""
        raw_job = {
            "id": 501,
            "user_id": "cust-1",
            "user_name": "Rahul Verma",
            "user_phone": "9998887771",
            "location": "Flat 402, Block B, Barakhamba Road, Connaught Place, New Delhi",
            "latitude": 28.6315,
            "longitude": 77.2167,
            "service_type": "Electrical"
        }

        # Viewer is not assigned:
        shielded = LocationPrivacyShield.obfuscate_job_request(raw_job, viewer_is_assigned_worker=False)
        self.assertNotIn('user_phone', shielded)
        self.assertEqual(shielded.get('user_phone_masked'), 'XXXXXX7771')
        self.assertNotIn('latitude', shielded)
        self.assertNotIn('longitude', shielded)
        self.assertIn('approx_lat', shielded)

        # Viewer is assigned:
        unshielded = LocationPrivacyShield.obfuscate_job_request(raw_job, viewer_is_assigned_worker=True)
        self.assertEqual(unshielded.get('user_phone'), '9998887771')


if __name__ == '__main__':
    unittest.main()
