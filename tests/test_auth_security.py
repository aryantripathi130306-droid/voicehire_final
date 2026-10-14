"""
Tests for VoiceHire Auth Security & Account Recovery Engine
"""

import time
import unittest
from auth_security import BruteForceShield, AccountRecoveryManager


class TestBruteForceShield(unittest.TestCase):
    def setUp(self):
        self.shield = BruteForceShield(max_attempts=3, window_seconds=2, lockout_seconds=2)

    def test_record_failures_and_lockout(self):
        key = "9876543210"
        locked, _ = self.shield.record_failure(key)
        self.assertFalse(locked)

        locked, _ = self.shield.record_failure(key)
        self.assertFalse(locked)

        # 3rd failure triggers lockout
        locked, rem = self.shield.record_failure(key)
        self.assertTrue(locked)
        self.assertGreater(rem, 0)

        # Still locked
        is_l, _ = self.shield.is_locked(key)
        self.assertTrue(is_l)

    def test_record_success_clears_failures(self):
        key = "9876543211"
        self.shield.record_failure(key)
        self.shield.record_failure(key)
        self.shield.record_success(key)

        is_l, _ = self.shield.is_locked(key)
        self.assertFalse(is_l)
        # Should need 3 fresh failures to lock
        self.shield.record_failure(key)
        is_l, _ = self.shield.is_locked(key)
        self.assertFalse(is_l)

    def test_lockout_expires(self):
        key = "9876543212"
        self.shield.record_failure(key)
        self.shield.record_failure(key)
        self.shield.record_failure(key)
        is_l, _ = self.shield.is_locked(key)
        self.assertTrue(is_l)

        # Sleep past lockout
        time.sleep(2.1)
        is_l, _ = self.shield.is_locked(key)
        self.assertFalse(is_l)


class TestAccountRecoveryManager(unittest.TestCase):
    def setUp(self):
        self.manager = AccountRecoveryManager(otp_validity_seconds=2, token_validity_seconds=2, max_otp_attempts=2)

    def test_otp_generation_and_verification(self):
        phone = "9876543210"
        role = "worker"
        otp = self.manager.create_recovery_request(phone, role)
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

        # Verify correct OTP
        success, reason, token = self.manager.verify_otp(phone, role, otp)
        self.assertTrue(success)
        self.assertEqual(reason, "verified")
        self.assertIsNotNone(token)

        # Verify and consume reset token
        valid = self.manager.verify_and_consume_reset_token(phone, role, token)
        self.assertTrue(valid)

        # Token is single use, cannot be consumed twice
        valid2 = self.manager.verify_and_consume_reset_token(phone, role, token)
        self.assertFalse(valid2)

    def test_invalid_otp_attempts_limit(self):
        phone = "9876543211"
        role = "user"
        otp = self.manager.create_recovery_request(phone, role)

        # Attempt 1: wrong OTP
        success, reason, _ = self.manager.verify_otp(phone, role, "000000")
        self.assertFalse(success)
        self.assertEqual(reason, "invalid")

        # Attempt 2: wrong OTP (hits max 2 attempts)
        success, reason, _ = self.manager.verify_otp(phone, role, "111111")
        self.assertFalse(success)
        self.assertEqual(reason, "too_many_attempts")

        # Subsequent attempt with even correct OTP is rejected
        success, reason, _ = self.manager.verify_otp(phone, role, otp)
        self.assertFalse(success)
        self.assertEqual(reason, "no_request_found")

    def test_otp_expiration(self):
        phone = "9876543212"
        role = "worker"
        otp = self.manager.create_recovery_request(phone, role)
        time.sleep(2.1)

        success, reason, _ = self.manager.verify_otp(phone, role, otp)
        self.assertFalse(success)
        self.assertEqual(reason, "expired")


if __name__ == '__main__':
    unittest.main()
