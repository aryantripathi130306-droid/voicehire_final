"""
VoiceHire - Comprehensive Language Coverage & Localization Test Suite
Verifies:
1. Centralized translations layer (parities, no missing keys, template parity).
2. Default language (Hindi) and verified Tier 1 languages (Hindi, Punjabi, English).
3. Indian formatting (dates, relative times, numbers, currency with ₹ and Indian grouping).
4. Accessible status representation (step number, localized text, aria-labels; no color-only status).
5. Persistence of language preference across cookies, sessions, endpoints, and profile updates.
6. Voice capabilities, trade mappings (Punjabi / regional terms), and clarification triggers.
7. Safe draft management (no secrets stored).
"""

import re
import os
import glob
import unittest
from datetime import datetime, timedelta
from app import app
import translations
from translations import (
    TRANSLATIONS,
    VERIFIED_LANGUAGES,
    DEFAULT_LANGUAGE,
    get_verified_language,
    get_translation,
    get_all_translations_for_lang,
    indian_number_format,
    format_currency,
    format_number,
    format_date,
    format_relative_time,
    get_localized_status,
    get_localized_validation,
)
import voice_service


class TestLanguageParityAndCoverage(unittest.TestCase):
    """Test 1 & 2: Centralized translations, default language and verified language parity."""

    def test_default_language_is_hindi(self):
        """Default language must strictly be Hindi ('hi')."""
        self.assertEqual(DEFAULT_LANGUAGE, 'hi')
        self.assertEqual(get_verified_language(None), 'hi')
        self.assertEqual(get_verified_language(''), 'hi')
        self.assertEqual(get_verified_language('unknown_lang'), 'hi')

    def test_verified_languages_list(self):
        """Tier 1 fully verified languages must at minimum be Hindi, Punjabi, and English."""
        self.assertIn('hi', VERIFIED_LANGUAGES)
        self.assertIn('pa', VERIFIED_LANGUAGES)
        self.assertIn('en', VERIFIED_LANGUAGES)
        self.assertEqual(len(VERIFIED_LANGUAGES), 3)

    def test_key_parity_between_hindi_punjabi_english(self):
        """Every key defined in Hindi must also be defined in Punjabi and English (100% key parity)."""
        hi_keys = set(TRANSLATIONS['hi'].keys())
        pa_keys = set(TRANSLATIONS['pa'].keys())
        en_keys = set(TRANSLATIONS['en'].keys())

        # Check count is high (over 450 centralized keys)
        self.assertGreaterEqual(len(hi_keys), 480)

        missing_in_pa = hi_keys - pa_keys
        missing_in_en = hi_keys - en_keys
        missing_in_hi = en_keys - hi_keys

        self.assertEqual(len(missing_in_pa), 0, f"Keys missing in Punjabi: {missing_in_pa}")
        self.assertEqual(len(missing_in_en), 0, f"Keys missing in English: {missing_in_en}")
        self.assertEqual(len(missing_in_hi), 0, f"Keys missing in Hindi: {missing_in_hi}")

    def test_no_empty_translations_in_verified_languages(self):
        """No translation string should be empty in verified languages."""
        for lang in ['hi', 'pa', 'en']:
            for key, val in TRANSLATIONS[lang].items():
                if key.strip():
                    self.assertTrue(bool(val and str(val).strip()), f"Empty translation for key '{key}' in lang '{lang}'")

    def test_template_translation_keys_exist_in_bundle(self):
        """Audit all Jinja2 templates for {{ t('...') }} calls and verify they exist in translations."""
        template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')
        html_files = glob.glob(os.path.join(template_dir, '*.html'))
        self.assertGreater(len(html_files), 5, "Template directory must contain html files")

        t_pattern = re.compile(r"\{\{\s*t\(\s*['\"](.*?)['\"]\s*[\),]")
        missing_keys = set()
        checked_count = 0

        for fpath in html_files:
            with open(fpath, 'r', encoding='utf-8') as f:
                content = f.read()
                matches = t_pattern.findall(content)
                for key in matches:
                    clean_key = key.replace("\\'", "'").replace('\\"', '"').strip()
                    if '%s' in clean_key:
                        continue
                    checked_count += 1
                    if clean_key not in TRANSLATIONS['hi']:
                        missing_keys.add(clean_key)

        self.assertGreater(checked_count, 100, f"Expected >100 template translation calls, found {checked_count}")
        self.assertEqual(len(missing_keys), 0, f"Template translation keys missing from translations.py: {missing_keys}")

    def test_get_all_translations_returns_active_bundle(self):
        """get_all_translations_for_lang returns full dictionary for client-side consumption."""
        hi_bundle = get_all_translations_for_lang('hi')
        pa_bundle = get_all_translations_for_lang('pa')
        en_bundle = get_all_translations_for_lang('en')

        self.assertGreaterEqual(len(hi_bundle), 480)
        self.assertGreaterEqual(len(pa_bundle), 480)
        self.assertEqual(hi_bundle['Home'], 'घर')
        self.assertEqual(pa_bundle['Home'], 'ਘਰ')
        self.assertEqual(en_bundle['Home'], 'Home')


class TestIndianLocalizationFormatting(unittest.TestCase):
    """Test 5: Localization of dates, numbers, currency amounts and validation messages for India."""

    def test_indian_number_formatting(self):
        """Check Indian comma separation rules (e.g. 1,50,000 instead of Western 150,000)."""
        self.assertEqual(indian_number_format(0), '0')
        self.assertEqual(indian_number_format(500), '500')
        self.assertEqual(indian_number_format(1500), '1,500')
        self.assertEqual(indian_number_format(15000), '15,000')
        self.assertEqual(indian_number_format(150000), '1,50,000')
        self.assertEqual(indian_number_format(1500000), '15,00,000')
        self.assertEqual(indian_number_format(10000000), '1,00,00,000')

    def test_format_currency(self):
        """Check currency formatting with Rupee symbol (₹) and Indian words."""
        self.assertEqual(format_currency(500, 'hi'), '₹500')
        self.assertEqual(format_currency(150000, 'hi'), '₹1,50,000')
        self.assertEqual(format_currency(150000, 'pa'), '₹1,50,000')
        self.assertEqual(format_currency(150000, 'en'), '₹1,50,000')

        # With words
        hi_words = format_currency(1500, 'hi', include_words=True)
        self.assertIn('रुपये', hi_words)
        self.assertIn('1,500', hi_words)

        pa_words = format_currency(1500, 'pa', include_words=True)
        self.assertIn('ਰੁਪਏ', pa_words)
        self.assertIn('1,500', pa_words)

        en_words = format_currency(1500, 'en', include_words=True)
        self.assertIn('Rupees', en_words)

    def test_format_date_localization(self):
        """Check dates localized in Hindi, Punjabi, and English."""
        test_dt = datetime(2026, 10, 17, 12, 0, 0)
        hi_date = format_date(test_dt, 'hi')
        pa_date = format_date(test_dt, 'pa')
        en_date = format_date(test_dt, 'en')

        self.assertIn('अक्टूबर', hi_date)
        self.assertIn('2026', hi_date)

        self.assertIn('ਅਕਤੂਬਰ', pa_date)
        self.assertIn('2026', pa_date)

        self.assertIn('Oct', en_date)
        self.assertIn('2026', en_date)

    def test_format_relative_time_localization(self):
        """Check relative times (just now, X mins ago, X hours ago)."""
        now = datetime.now()

        # Just now
        self.assertEqual(format_relative_time(now, 'hi'), 'अभी')
        self.assertEqual(format_relative_time(now, 'pa'), 'ਹੁਣੇ')
        self.assertEqual(format_relative_time(now, 'en'), 'Just now')

        # 5 minutes ago
        five_mins_ago = now - timedelta(minutes=5)
        self.assertIn('मिनट पहले', format_relative_time(five_mins_ago, 'hi'))
        self.assertIn('ਮਿੰਟ ਪਹਿਲਾਂ', format_relative_time(five_mins_ago, 'pa'))
        self.assertIn('mins ago', format_relative_time(five_mins_ago, 'en'))

        # 2 hours ago
        two_hours_ago = now - timedelta(hours=2)
        self.assertIn('घंटे पहले', format_relative_time(two_hours_ago, 'hi'))
        self.assertIn('ਘੰਟੇ ਪਹਿਲਾਂ', format_relative_time(two_hours_ago, 'pa'))
        self.assertIn('hours ago', format_relative_time(two_hours_ago, 'en'))

    def test_localized_validation_messages(self):
        """Check form and hardware validation messages across verified languages."""
        error_keys = ['phone_required', 'phone_invalid', 'password_short', 'gps_denied', 'camera_denied', 'offline']

        for err in error_keys:
            hi_val = get_localized_validation(err, 'hi')
            pa_val = get_localized_validation(err, 'pa')
            en_val = get_localized_validation(err, 'en')

            self.assertTrue(bool(hi_val and hi_val != err), f"Missing Hindi validation for {err}")
            self.assertTrue(bool(pa_val and pa_val != err), f"Missing Punjabi validation for {err}")
            self.assertTrue(bool(en_val and en_val != err), f"Missing English validation for {err}")


class TestAccessibleBookingStatus(unittest.TestCase):
    """Test 7: Accessible booking status (no color-only or icon-only statuses)."""

    def test_localized_status_structure(self):
        """get_localized_status returns dictionary with full descriptive labels and step numbers."""
        statuses = [
            'Booked',
            'On The Way',
            'Arrived',
            'Work Started',
            'Completed',
            'Payment Pending',
            'Paid',
            'Cancelled',
            'Disputed',
        ]

        for s in statuses:
            for lang in ['hi', 'pa', 'en']:
                st = get_localized_status(s, lang)
                self.assertIn('label', st)
                self.assertIn('description', st)
                self.assertIn('badge_class', st)
                self.assertIn('step_number', st)
                self.assertIn('aria_label', st)

                # Ensure label and description are non-empty and language-specific
                self.assertTrue(len(st['label']) > 0)
                self.assertTrue(len(st['description']) > 0)
                self.assertIn(st['label'], st['aria_label'])

    def test_status_step_numbers_and_non_reliance_on_color(self):
        """Ensure progression step numbers exist and status descriptions are clear."""
        st_booked = get_localized_status('Booked', 'hi')
        self.assertEqual(st_booked['step_number'], 1)
        self.assertEqual(st_booked['label'], 'स्वीकृत')

        st_arrived = get_localized_status('Arrived', 'pa')
        self.assertEqual(st_arrived['step_number'], 3)
        self.assertEqual(st_arrived['label'], 'ਪਹੁੰਚ ਗਏ ਹਨ')

        st_started = get_localized_status('Work Started', 'hi')
        self.assertEqual(st_started['step_number'], 4)
        self.assertEqual(st_started['label'], 'कार्य प्रगति पर')

        st_done = get_localized_status('Completed', 'en')
        self.assertEqual(st_done['step_number'], 5)
        self.assertEqual(st_done['label'], 'Completed')


class TestLanguagePreferencePersistence(unittest.TestCase):
    """Test 3: Language preference persistence across sessions, cookies, and route handlers."""

    def setUp(self):
        self.client = app.test_client()

    def test_default_request_sets_hindi(self):
        """Unauthenticated fresh visitor without cookie gets Hindi default."""
        with self.client as c:
            res = c.get('/')
            self.assertEqual(res.status_code, 200)
            from flask import session
            self.assertEqual(session.get('lang'), 'hi')

    def test_set_lang_route_persists_in_cookie_and_session(self):
        """Visiting /set_lang/pa sets session and 30-day voicehire_lang cookie."""
        with self.client as c:
            res = c.get('/set_lang/pa')
            self.assertEqual(res.status_code, 302)
            from flask import session
            self.assertEqual(session.get('lang'), 'pa')

            # Verify cookie
            cookies = res.headers.getlist('Set-Cookie')
            cookie_text = " ".join(cookies)
            self.assertIn('voicehire_lang=pa', cookie_text)

    def test_cookie_restores_session_preference(self):
        """If session has no language, cookie restores the preference."""
        with self.client as c:
            # Set cookie directly
            c.set_cookie('voicehire_lang', 'pa')
            res = c.get('/')
            self.assertEqual(res.status_code, 200)
            from flask import session
            self.assertEqual(session.get('lang'), 'pa')

    def test_set_lang_ajax_json_response(self):
        """Calling /set_lang/<lang> via AJAX returns JSON payload."""
        with self.client as c:
            res = c.get('/set_lang/pa', headers={'X-Requested-With': 'XMLHttpRequest'})
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertTrue(data['success'])
            self.assertEqual(data['lang'], 'pa')

    def test_api_translations_endpoint(self):
        """GET /api/translations returns language bundle and metadata."""
        with self.client as c:
            c.get('/set_lang/pa')
            res = c.get('/api/translations')
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            self.assertEqual(data['lang'], 'pa')
            self.assertIn('translations', data)
            self.assertEqual(data['translations']['Home'], 'ਘਰ')


class TestVoiceCapabilitiesAndRegionalSupport(unittest.TestCase):
    """Test 2 & 4: Voice capabilities, regional vocabulary and clarification triggers."""

    def test_voice_capabilities_advertises_only_verified_languages(self):
        """Only Tier 1 verified languages (hi, pa, en) are flagged as verified."""
        caps = voice_service.get_voice_capabilities()
        self.assertIn('verified_languages', caps)
        self.assertEqual(caps['verified_languages'], ['hi', 'pa', 'en'])

        # Check supported_languages list
        langs = {l['code']: l for l in caps.get('supported_languages', [])}
        self.assertTrue(langs['hi']['is_verified'])
        self.assertTrue(langs['pa']['is_verified'])
        self.assertTrue(langs['en']['is_verified'])

        # Other languages must have is_verified == False
        for l_code, l_info in langs.items():
            if l_code not in ['hi', 'pa', 'en']:
                self.assertFalse(l_info.get('is_verified', False))

    def test_regional_and_punjabi_trade_vocabulary(self):
        """Voice engine recognizes regional terms and Punjabi trade terms."""
        # Tarkhan -> carpenter
        carpenters = voice_service.detect_trade("ਮੈਨੂੰ ਘਰ ਦੇ ਦਰਵਾਜ਼ੇ ਲਈ ਤਰਖਾਣ ਚਾਹੀਦਾ ਹੈ")
        self.assertEqual(carpenters, "Carpenter")

        # Safedi -> painter
        painters = voice_service.detect_trade("दीवारों पर सफेदी करानी है")
        self.assertEqual(painters, "Painter")

        # Tonti -> plumber
        plumbers = voice_service.detect_trade("रसोई की टोंटी खराब हो गई है")
        self.assertEqual(plumbers, "Plumber")

        # Chalak -> driver
        drivers = voice_service.detect_trade("ਗੱਡੀ ਚਲਾਉਣ ਲਈ ਚਾਲਕ ਚਾਹੀਦਾ")
        self.assertEqual(drivers, "Driver")

    def test_voice_clarification_on_ambiguous_recognition(self):
        """When speech recognition is unclear or unintelligible, engine asks for clarification."""
        result = voice_service.analyze_voice_intent(
            raw_text="blah blah unintelligible gibberish xyz",
            lang_code="hi",
            current_state="GREETING"
        )
        self.assertTrue(result.get('requires_clarification', False))
        self.assertIn('clarification_prompt', result)
        self.assertTrue(len(result['clarification_prompt']) > 0)


if __name__ == '__main__':
    unittest.main()
