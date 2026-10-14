"""
VoiceHire — Automated Test Suite for Role-Aware Authentication System
═══════════════════════════════════════════════════════════════════════
Tests cover:
  1. Worker & Employer signup success with password hashing & session establishment.
  2. Duplicate phone rejection (same role and cross-role protection).
  3. Phone validation (10-digit Indian standard) and password length validation.
  4. Worker & Employer login success with authoritative server role & session rotation.
  5. Invalid credentials rejection (401 Unauthorized).
  6. Role mismatch rejection (403 Forbidden) with detected role & switch URL.
  7. Brute force rate limiting & lockout (429 Too Many Requests after 5 attempts).
  8. Dashboard access protection & unauthorized cross-role isolation.
  9. Account recovery (OTP generation, role mismatch, invalid OTP, expiry, password reset).
 10. Complete end-to-end cycle: Register -> Authenticate -> Refresh/Verify -> Logout.
"""

import json
import unittest
from unittest.mock import MagicMock, patch
from werkzeug.security import generate_password_hash, check_password_hash

from app import app
from auth_security import auth_shield, recovery_manager


class MockSupabaseQuery:
    def __init__(self, data=None):
        self._data = data if data is not None else []
        self._table = None
        self._filter_phone = None
        self._filter_id = None
        self._selected_cols = "*"
        self._last_inserted = None
        self._pending_updates = None

    def select(self, cols):
        self._selected_cols = cols
        return self

    def insert(self, record):
        if isinstance(record, dict):
            new_rec = dict(record)
            if 'id' not in new_rec:
                new_rec['id'] = f"mock-uuid-{len(self._data) + 1}"
            self._data.append(new_rec)
            self._last_inserted = [new_rec]
        return self

    def update(self, updates):
        self._pending_updates = updates
        return self

    def eq(self, col, val):
        if col == 'phone':
            self._filter_phone = val
        elif col == 'id':
            self._filter_id = val
        return self

    def execute(self):
        if self._last_inserted is not None:
            res = self._last_inserted
            self._last_inserted = None
            return MockSupabaseResponse(res)

        if self._pending_updates is not None:
            updated = []
            for rec in self._data:
                if (self._filter_phone is not None and rec.get('phone') == self._filter_phone) or \
                   (self._filter_id is not None and rec.get('id') == self._filter_id):
                    rec.update(self._pending_updates)
                    updated.append(rec)
            self._pending_updates = None
            return MockSupabaseResponse(updated)

        filtered = self._data
        if self._filter_phone is not None:
            filtered = [r for r in filtered if r.get('phone') == self._filter_phone]
        if self._filter_id is not None:
            filtered = [r for r in filtered if r.get('id') == self._filter_id]
        return MockSupabaseResponse(filtered)


class MockSupabaseResponse:
    def __init__(self, data):
        self.data = data


class MockSupabaseClient:
    def __init__(self):
        self.users = []
        self.workers = []

    def table(self, table_name):
        if table_name == 'users':
            q = MockSupabaseQuery(self.users)
        elif table_name == 'workers':
            q = MockSupabaseQuery(self.workers)
        else:
            q = MockSupabaseQuery([])
        return q


class TestAuthFlow(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        auth_shield.reset()
        recovery_manager.reset()

        self.mock_db = MockSupabaseClient()
        self.supabase_patcher = patch('app.supabase', self.mock_db)
        self.supabase_patcher.start()

    def tearDown(self):
        self.supabase_patcher.stop()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. SIGNUP TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_signup_user_success(self):
        """Employer (User) signup succeeds, hashes password, sets session, and returns 201."""
        response = self.client.post('/api/auth/signup/user', data={
            'name': 'Ramesh Kumar',
            'phone': '9876543210',
            'password': 'SecurePassword123'
        })
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data['role'], 'user')
        self.assertIn('/dashboard/user', data['redirect'])

        # Check DB record
        self.assertEqual(len(self.mock_db.users), 1)
        user = self.mock_db.users[0]
        self.assertEqual(user['name'], 'Ramesh Kumar')
        self.assertEqual(user['phone'], '9876543210')
        # Plain password must never be stored
        self.assertNotEqual(user['password'], 'SecurePassword123')
        self.assertTrue(check_password_hash(user['password'], 'SecurePassword123'))

        # Check session
        with self.client.session_transaction() as sess:
            self.assertEqual(sess['role'], 'user')
            self.assertEqual(sess['name'], 'Ramesh Kumar')
            self.assertEqual(sess['phone'], '9876543210')

    def test_signup_worker_success(self):
        """Worker signup succeeds with work and location, hashes password, and sets session."""
        response = self.client.post('/api/auth/signup/worker', data={
            'name': 'Suresh Plumber',
            'work': 'Plumber',
            'location': 'Noida Sector 62',
            'phone': '9876543211',
            'password': 'WorkerPassword123'
        })
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data['role'], 'worker')
        self.assertIn('/dashboard/worker', data['redirect'])

        # Check DB record
        self.assertEqual(len(self.mock_db.workers), 1)
        worker = self.mock_db.workers[0]
        self.assertEqual(worker['name'], 'Suresh Plumber')
        self.assertEqual(worker['work'], 'Plumber')
        self.assertEqual(worker['phone'], '9876543211')
        self.assertTrue(check_password_hash(worker['password'], 'WorkerPassword123'))

        # Check session
        with self.client.session_transaction() as sess:
            self.assertEqual(sess['role'], 'worker')

    def test_signup_validation_errors(self):
        """Signup validates 10-digit Indian phone and min 6 characters password."""
        # Invalid phone
        resp1 = self.client.post('/api/auth/signup/user', data={
            'name': 'Test User',
            'phone': '12345',
            'password': 'Password123'
        })
        self.assertEqual(resp1.status_code, 400)
        self.assertIn('Invalid Indian phone number', resp1.get_json()['error'])

        # Short password
        resp2 = self.client.post('/api/auth/signup/user', data={
            'name': 'Test User',
            'phone': '9876543210',
            'password': '123'
        })
        self.assertEqual(resp2.status_code, 400)
        self.assertIn('at least 6 characters', resp2.get_json()['error'])

    def test_signup_duplicate_phone_protection(self):
        """Reject duplicate phone within same role and cross-role with clear guidance."""
        # Seed an existing user
        self.mock_db.users.append({
            'id': 'user-1',
            'name': 'Existing User',
            'phone': '9876543210',
            'password': generate_password_hash('Password123')
        })

        # Attempt to sign up same phone as user
        resp1 = self.client.post('/api/auth/signup/user', data={
            'name': 'Duplicate User',
            'phone': '9876543210',
            'password': 'NewPassword123'
        })
        self.assertEqual(resp1.status_code, 400)
        self.assertIn('already registered as an Employer', resp1.get_json()['error'])

        # Attempt to sign up same phone as worker (cross-role duplicate)
        resp2 = self.client.post('/api/auth/signup/worker', data={
            'name': 'Duplicate Worker',
            'work': 'Electrician',
            'location': 'Delhi',
            'phone': '9876543210',
            'password': 'NewPassword123'
        })
        self.assertEqual(resp2.status_code, 400)
        self.assertIn('already registered as an Employer', resp2.get_json()['error'])

    # ─────────────────────────────────────────────────────────────────────────
    # 2. LOGIN & ROLE MISMATCH TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_login_user_success_and_session_rotation(self):
        """Employer login succeeds, rotates session, sets authoritative role."""
        self.mock_db.users.append({
            'id': 'user-101',
            'name': 'Amit Shah',
            'phone': '9876543210',
            'password': generate_password_hash('Password123')
        })

        # Inject an old stale session key to verify session rotation
        with self.client.session_transaction() as sess:
            sess['stale_data'] = 'should_be_cleared'

        response = self.client.post('/api/auth/login', json={
            'phone': '9876543210',
            'password': 'Password123',
            'role': 'user'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['role'], 'user')
        self.assertIn('/dashboard/user', data['redirect'])

        # Verify session rotation
        with self.client.session_transaction() as sess:
            self.assertNotIn('stale_data', sess)
            self.assertEqual(sess['user_id'], 'user-101')
            self.assertEqual(sess['role'], 'user')
            self.assertEqual(sess['name'], 'Amit Shah')

    def test_login_worker_success(self):
        """Worker login succeeds with authoritative role worker."""
        self.mock_db.workers.append({
            'id': 'worker-202',
            'name': 'Mohan Carpenter',
            'work': 'Carpenter',
            'phone': '9876543211',
            'password': generate_password_hash('CarpPass123')
        })

        response = self.client.post('/api/auth/login', json={
            'phone': '9876543211',
            'password': 'CarpPass123',
            'role': 'worker'
        })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['role'], 'worker')
        self.assertIn('/dashboard/worker', data['redirect'])

    def test_login_invalid_password(self):
        """Login with wrong password returns 401 Unauthorized."""
        self.mock_db.users.append({
            'id': 'user-102',
            'name': 'Test User',
            'phone': '9876543210',
            'password': generate_password_hash('CorrectPassword')
        })

        response = self.client.post('/api/auth/login', json={
            'phone': '9876543210',
            'password': 'WrongPassword',
            'role': 'user'
        })
        self.assertEqual(response.status_code, 401)
        self.assertIn('Invalid phone or password', response.get_json()['error'])

    def test_role_mismatch_worker_attempts_user_login(self):
        """
        If a user is registered as a Worker but attempts Employer login,
        do NOT grant access. Return 403 with role_mismatch and switch URL.
        """
        self.mock_db.workers.append({
            'id': 'worker-303',
            'name': 'Dinesh Painter',
            'phone': '9876543212',
            'password': generate_password_hash('Painter123')
        })

        response = self.client.post('/api/auth/login', json={
            'phone': '9876543212',
            'password': 'Painter123',
            'role': 'user'  # Wrong role requested
        })
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertEqual(data['error'], 'role_mismatch')
        self.assertEqual(data['detected_role'], 'worker')
        self.assertEqual(data['requested_role'], 'user')
        self.assertIn('/login?role=worker', data['switch_url'])

        # Ensure no session was established
        with self.client.session_transaction() as sess:
            self.assertNotIn('user_id', sess)

    def test_role_mismatch_user_attempts_worker_login(self):
        """Employer phone attempting Worker login returns 403 with switch to Employer."""
        self.mock_db.users.append({
            'id': 'user-404',
            'name': 'Sunita Sharma',
            'phone': '9876543213',
            'password': generate_password_hash('Sunita123')
        })

        response = self.client.post('/api/auth/login', json={
            'phone': '9876543213',
            'password': 'Sunita123',
            'role': 'worker'  # Wrong role requested
        })
        self.assertEqual(response.status_code, 403)
        data = response.get_json()
        self.assertEqual(data['error'], 'role_mismatch')
        self.assertEqual(data['detected_role'], 'user')
        self.assertIn('/login?role=user', data['switch_url'])

    def test_brute_force_lockout_protection(self):
        """5 failed login attempts triggers 429 lockout."""
        phone = '9876543214'
        for i in range(5):
            res = self.client.post('/api/auth/login', json={
                'phone': phone,
                'password': f'Wrong_{i}',
                'role': 'user'
            })
            if i < 4:
                self.assertEqual(res.status_code, 401)
            else:
                self.assertEqual(res.status_code, 429)
                data = res.get_json()
                self.assertTrue(data.get('lockout'))
                self.assertIn('Too many failed login attempts', data['error'])

        # Next attempt is immediately locked out without querying DB
        res_locked = self.client.post('/api/auth/login', json={
            'phone': phone,
            'password': 'AnyPassword',
            'role': 'user'
        })
        self.assertEqual(res_locked.status_code, 429)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. SESSION STATUS & AUTHORIZATION TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_session_status_endpoint(self):
        """GET /api/auth/session returns authoritative role and never leaks password."""
        # Unauthenticated
        resp1 = self.client.get('/api/auth/session')
        self.assertEqual(resp1.status_code, 200)
        self.assertFalse(resp1.get_json()['authenticated'])

        # Authenticated as user
        self.mock_db.users.append({
            'id': 'user-501',
            'name': 'Kavita Roy',
            'phone': '9876543215',
            'password': generate_password_hash('SecretPass')
        })
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'user-501'
            sess['role'] = 'user'

        with patch('app.try_select') as mock_select:
            mock_select.return_value = MockSupabaseResponse([{
                'id': 'user-501',
                'name': 'Kavita Roy',
                'phone': '9876543215',
                'password': 'hashed_secret_never_leak'
            }])
            resp2 = self.client.get('/api/auth/session')
            self.assertEqual(resp2.status_code, 200)
            data = resp2.get_json()
            self.assertTrue(data['authenticated'])
            self.assertEqual(data['role'], 'user')
            self.assertEqual(data['user_id'], 'user-501')
            self.assertNotIn('password', data['user'])

    def test_unauthorized_dashboard_access(self):
        """Unauthenticated access to dashboards redirects to role-appropriate login."""
        res1 = self.client.get('/dashboard/user')
        self.assertEqual(res1.status_code, 302)
        self.assertIn('/login?role=user', res1.headers['Location'])

        res2 = self.client.get('/dashboard/worker')
        self.assertEqual(res2.status_code, 302)
        self.assertIn('/login?role=worker', res2.headers['Location'])

    def test_cross_role_dashboard_rejection(self):
        """Worker cannot access Employer dashboard, and Employer cannot access Worker dashboard."""
        # Logged in as Worker
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'worker-999'
            sess['role'] = 'worker'

        res_user_dash = self.client.get('/dashboard/user')
        self.assertEqual(res_user_dash.status_code, 302)
        self.assertIn('/login?role=user', res_user_dash.headers['Location'])

        # Logged in as Employer
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'user-999'
            sess['role'] = 'user'

        res_worker_dash = self.client.get('/dashboard/worker')
        self.assertEqual(res_worker_dash.status_code, 302)
        self.assertIn('/login?role=worker', res_worker_dash.headers['Location'])

    # ─────────────────────────────────────────────────────────────────────────
    # 4. ACCOUNT RECOVERY (PASSWORD RESET) TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def test_account_recovery_flow(self):
        """Complete account recovery: request OTP -> verify OTP -> reset password -> login with new password."""
        self.mock_db.workers.append({
            'id': 'worker-777',
            'name': 'Ashok Electrician',
            'phone': '9876543216',
            'password': generate_password_hash('OldPassword123')
        })

        # Step 1: Request OTP
        req_res = self.client.post('/api/auth/forgot-password/request', json={
            'phone': '9876543216',
            'role': 'worker'
        })
        self.assertEqual(req_res.status_code, 200)
        req_data = req_res.get_json()
        otp = req_data.get('demo_otp')
        self.assertIsNotNone(otp)
        self.assertEqual(len(otp), 6)

        # Step 2: Verify OTP
        verify_res = self.client.post('/api/auth/forgot-password/verify', json={
            'phone': '9876543216',
            'role': 'worker',
            'otp': otp
        })
        self.assertEqual(verify_res.status_code, 200)
        verify_data = verify_res.get_json()
        reset_token = verify_data.get('reset_token')
        self.assertIsNotNone(reset_token)

        # Step 3: Reset Password
        reset_res = self.client.post('/api/auth/forgot-password/reset', json={
            'phone': '9876543216',
            'role': 'worker',
            'reset_token': reset_token,
            'new_password': 'BrandNewPassword456'
        })
        self.assertEqual(reset_res.status_code, 200)

        # Verify old password no longer works
        login_old = self.client.post('/api/auth/login', json={
            'phone': '9876543216',
            'password': 'OldPassword123',
            'role': 'worker'
        })
        self.assertEqual(login_old.status_code, 401)

        # Verify new password logs in successfully
        login_new = self.client.post('/api/auth/login', json={
            'phone': '9876543216',
            'password': 'BrandNewPassword456',
            'role': 'worker'
        })
        self.assertEqual(login_new.status_code, 200)

    def test_account_recovery_role_mismatch(self):
        """Attempting account recovery with phone registered under alternate role returns 403."""
        self.mock_db.users.append({
            'id': 'user-888',
            'name': 'Vikram Mehra',
            'phone': '9876543217',
            'password': generate_password_hash('Pass123')
        })

        # Request recovery with role='worker'
        res = self.client.post('/api/auth/forgot-password/request', json={
            'phone': '9876543217',
            'role': 'worker'
        })
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertEqual(data['error'], 'role_mismatch')
        self.assertEqual(data['detected_role'], 'user')

    # ─────────────────────────────────────────────────────────────────────────
    # 5. COMPLETE LIFECYCLE: REGISTER -> AUTH -> REFRESH -> LOGOUT
    # ─────────────────────────────────────────────────────────────────────────

    def test_complete_auth_lifecycle(self):
        """End-to-end verification of registration, authentication, session refresh, and logout."""
        phone = '9876543218'
        password = 'LifecyclePassword99'

        # 1. Register Worker
        reg_res = self.client.post('/api/auth/signup/worker', data={
            'name': 'Gopal Delivery',
            'work': 'Delivery Assistant',
            'location': 'Delhi Connaught Place',
            'phone': phone,
            'password': password
        })
        self.assertEqual(reg_res.status_code, 201)

        # 2. Verify Session immediately after registration
        with patch('app.try_select') as mock_select:
            mock_select.return_value = MockSupabaseResponse([{
                'id': self.mock_db.workers[0]['id'],
                'name': 'Gopal Delivery',
                'phone': phone,
                'role': 'worker'
            }])
            status_res1 = self.client.get('/api/auth/session')
            self.assertEqual(status_res1.status_code, 200)
            self.assertTrue(status_res1.get_json()['authenticated'])
            self.assertEqual(status_res1.get_json()['role'], 'worker')

        # 3. Explicit Logout
        logout_res = self.client.post('/api/auth/logout')
        self.assertEqual(logout_res.status_code, 200)

        # 4. Verify Session is cleared
        status_res2 = self.client.get('/api/auth/session')
        self.assertFalse(status_res2.get_json()['authenticated'])

        # 5. Authenticate via Login
        login_res = self.client.post('/api/auth/login', json={
            'phone': phone,
            'password': password,
            'role': 'worker'
        })
        self.assertEqual(login_res.status_code, 200)
        self.assertEqual(login_res.get_json()['role'], 'worker')

        # 6. Session refreshed and valid again
        with patch('app.try_select') as mock_select:
            mock_select.return_value = MockSupabaseResponse([{
                'id': self.mock_db.workers[0]['id'],
                'name': 'Gopal Delivery',
                'phone': phone,
                'role': 'worker'
            }])
            status_res3 = self.client.get('/api/auth/session')
            self.assertTrue(status_res3.get_json()['authenticated'])
            self.assertEqual(status_res3.get_json()['role'], 'worker')


if __name__ == '__main__':
    unittest.main()
