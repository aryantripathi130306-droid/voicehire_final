"""
VoiceHire — Automated Test Suite for Voice Service Layer
Tests cover:
  1. Unknown language graceful fallback to Hindi (hi-IN)
  2. Empty / whitespace-only transcript handling
  3. Low-confidence transcript (< 0.60 threshold) clarification triggering
  4. Ambiguous input clarification without state advancement
  5. Hinglish and regional code-switching recognition (Hindi, Punjabi, Bengali, Tamil, etc.)
  6. Cancellation and retry voice intents
  7. Language switching intents
  8. Role and trade extraction from natural colloquial speech
  9. Action selection (login vs register)
  10. Server capabilities metadata and credential isolation
"""

import unittest
from voice_service import (
    analyze_voice_intent,
    get_voice_capabilities,
    get_clarification_message,
    detect_trade,
    get_verified_language,
    LANGUAGE_REGISTRY,
    DEFAULT_LANGUAGE
)


class TestVoiceServiceLocaleAndRegistry(unittest.TestCase):
    """Tests for language registry integrity, locale mappings, and fallbacks."""

    def test_default_language_is_hindi(self):
        """Requirement: Default language must be Hindi (hi-IN)."""
        self.assertEqual(DEFAULT_LANGUAGE, 'hi')
        self.assertIn('hi', LANGUAGE_REGISTRY)
        self.assertEqual(LANGUAGE_REGISTRY['hi']['stt_locale'], 'hi-IN')
        self.assertEqual(LANGUAGE_REGISTRY['hi']['tts_locale'], 'hi-IN')

    def test_unknown_language_fallback(self):
        """Requirement: Unknown or unsupported languages must safely fallback to Hindi (hi-IN)."""
        self.assertEqual(get_verified_language('xx-XX'), 'hi')
        self.assertEqual(get_verified_language('invalid_lang'), 'hi')
        self.assertEqual(get_verified_language(None), 'hi')
        self.assertEqual(get_verified_language(''), 'hi')
        self.assertEqual(get_verified_language(123), 'hi')

    def test_supported_locales_registered(self):
        """Requirement: Verified locale mappings for all advertised languages."""
        required_languages = ['hi', 'pa', 'en', 'bn', 'mr', 'ta', 'te', 'gu', 'kn', 'ml', 'or', 'ur']
        for lang_code in required_languages:
            self.assertIn(lang_code, LANGUAGE_REGISTRY, f"Language {lang_code} missing from registry")
            meta = LANGUAGE_REGISTRY[lang_code]
            self.assertIn('stt_locale', meta)
            self.assertIn('tts_locale', meta)
            self.assertTrue(meta['stt_locale'].endswith('-IN'), f"Locale for {lang_code} should be Indian regional")
            self.assertIn('code_switching', meta)
            self.assertGreater(meta['confidence_threshold'], 0.0)

    def test_capabilities_exposure_no_secrets(self):
        """Requirement: Use server-side credentials; never leak API keys to frontend."""
        caps = get_voice_capabilities()
        self.assertEqual(caps['default_language'], 'hi')
        self.assertIn('supported_languages', caps)
        self.assertIn('features', caps)
        self.assertTrue(caps['provider_status']['server_credentials_secured'])
        
        # Verify no secret tokens exist in capabilities
        caps_str = str(caps).lower()
        self.assertNotIn('secret', caps_str)
        self.assertNotIn('api_key', caps_str)
        self.assertNotIn('password', caps_str)
        self.assertNotIn('bearer', caps_str)


class TestVoiceServiceEmptyAndLowConfidence(unittest.TestCase):
    """Tests for empty input, low confidence, and clarification dialogs."""

    def test_empty_transcript(self):
        """Requirement: Empty transcript returns empty_transcript intent with localized prompt."""
        for empty_val in ["", "   ", "\t\n", None]:
            result = analyze_voice_intent(empty_val, language_code='hi')
            self.assertFalse(result['success'])
            self.assertEqual(result['intent'], 'empty_transcript')
            self.assertTrue(result['requires_clarification'])
            self.assertIn('सुनाई नहीं दी', result['clarification_prompt'])
            self.assertIsNone(result['role'])
            self.assertIsNone(result['action'])

    def test_empty_transcript_localized_punjabi(self):
        """Empty transcript in Punjabi returns Punjabi clarification."""
        result = analyze_voice_intent("", language_code='pa')
        self.assertFalse(result['success'])
        self.assertEqual(result['intent'], 'empty_transcript')
        self.assertIn('ਨਹੀਂ ਸੁਣੀ', result['clarification_prompt'])

    def test_low_confidence_input_triggers_clarification(self):
        """Requirement: Low-confidence recognition (<0.60) must ask a short clarification question.
        Must never create booking or advance state on uncertain interpretation.
        """
        # Confidence explicitly provided below threshold
        result = analyze_voice_intent(
            "main plumber hu",
            language_code='hi',
            confidence=0.45
        )
        self.assertFalse(result['success'])
        self.assertEqual(result['intent'], 'low_confidence')
        self.assertTrue(result['requires_clarification'])
        self.assertIn('साफ़ सुनाई नहीं दी', result['clarification_prompt'])
        # Crucial security & UX rule: role and action must remain uncommitted!
        self.assertIsNone(result['role'])
        self.assertIsNone(result['action'])

    def test_ambiguous_transcript_triggers_clarification(self):
        """Ambiguous/casual phrases (e.g., 'theek hai', 'haan') ask clarification instead of guessing."""
        result = analyze_voice_intent("theek hai haan", language_code='hi', current_state='ROLE_SELECT')
        self.assertFalse(result['success'])
        self.assertEqual(result['intent'], 'clarification_needed')
        self.assertTrue(result['requires_clarification'])
        self.assertIsNone(result['role'])
        self.assertTrue('काम' in result['clarification_prompt'] or 'work' in result['clarification_prompt'].lower())


class TestVoiceServiceHinglishAndConversational(unittest.TestCase):
    """Tests natural conversational speech, ordinary regional accents, and Hinglish."""

    def test_hinglish_customer_intent(self):
        """Hinglish phrase: 'Mujhe ek electrician chahiye' -> Customer role with electrician trade."""
        result = analyze_voice_intent("mujhe ek electrician chahiye", language_code='hi')
        self.assertTrue(result['success'])
        self.assertEqual(result['intent'], 'select_role_customer')
        self.assertEqual(result['role'], 'user')
        self.assertEqual(result['trade'], 'Electrician')
        self.assertFalse(result['requires_clarification'])
        self.assertGreaterEqual(result['confidence'], 0.70)

    def test_hinglish_worker_intent(self):
        """Hinglish phrase: 'Main plumber hu kaam dhundh raha hu' -> Worker role with plumber trade."""
        result = analyze_voice_intent("main plumber hu kaam dhundh raha hu", language_code='hi')
        self.assertTrue(result['success'])
        self.assertEqual(result['intent'], 'select_role_worker')
        self.assertEqual(result['role'], 'worker')
        self.assertEqual(result['trade'], 'Plumber')
        self.assertFalse(result['requires_clarification'])
        self.assertGreaterEqual(result['confidence'], 0.70)

    def test_punjabi_worker_intent(self):
        """Punjabi phrase: 'Mainu kam chahida hai' -> Worker role."""
        result = analyze_voice_intent("mainu kam chahida hai", language_code='pa')
        self.assertTrue(result['success'])
        self.assertEqual(result['intent'], 'select_role_worker')
        self.assertEqual(result['role'], 'worker')

    def test_punjabi_customer_intent(self):
        """Punjabi phrase: 'Bande di lod hai plumber chahida' -> Customer role."""
        result = analyze_voice_intent("bande di lod hai plumber chahida", language_code='pa')
        self.assertTrue(result['success'])
        self.assertEqual(result['intent'], 'select_role_customer')
        self.assertEqual(result['role'], 'user')
        self.assertEqual(result['trade'], 'Plumber')

    def test_bengali_worker_intent(self):
        """Bengali phrase: 'amar kaj lagbe' -> Worker role."""
        result = analyze_voice_intent("amar kaj lagbe", language_code='bn')
        self.assertTrue(result['success'])
        self.assertEqual(result['intent'], 'select_role_worker')
        self.assertEqual(result['role'], 'worker')

    def test_tamil_worker_intent(self):
        """Tamil phrase: 'enakku velai vendum' -> Worker role."""
        result = analyze_voice_intent("enakku velai vendum", language_code='ta')
        self.assertTrue(result['success'])
        self.assertEqual(result['intent'], 'select_role_worker')
        self.assertEqual(result['role'], 'worker')

    def test_trade_extraction_various_accents_and_spellings(self):
        """Trade extraction for common Indian blue-collar trades."""
        trades_to_test = [
            ("mujhe mistri chahiye", "Mason"),
            ("carpenter ka kaam", "Carpenter"),
            ("electrician bulao", "Electrician"),
            ("safai karni hai cleaner", "Cleaner"),
            ("gaadi driver chahiye", "Driver"),
            ("painter dhundho", "Painter"),
            ("plumber chahiye", "Plumber"),
            ("mechanic ki jarurat hai", "Mechanic")
        ]
        for phrase, expected_trade in trades_to_test:
            extracted = detect_trade(phrase)
            self.assertEqual(extracted, expected_trade, f"Failed trade extraction for '{phrase}'")


class TestVoiceServiceActionSelection(unittest.TestCase):
    """Tests action selection: login vs new account (register)."""

    def test_login_intent_hindi_and_hinglish(self):
        """Phrases indicating login."""
        phrases = [
            "login karna hai",
            "pehle se account hai",
            "open my account",
            "login"
        ]
        for phrase in phrases:
            result = analyze_voice_intent(phrase, language_code='hi', current_state='ACTION_SELECT')
            self.assertTrue(result['success'], f"Failed login detection for '{phrase}'")
            self.assertEqual(result['intent'], 'select_action_login')
            self.assertEqual(result['action'], 'login')

    def test_register_intent_hindi_and_hinglish(self):
        """Phrases indicating registration / new account."""
        phrases = [
            "naya account banana hai",
            "signup karna hai",
            "pehli baar aaya hu new registration",
            "register"
        ]
        for phrase in phrases:
            result = analyze_voice_intent(phrase, language_code='hi', current_state='ACTION_SELECT')
            self.assertTrue(result['success'], f"Failed register detection for '{phrase}'")
            self.assertEqual(result['intent'], 'select_action_register')
            self.assertEqual(result['action'], 'register')


class TestVoiceServiceCancellationAndRetry(unittest.TestCase):
    """Tests voice cancellation and retry triggers."""

    def test_cancellation_intents(self):
        """User saying cancel/stop/ruk jao must trigger cancel intent."""
        phrases = [
            "cancel karo",
            "stop listening",
            "ruk jao",
            "chhod do wapas jao",
            "band karo"
        ]
        for phrase in phrases:
            result = analyze_voice_intent(phrase, language_code='hi')
            self.assertTrue(result['success'], f"Failed cancel detection for '{phrase}'")
            self.assertEqual(result['intent'], 'cancel')

    def test_retry_intents(self):
        """User asking to repeat/retry must trigger retry intent."""
        phrases = [
            "phir se bolo",
            "try again",
            "dobara kaho",
            "repeat karo",
            "phir se kaho"
        ]
        for phrase in phrases:
            result = analyze_voice_intent(phrase, language_code='hi')
            self.assertTrue(result['success'], f"Failed retry detection for '{phrase}'")
            self.assertEqual(result['intent'], 'retry')


class TestVoiceServiceLanguageSwitch(unittest.TestCase):
    """Tests spoken language switching commands."""

    def test_switch_to_punjabi(self):
        result = analyze_voice_intent("punjabi me baat karo", language_code='hi')
        self.assertTrue(result['success'])
        self.assertEqual(result['intent'], 'select_language')
        self.assertEqual(result['target_language'], 'pa')

    def test_switch_to_english(self):
        result = analyze_voice_intent("speak in english please", language_code='hi')
        self.assertTrue(result['success'])
        self.assertEqual(result['intent'], 'select_language')
        self.assertEqual(result['target_language'], 'en')

    def test_switch_to_hindi(self):
        result = analyze_voice_intent("hindi me bolo", language_code='en')
        self.assertTrue(result['success'])
        self.assertEqual(result['intent'], 'select_language')
        self.assertEqual(result['target_language'], 'hi')


if __name__ == '__main__':
    unittest.main()
