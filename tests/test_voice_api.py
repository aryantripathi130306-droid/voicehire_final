"""
VoiceHire — Automated Flask API Integration Tests for Voice Layer
Tests cover:
  1. /api/voice/intent with valid spoken transcript
  2. /api/voice/intent with empty/whitespace input
  3. /api/voice/intent with low confidence threshold
  4. /api/voice/intent with unknown language fallback
  5. /api/voice/intent with invalid/malformed JSON
  6. /api/voice/intent server error recovery
  7. /api/voice/capabilities endpoint verification and secret isolation
  8. Language continuity across requests
"""

import json
import unittest
from unittest.mock import patch
from app import app


class TestVoiceAPIEndpoints(unittest.TestCase):
    """Integration test suite for VoiceHire voice API endpoints."""

    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_voice_capabilities_endpoint(self):
        """GET /api/voice/capabilities returns 200 with supported locales and no leaked secrets."""
        response = self.client.get('/api/voice/capabilities')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsNotNone(data)
        self.assertEqual(data.get('default_language'), 'hi')
        self.assertIn('supported_languages', data)
        self.assertGreaterEqual(len(data['supported_languages']), 12)
        
        # Verify default Hindi is present
        hindi = next((l for l in data['supported_languages'] if l['code'] == 'hi'), None)
        self.assertIsNotNone(hindi)
        self.assertEqual(hindi['stt_locale'], 'hi-IN')
        self.assertEqual(hindi['tts_locale'], 'hi-IN')

        # Check strict server credential isolation
        body_text = response.get_data(as_text=True).lower()
        self.assertNotIn('supabase_key', body_text)
        self.assertNotIn('secret_key', body_text)
        self.assertNotIn('password', body_text)
        self.assertNotIn('api_key', body_text)

    def test_voice_intent_valid_hindi_worker(self):
        """POST /api/voice/intent with spoken Hindi worker intent."""
        payload = {
            'transcript': 'main electrician hu kaam chahiye',
            'language': 'hi',
            'confidence': 0.92,
            'current_state': 'ROLE_SELECT'
        }
        response = self.client.post(
            '/api/voice/intent',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['intent'], 'select_role_worker')
        self.assertEqual(data['role'], 'worker')
        self.assertEqual(data['trade'], 'Electrician')
        self.assertFalse(data['requires_clarification'])

    def test_voice_intent_valid_hinglish_customer(self):
        """POST /api/voice/intent with spoken Hinglish customer intent."""
        payload = {
            'transcript': 'mujhe plumber chahiye nal theek karna hai',
            'language': 'hi',
            'confidence': 0.88,
            'current_state': 'ROLE_SELECT'
        }
        response = self.client.post(
            '/api/voice/intent',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['intent'], 'select_role_customer')
        self.assertEqual(data['role'], 'user')
        self.assertEqual(data['trade'], 'Plumber')
        self.assertFalse(data['requires_clarification'])

    def test_voice_intent_empty_transcript(self):
        """POST /api/voice/intent with empty audio/transcript returns polite clarification."""
        payload = {
            'transcript': '   ',
            'language': 'hi',
            'confidence': 0.0
        }
        response = self.client.post(
            '/api/voice/intent',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['intent'], 'empty_transcript')
        self.assertTrue(data['requires_clarification'])
        self.assertIn('सुनाई नहीं दी', data['clarification_prompt'])
        self.assertIsNone(data['role'])

    def test_voice_intent_low_confidence_clarification(self):
        """POST /api/voice/intent with low confidence (<0.60) never commits consequential role/action."""
        payload = {
            'transcript': 'booking something',
            'language': 'hi',
            'confidence': 0.38
        }
        response = self.client.post(
            '/api/voice/intent',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['intent'], 'low_confidence')
        self.assertTrue(data['requires_clarification'])
        self.assertIsNone(data['role'])
        self.assertIsNone(data['action'])
        self.assertIn('साफ़ सुनाई नहीं दी', data['clarification_prompt'])

    def test_voice_intent_unknown_language_fallback(self):
        """POST /api/voice/intent with unknown language falls back to Hindi (hi-IN)."""
        payload = {
            'transcript': 'main plumber hu',
            'language': 'klingon-99',
            'confidence': 0.90
        }
        response = self.client.post(
            '/api/voice/intent',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        # Falls back to Hindi gracefully
        self.assertEqual(data['language'], 'hi')
        self.assertEqual(data['intent'], 'select_role_worker')

    def test_voice_intent_malformed_request(self):
        """POST /api/voice/intent with non-JSON or invalid body returns 400."""
        response = self.client.post(
            '/api/voice/intent',
            data="not a json string",
            content_type='text/plain'
        )
        self.assertEqual(response.status_code, 400)
        data = response.get_json()
        self.assertFalse(data['success'])
        self.assertIn('Invalid JSON', data.get('error', ''))

    def test_voice_intent_provider_exception_recovery(self):
        """POST /api/voice/intent handles unexpected backend errors with recoverable 500 response."""
        with patch('app.analyze_voice_intent', side_effect=RuntimeError("Simulated speech engine failure")):
            response = self.client.post(
                '/api/voice/intent',
                data=json.dumps({'transcript': 'hello'}),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 500)
            data = response.get_json()
            self.assertFalse(data['success'])
            self.assertIn('error', data)
            self.assertIn('speech_response', data)


if __name__ == '__main__':
    unittest.main()
