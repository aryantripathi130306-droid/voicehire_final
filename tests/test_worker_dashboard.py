"""
VoiceHire — Automated Test Suite for Worker Dashboard
═════════════════════════════════════════════════════
Validates:
  1. Worker authentication enforcement on dashboard and API endpoints
  2. Nearby jobs filtering by category, radius, urgency, and search
  3. Privacy preservation: customer phone and exact coordinates shielded for unassigned workers
  4. Haversine distance calculations and service coverage radius enforcement
  5. Worker profile summary & service area updates
  6. Worker availability toggle (on-duty / off-duty)
  7. Concurrency shield: Atomic CAS job acceptance & HTTP 409 Conflict handling on double-acceptance
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from app import app
from backend_service import LocationPrivacyShield, JobConcurrencyShield


class MockPostgresQuery:
    """Mock PostgREST query builder for worker dashboard testing."""
    def __init__(self, data=None):
        self._data = data if data is not None else []
        self._filters = {}
        self._selected_cols = "*"
        self._pending_updates = None

    def select(self, cols="*"):
        self._selected_cols = cols
        return self

    def eq(self, key, val):
        self._filters[key] = val
        return self

    def in_(self, key, values):
        self._filters[f"{key}__in"] = list(values)
        return self

    def ilike(self, key, val):
        clean = val.replace("%", "").lower()
        self._filters[f"{key}__ilike"] = clean
        return self

    def order(self, col, desc=False):
        return self

    def limit(self, n):
        return self

    def update(self, updates):
        self._pending_updates = dict(updates)
        return self

    def insert(self, record):
        if isinstance(record, dict):
            self._data.append(dict(record))
        elif isinstance(record, list):
            for r in record:
                self._data.append(dict(r))
        return self

    def execute(self):
        resp = MagicMock()
        filtered = list(self._data)

        for k, v in self._filters.items():
            if k.endswith("__in"):
                field = k[:-4]
                filtered = [r for r in filtered if r.get(field) in v]
            elif k.endswith("__ilike"):
                field = k[:-7]
                filtered = [r for r in filtered if v in str(r.get(field, "")).lower()]
            else:
                filtered = [r for r in filtered if r.get(k) == v]

        if self._pending_updates is not None:
            for r in filtered:
                r.update(self._pending_updates)
            resp.data = filtered
            return resp

        resp.data = [dict(r) for r in filtered]
        return resp


class TestWorkerDashboard(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key'
        self.client = app.test_client()

        # Shared mock database state
        self.workers_data = [
            {
                "id": "worker-uuid-1",
                "name": "Raju Sharma",
                "phone": "9876543210",
                "password": "hashed-secret-pw",
                "work": "Plumber",
                "location": "Indirapuram, Ghaziabad",
                "latitude": 28.6366,
                "longitude": 77.3687,
                "live_lat": 28.6366,
                "live_lng": 77.3687,
                "service_radius_km": 15,
                "is_available": True,
                "is_verified": True,
                "price": 500,
                "rating": 4.8
            }
        ]

        self.jobs_data = [
            {
                "id": 101,
                "user_id": "cust-uuid-1",
                "worker_id": None,
                "user_name": "Amit Kumar",
                "user_phone": "9811122233",
                "service_type": "Plumbing",
                "description": "Fix leaking bathroom pipe and faucet",
                "location": "Indirapuram, Sector 14",
                "latitude": 28.6400,
                "longitude": 77.3750,
                "is_urgent": True,
                "status": "open",
                "price": 550,
                "created_at": "2026-10-15T08:00:00Z"
            },
            {
                "id": 102,
                "user_id": "cust-uuid-2",
                "worker_id": None,
                "user_name": "Priya Singh",
                "user_phone": "9899988877",
                "service_type": "Electrical",
                "description": "Install ceiling fan and bedroom light fixture",
                "location": "Noida Sector 62",
                "latitude": 28.6250,
                "longitude": 77.3600,
                "is_urgent": False,
                "status": "open",
                "price": 400,
                "created_at": "2026-10-15T08:30:00Z"
            },
            {
                "id": 103,
                "user_id": "cust-uuid-3",
                "worker_id": None,
                "user_name": "Deepak Verma",
                "user_phone": "9711100022",
                "service_type": "Carpentry",
                "description": "Fix wooden door hinge and wardrobe handle",
                "location": "Gurugram Cyber Hub",
                "latitude": 28.4900,
                "longitude": 77.0900,
                "is_urgent": False,
                "status": "open",
                "price": 700,
                "created_at": "2026-10-15T07:00:00Z"
            }
        ]

        self.skills_data = [
            {"id": 1, "worker_id": "worker-uuid-1", "skill_name": "Pipe Fitting", "experience_years": 4},
            {"id": 2, "worker_id": "worker-uuid-1", "skill_name": "Water Heaters", "experience_years": 3}
        ]

    def _setup_supabase_mock(self, mock_sb):
        def table_router(table_name):
            if table_name == "workers":
                return MockPostgresQuery(self.workers_data)
            elif table_name == "jobs":
                return MockPostgresQuery(self.jobs_data)
            elif table_name == "worker_skills":
                return MockPostgresQuery(self.skills_data)
            return MockPostgresQuery([])

        mock_sb.table.side_effect = table_router

    # ─────────────────────────────────────────────────────────────────
    # 1. AUTHENTICATION & ACCESS CONTROL
    # ─────────────────────────────────────────────────────────────────
    def test_nearby_jobs_unauthorized_without_session(self):
        """Unauthenticated requests must be rejected with 401."""
        res = self.client.get('/api/workers/nearby')
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertIn('Unauthorized', data['error'])

    def test_nearby_jobs_customer_cannot_access(self):
        """Customer sessions cannot view worker nearby jobs."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'cust-123'
            sess['role'] = 'user'

        res = self.client.get('/api/workers/nearby')
        self.assertEqual(res.status_code, 401)

    # ─────────────────────────────────────────────────────────────────
    # 2. PRIVACY PRESERVATION (CUSTOMER PII SHIELD)
    # ─────────────────────────────────────────────────────────────────
    @patch('app.supabase')
    def test_nearby_jobs_privacy_shield_enforced(self, mock_sb):
        """Open jobs must NOT disclose customer's phone number or exact coordinates to nearby workers."""
        self._setup_supabase_mock(mock_sb)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'worker-uuid-1'
            sess['role'] = 'worker'

        res = self.client.get('/api/workers/nearby')
        self.assertEqual(res.status_code, 200)
        jobs = res.get_json()
        self.assertGreater(len(jobs), 0)

        for job in jobs:
            # Sensitive customer phone number must NOT be exposed
            self.assertNotIn('user_phone', job)
            if 'user_phone_masked' in job:
                self.assertTrue(job['user_phone_masked'].startswith('XXXXXX'))

            # Raw un-fuzzed coordinates must NOT be exposed for unaccepted jobs
            self.assertNotIn('latitude', job)
            self.assertNotIn('longitude', job)

            # Approximate coordinates should be present and rounded (~1.1km)
            self.assertIn('approx_lat', job)
            self.assertIn('approx_lng', job)

            # Customer name formatted safely (first name + initial)
            display_name = job.get('user_name_display')
            self.assertTrue(display_name is not None and len(display_name) > 0)
            self.assertNotIn("Amit Kumar", display_name) # Should be "Amit K."

    # ─────────────────────────────────────────────────────────────────
    # 3. FILTERS: CATEGORY, DISTANCE, URGENCY
    # ─────────────────────────────────────────────────────────────────
    @patch('app.supabase')
    def test_nearby_jobs_category_filter(self, mock_sb):
        """Worker can filter open requests by trade / category."""
        self._setup_supabase_mock(mock_sb)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'worker-uuid-1'
            sess['role'] = 'worker'

        res = self.client.get('/api/workers/nearby?category=Plumbing')
        self.assertEqual(res.status_code, 200)
        jobs = res.get_json()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['service_type'], 'Plumbing')

    @patch('app.supabase')
    def test_nearby_jobs_urgency_filter(self, mock_sb):
        """Worker can filter for urgent emergency jobs."""
        self._setup_supabase_mock(mock_sb)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'worker-uuid-1'
            sess['role'] = 'worker'

        res = self.client.get('/api/workers/nearby?urgent_only=true')
        self.assertEqual(res.status_code, 200)
        jobs = res.get_json()
        for j in jobs:
            self.assertTrue(j.get('is_urgent'))

    @patch('app.supabase')
    def test_nearby_jobs_radius_filter(self, mock_sb):
        """Jobs outside specified radius are excluded when coordinates are available."""
        self._setup_supabase_mock(mock_sb)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'worker-uuid-1'
            sess['role'] = 'worker'

        # Gurugram job (103) is ~35 km from Indirapuram, Ghaziabad (worker)
        # Filtering to 10 km should only return Indirapuram (101) and Noida (102)
        res = self.client.get('/api/workers/nearby?radius_km=10')
        self.assertEqual(res.status_code, 200)
        jobs = res.get_json()
        job_ids = [j['id'] for j in jobs]
        self.assertIn(101, job_ids)
        self.assertIn(102, job_ids)
        self.assertNotIn(103, job_ids)

    # ─────────────────────────────────────────────────────────────────
    # 4. WORKER PROFILE & AVAILABILITY TOGGLE
    # ─────────────────────────────────────────────────────────────────
    @patch('app.supabase')
    def test_worker_profile_endpoint(self, mock_sb):
        """GET /api/worker/profile returns authenticated worker's summary without password."""
        self._setup_supabase_mock(mock_sb)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'worker-uuid-1'
            sess['role'] = 'worker'

        res = self.client.get('/api/worker/profile')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['id'], 'worker-uuid-1')
        self.assertEqual(data['name'], 'Raju Sharma')
        self.assertNotIn('password', data)
        self.assertIn('skills', data)
        self.assertEqual(len(data['skills']), 2)

    @patch('app.supabase')
    def test_worker_availability_toggle(self, mock_sb):
        """POST /api/worker/availability updates worker duty status."""
        self._setup_supabase_mock(mock_sb)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'worker-uuid-1'
            sess['role'] = 'worker'

        res = self.client.post(
            '/api/worker/availability',
            data=json.dumps({"is_available": False}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data['is_available'])
        self.assertFalse(self.workers_data[0]['is_available'])

    @patch('app.supabase')
    def test_worker_service_area_update(self, mock_sb):
        """POST /api/worker/service-area updates registered locality and coverage radius."""
        self._setup_supabase_mock(mock_sb)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'worker-uuid-1'
            sess['role'] = 'worker'

        res = self.client.post(
            '/api/worker/service-area',
            data=json.dumps({"location": "Connaught Place, New Delhi", "radius_km": 25}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.workers_data[0]['location'], 'Connaught Place, New Delhi')
        self.assertEqual(self.workers_data[0]['service_radius_km'], 25)

    # ─────────────────────────────────────────────────────────────────
    # 5. ATOMIC CAS ACCEPTANCE & DOUBLE-ACCEPTANCE CONFLICT (409)
    # ─────────────────────────────────────────────────────────────────
    @patch('app.supabase')
    def test_accept_job_success_and_409_concurrency_conflict(self, mock_sb):
        """
        Validates atomic CAS acceptance:
        First worker succeeds (200), second worker attempting same job receives 409 Conflict.
        """
        self._setup_supabase_mock(mock_sb)

        with self.client.session_transaction() as sess:
            sess['user_id'] = 'worker-uuid-1'
            sess['role'] = 'worker'

        # First worker accepts job 101
        res1 = self.client.post(
            '/api/jobs/101/accept',
            data=json.dumps({"price": 550}),
            content_type='application/json'
        )
        self.assertEqual(res1.status_code, 200)
        data1 = res1.get_json()
        self.assertEqual(data1['message'], 'Job accepted successfully')
        self.assertEqual(self.jobs_data[0]['status'], 'accepted')
        self.assertEqual(self.jobs_data[0]['worker_id'], 'worker-uuid-1')

        # Second worker attempts to accept already accepted job
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'worker-uuid-2'
            sess['role'] = 'worker'

        res2 = self.client.post(
            '/api/jobs/101/accept',
            data=json.dumps({"price": 500}),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 409)
        data2 = res2.get_json()
        self.assertIn('already accepted', data2['error'].lower())

    # ─────────────────────────────────────────────────────────────────
    # 6. HAVERSINE DISTANCE ENGINE VALIDATION
    # ─────────────────────────────────────────────────────────────────
    def test_haversine_distance_calculation(self):
        """Verifies accuracy of Great-Circle Haversine calculations."""
        # Delhi to Mumbai ~1150-1170 km
        dist = LocationPrivacyShield.calculate_distance_km(28.6139, 77.2090, 19.0760, 72.8777)
        self.assertIsNotNone(dist)
        self.assertTrue(1140 <= dist <= 1180)

        # Nearby points in Delhi NCR (~1.5 km)
        near_dist = LocationPrivacyShield.calculate_distance_km(28.6366, 77.3687, 28.6400, 77.3750)
        self.assertIsNotNone(near_dist)
        self.assertTrue(0.5 <= near_dist <= 2.0)

        # Invalid coordinates return None
        self.assertIsNone(LocationPrivacyShield.calculate_distance_km(None, 77.0, 28.0, 77.0))


if __name__ == '__main__':
    unittest.main()
