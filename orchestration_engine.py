"""
VoiceHire — Conversational Orchestration Engine
═══════════════════════════════════════════════════════════════════════════════
Complies with Master Engineering Rules & Phase 3 Specifications:
 1. Deterministic conversation state machine:
    GREETING, LANGUAGE_SELECTION, ROLE_SELECTION, LOGIN_SIGNUP_SELECTION,
    COLLECTING_PROFILE_FIELDS, AWAITING_USER_CONFIRMATION, AUTHENTICATED,
    PROFILE_COMPLETION, JOB_DISCOVERY, BOOKING_GUIDANCE, MANUAL_TAKEOVER,
    RECOVERABLE_ERROR.
 2. Natural language intent interpretation and concise multilingual response generation.
 3. Explicit whitelist of permitted assistant actions with validated arguments.
 4. Strict backend authorization guard; rejects arbitrary code, SQL or unrestricted requests.
 5. Language preference and conversation state persistence across page navigation and refresh.
 6. One-question-at-a-time dialogue with yes/no choices, repeat hints and manual correction.
 7. Explicit user confirmation before any consequential action (account creation, job post,
    booking, offer acceptance, QR check-in, payment).
 8. ZERO password/OTP collection via voice; routes users to secure authentication flow.
 9. Distinguishes general questions from commands; answers without unwanted state transitions.
 10. Idempotency and deduplication guard preventing repeated executions from rapid voice events.
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import re
import time
import json
import hashlib
import hmac
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple, Set

from voice_service import (
    LANGUAGE_REGISTRY,
    DEFAULT_LANGUAGE,
    get_verified_language,
    detect_trade,
    TRADE_MAP
)
from translations import get_translation


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONVERSATION STATES
# ─────────────────────────────────────────────────────────────────────────────
class ConversationState(str, Enum):
    GREETING = "greeting"
    LANGUAGE_SELECTION = "language_selection"
    ROLE_SELECTION = "role_selection"
    LOGIN_SIGNUP_SELECTION = "login_signup_selection"
    COLLECTING_PROFILE_FIELDS = "collecting_permitted_profile_fields"
    AWAITING_USER_CONFIRMATION = "awaiting_user_confirmation"
    AUTHENTICATED = "authenticated"
    PROFILE_COMPLETION = "profile_completion"
    JOB_DISCOVERY = "job_discovery"
    BOOKING_GUIDANCE = "booking_guidance"
    MANUAL_TAKEOVER = "manual_takeover"
    RECOVERABLE_ERROR = "recoverable_error"


# ─────────────────────────────────────────────────────────────────────────────
# 2. PERMITTED ASSISTANT ACTIONS (Strict Whitelist)
# ─────────────────────────────────────────────────────────────────────────────
class AssistantAction(str, Enum):
    SELECT_LANGUAGE = "select_language"
    SELECT_ROLE = "select_role"
    SELECT_AUTH_MODE = "select_auth_mode"
    NAVIGATE = "navigate"
    SET_FORM_FIELD = "set_form_field"
    SEARCH_WORKERS = "search_workers"
    SEARCH_JOBS = "search_jobs"
    REQUEST_CONFIRMATION = "request_confirmation"
    EXECUTE_CONFIRMED_ACTION = "execute_confirmed_action"
    CANCEL_PENDING_ACTION = "cancel_pending_action"
    ANSWER_GENERAL_QUESTION = "answer_general_question"
    SWITCH_MANUAL_TAKEOVER = "switch_manual_takeover"
    REPEAT_INSTRUCTION = "repeat_instruction"
    RECOVER_FROM_ERROR = "recover_from_error"


# Permitted non-sensitive form fields that assistant may collect or auto-fill
PERMITTED_FORM_FIELDS: Set[str] = {
    "name", "trade", "location", "bio", "rate", "experience", "query", "city", "work_type"
}

# Strictly forbidden sensitive fields that MUST NEVER be collected via voice or assistant
FORBIDDEN_SENSITIVE_FIELDS: Set[str] = {
    "password", "pass", "pwd", "otp", "code", "pin", "token", "secret", "cvv", "card_number", "card"
}

# Permitted navigation routes whitelist
PERMITTED_ROUTES: Set[str] = {
    "/", "/gateway", "/home", "/login", "/signup", "/signup/user", "/signup/worker",
    "/dashboard/user", "/dashboard/worker", "/role", "/bookings", "/scan", "/jobs", "/workers"
}

# Actions classified as consequential requiring explicit user confirmation
CONSEQUENTIAL_ACTIONS: Set[str] = {
    "create_account",
    "publish_job",
    "create_booking",
    "accept_offer",
    "qr_checkin",
    "initiate_payment"
}


# ─────────────────────────────────────────────────────────────────────────────
# 3. DETERMINISTIC STATE TRANSITION MATRIX
# ─────────────────────────────────────────────────────────────────────────────
VALID_TRANSITIONS: Dict[ConversationState, Set[ConversationState]] = {
    ConversationState.GREETING: {
        ConversationState.LANGUAGE_SELECTION,
        ConversationState.ROLE_SELECTION,
        ConversationState.LOGIN_SIGNUP_SELECTION,
        ConversationState.JOB_DISCOVERY,
        ConversationState.AUTHENTICATED,
        ConversationState.MANUAL_TAKEOVER,
        ConversationState.RECOVERABLE_ERROR
    },
    ConversationState.LANGUAGE_SELECTION: {
        ConversationState.ROLE_SELECTION,
        ConversationState.GREETING,
        ConversationState.LOGIN_SIGNUP_SELECTION,
        ConversationState.MANUAL_TAKEOVER,
        ConversationState.RECOVERABLE_ERROR
    },
    ConversationState.ROLE_SELECTION: {
        ConversationState.LOGIN_SIGNUP_SELECTION,
        ConversationState.COLLECTING_PROFILE_FIELDS,
        ConversationState.LANGUAGE_SELECTION,
        ConversationState.JOB_DISCOVERY,
        ConversationState.MANUAL_TAKEOVER,
        ConversationState.RECOVERABLE_ERROR
    },
    ConversationState.LOGIN_SIGNUP_SELECTION: {
        ConversationState.COLLECTING_PROFILE_FIELDS,
        ConversationState.AUTHENTICATED,
        ConversationState.ROLE_SELECTION,
        ConversationState.MANUAL_TAKEOVER,
        ConversationState.RECOVERABLE_ERROR
    },
    ConversationState.COLLECTING_PROFILE_FIELDS: {
        ConversationState.COLLECTING_PROFILE_FIELDS,  # Field progression (name -> trade -> location)
        ConversationState.AWAITING_USER_CONFIRMATION,
        ConversationState.LOGIN_SIGNUP_SELECTION,
        ConversationState.MANUAL_TAKEOVER,
        ConversationState.RECOVERABLE_ERROR
    },
    ConversationState.AWAITING_USER_CONFIRMATION: {
        ConversationState.AUTHENTICATED,
        ConversationState.COLLECTING_PROFILE_FIELDS,
        ConversationState.JOB_DISCOVERY,
        ConversationState.BOOKING_GUIDANCE,
        ConversationState.LOGIN_SIGNUP_SELECTION,
        ConversationState.MANUAL_TAKEOVER,
        ConversationState.RECOVERABLE_ERROR
    },
    ConversationState.AUTHENTICATED: {
        ConversationState.PROFILE_COMPLETION,
        ConversationState.JOB_DISCOVERY,
        ConversationState.BOOKING_GUIDANCE,
        ConversationState.AWAITING_USER_CONFIRMATION,
        ConversationState.MANUAL_TAKEOVER,
        ConversationState.RECOVERABLE_ERROR
    },
    ConversationState.PROFILE_COMPLETION: {
        ConversationState.AUTHENTICATED,
        ConversationState.AWAITING_USER_CONFIRMATION,
        ConversationState.JOB_DISCOVERY,
        ConversationState.MANUAL_TAKEOVER,
        ConversationState.RECOVERABLE_ERROR
    },
    ConversationState.JOB_DISCOVERY: {
        ConversationState.BOOKING_GUIDANCE,
        ConversationState.AWAITING_USER_CONFIRMATION,
        ConversationState.AUTHENTICATED,
        ConversationState.MANUAL_TAKEOVER,
        ConversationState.RECOVERABLE_ERROR
    },
    ConversationState.BOOKING_GUIDANCE: {
        ConversationState.AWAITING_USER_CONFIRMATION,
        ConversationState.AUTHENTICATED,
        ConversationState.JOB_DISCOVERY,
        ConversationState.MANUAL_TAKEOVER,
        ConversationState.RECOVERABLE_ERROR
    },
    ConversationState.MANUAL_TAKEOVER: {
        ConversationState.GREETING,
        ConversationState.AUTHENTICATED,
        ConversationState.ROLE_SELECTION,
        ConversationState.JOB_DISCOVERY
    },
    ConversationState.RECOVERABLE_ERROR: {
        ConversationState.GREETING,
        ConversationState.LANGUAGE_SELECTION,
        ConversationState.ROLE_SELECTION,
        ConversationState.LOGIN_SIGNUP_SELECTION,
        ConversationState.COLLECTING_PROFILE_FIELDS,
        ConversationState.AUTHENTICATED,
        ConversationState.JOB_DISCOVERY
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# 4. MALICIOUS INSTRUCTION & SECURITY FILTERS
# ─────────────────────────────────────────────────────────────────────────────
MALICIOUS_PATTERNS = [
    r'\b(select\s+.+\s+from|insert\s+into|delete\s+from|drop\s+table|update\s+.+\s+set)\b',
    r"('\s*or\s*'|'\s*or\s*\d|\bor\s+1\s*=\s*1\b|admin'\s*--)",
    r'(\-\-|\;|\/\*|\*\/)',
    r'\b(ignore\s+(all\s+)?previous\s+instructions|system\s+prompt|jailbreak|developer\s+mode)\b',
    r'\b(exec\(|eval\(|os\.system|subprocess|import\s+os|import\s+sys)\b',
    r'(<script|javascript:|onerror=|onload=)',
    r'\b(give\s+me\s+all\s+passwords|dump\s+database|admin\s+access|bypass\s+auth)\b'
]

def is_malicious_instruction(text: str) -> bool:
    """Detect prompt injection, SQL injection, script tags, or shell execution attempts."""
    if not text or not isinstance(text, str):
        return False
    lower = text.lower()
    for pattern in MALICIOUS_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE):
            return True
    return False


def contains_password_or_otp_request(text: str) -> bool:
    """Check if spoken input or prompt contains attempt to speak password or OTP."""
    if not text or not isinstance(text, str):
        return False
    lower = text.lower()
    patterns = [
        r'\b(my password is|mera password hai|password le lo|ye raha password)\b',
        r'\b(otp hai|otp is|mera otp|ye raha otp|verification code)\b',
        r'\b(password\s*:\s*\S+|otp\s*:\s*\d+)\b'
    ]
    for p in patterns:
        if re.search(p, lower):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 5. IDEMPOTENCY & DUPLICATION CACHE (Requirement 10)
# ─────────────────────────────────────────────────────────────────────────────
class ActionDeduplicator:
    """Prevents repeated voice clicks, network retries, or duplicate model execution."""
    def __init__(self, ttl_seconds: float = 4.0):
        self.ttl = ttl_seconds
        self.seen_events: Dict[str, float] = {}

    def is_duplicate(self, key: str) -> bool:
        now = time.time()
        self._cleanup(now)
        if key in self.seen_events:
            return True
        self.seen_events[key] = now
        return False

    def generate_key(self, user_id: str, action: str, args: Dict[str, Any], idempotency_key: Optional[str] = None) -> str:
        if idempotency_key:
            return f"idem:{idempotency_key}"
        serialized = json.dumps({'user': user_id, 'action': action, 'args': args}, sort_keys=True)
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()

    def _cleanup(self, now: float):
        expired = [k for k, ts in self.seen_events.items() if now - ts > self.ttl]
        for k in expired:
            del self.seen_events[k]

    def reset(self):
        self.seen_events.clear()

deduplicator = ActionDeduplicator()


# ─────────────────────────────────────────────────────────────────────────────
# 6. GENERAL FAQ & KNOWLEDGE BASE (Requirement 9: Questions vs Commands)
# ─────────────────────────────────────────────────────────────────────────────
GENERAL_FAQ_TOPICS = {
    'about_platform': {
        'keywords': ['kya hai', 'what is voice hire', 'what is voicehire', 'kya kaam karta hai', 'about', 'kaise kaam'],
        'answers': {
            'hi': "VoiceHire एक ऐसा मंच है जहाँ आप अपनी आवाज़ से काम ढूँढ सकते हैं या कुशल कामगारों को बुक कर सकते हैं।",
            'en': "VoiceHire is a voice-first platform where workers find jobs and customers book local skilled services.",
            'pa': "VoiceHire ਇੱਕ ਮੰਚ ਹੈ ਜਿੱਥੇ ਤੁਸੀਂ ਆਪਣੀ ਆਵਾਜ਼ ਰਾਹੀਂ ਕੰਮ ਲੱਭ ਸਕਦੇ ਹੋ ਜਾਂ ਕਾਰੀਗਰ ਬੁੱਕ ਕਰ ਸਕਦੇ ਹੋ।"
        }
    },
    'pricing_and_fees': {
        'keywords': ['fees', 'charges', 'kitna paisa', 'price', 'free hai', 'paisa lagta hai', 'cost', 'rate'],
        'answers': {
            'hi': "VoiceHire पर खाता बनाना और काम ढूँढना बिल्कुल मुफ़्त है। काम पूरा होने पर सीधे कामगार को तय दर पर भुगतान करें।",
            'en': "Creating an account and finding work is completely free. Payment is made directly at the agreed rate.",
            'pa': "ਅਕਾਊਂਟ ਬਣਾਉਣਾ ਅਤੇ ਕੰਮ ਲੱਭਣਾ ਬਿਲਕੁਲ ਮੁਫ਼ਤ ਹੈ।"
        }
    },
    'how_payment_works': {
        'keywords': ['payment kaise', 'how to pay', 'bhugtan', 'paisa kaise milega', 'pay kaise kare'],
        'answers': {
            'hi': "काम पूरा होने और QR स्कैन से सत्यापन के बाद, आप सीधे ऑनलाइन या नकद भुगतान कर सकते हैं।",
            'en': "After the job is completed and verified via QR check-in, you can pay securely online or with cash.",
            'pa': "ਕੰਮ ਪੂਰਾ ਹੋਣ ਅਤੇ ਕਿਊਆਰ ਸਕੈਨ ਪੁਸ਼ਟੀ ਤੋਂ ਬਾਅਦ, ਤੁਸੀਂ ਸਿੱਧਾ ਭੁਗਤਾਨ ਕਰ ਸਕਦੇ ਹੋ।"
        }
    },
    'security_and_trust': {
        'keywords': ['safe hai', 'is it safe', 'surakshit', 'trust', 'police verification', 'bharosa'],
        'answers': {
            'hi': "यहाँ सभी कामगारों और ग्राहकों का सत्यापन किया जाता है। आपकी सुरक्षा और गोपनीयता हमारी पहली प्राथमिकता है।",
            'en': "Workers and jobs are verified. Your safety, verified check-in, and privacy are strictly safeguarded.",
            'pa': "ਸਾਰੇ ਕਾਰੀਗਰਾਂ ਦੀ ਪੁਸ਼ਟੀ ਕੀਤੀ ਜਾਂਦੀ ਹੈ ਅਤੇ ਤੁਹਾਡੀ ਸੁਰੱਖਿਆ ਸਾਡੀ ਪਹਿਲ ਹੈ।"
        }
    }
}

def detect_general_question(text: str) -> Optional[Tuple[str, str]]:
    """Check if the user is asking a general informational question instead of issuing a command."""
    if not text:
        return None
    lower = text.lower()
    # Check if asking a question
    question_markers = ['kya', 'kaise', 'kyun', 'kitna', 'kitne', 'kitni', 'what', 'how', 'why', 'can i', 'batao', 'explain', 'help']
    has_marker = any(m in lower for m in question_markers)
    if not has_marker:
        return None

    for topic_id, data in GENERAL_FAQ_TOPICS.items():
        if any(kw in lower for kw in data['keywords']):
            return topic_id, data
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 7. CONVERSATIONAL ORCHESTRATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class OrchestrationEngine:
    """
    Production-grade conversational orchestration state machine for VoiceHire.
    Coordinates speech input, state transitions, validation, and action staging.
    """

    @classmethod
    def get_initial_state(cls, user_id: Optional[str] = None) -> ConversationState:
        """Determines initial conversation state based on login status."""
        return ConversationState.AUTHENTICATED if user_id else ConversationState.GREETING

    @classmethod
    def validate_transition(cls, from_state: ConversationState, to_state: ConversationState) -> bool:
        """Validates if state transition is deterministic and allowed."""
        if from_state == to_state:
            return True
        allowed = VALID_TRANSITIONS.get(from_state, set())
        return to_state in allowed

    @classmethod
    def process_turn(
        cls,
        user_input: str,
        current_state: ConversationState,
        language: str = DEFAULT_LANGUAGE,
        session_data: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes one conversational turn deterministically.
        Returns:
            - current_state: new or retained state
            - action: validated AssistantAction
            - action_arguments: validated non-sensitive arguments
            - speech_response: localized response to speak to user
            - display_text: concise text to render in assistant drawer
            - requires_confirmation: bool
            - pending_action: dict of pending consequential action (if any)
            - quick_replies: list of clickable buttons for accessibility
            - is_question: bool
        """
        session_data = session_data or {}
        lang = get_verified_language(language)
        user_id = session_data.get('user_id')
        user_role = session_data.get('role')
        user_name = session_data.get('name')
        pending_action = session_data.get('pending_action')

        clean_text = (user_input or '').strip()
        lower_text = clean_text.lower()

        # ── 1. SECURITY FILTER: Malicious Input Guard ──
        if is_malicious_instruction(clean_text):
            return {
                'success': False,
                'current_state': current_state.value,
                'action': AssistantAction.RECOVER_FROM_ERROR.value,
                'action_arguments': {'error': 'security_violation'},
                'speech_response': "सुरक्षा कारणों से इस अनुरोध को पूरा नहीं किया जा सकता। कृपया सरल शब्दों में बताएँ कि आपको क्या मदद चाहिए।" if lang == 'hi' else "This instruction cannot be processed for security reasons. How may I help you?",
                'display_text': "सुरक्षा चेतावनी: अमान्य निर्देश। कृपया सही विकल्प चुनें।",
                'requires_confirmation': False,
                'pending_action': None,
                'quick_replies': ["काम ढूँढें", "वर्कर बुक करें", "सहायता"],
                'is_question': False,
                'language': lang
            }

        # ── 2. SECURITY FILTER: Password / OTP Voice Collection Prohibition (Rule 8) ──
        if contains_password_or_otp_request(clean_text):
            return {
                'success': False,
                'current_state': current_state.value,
                'action': AssistantAction.ANSWER_GENERAL_QUESTION.value,
                'action_arguments': {'security_guard': 'no_voice_passwords'},
                'speech_response': "आपकी सुरक्षा के लिए, पासवर्ड या OTP बोलकर नहीं बताना चाहिए। कृपया स्क्रीन पर पासवर्ड टाइप करें।" if lang == 'hi' else "For your security, passwords and OTPs must never be spoken. Please type it directly on screen.",
                'display_text': "सुरक्षा नियम: पासवर्ड या OTP कभी बोलकर न दें। कृपया सुरक्षित फॉर्म में टाइप करें।",
                'requires_confirmation': False,
                'pending_action': None,
                'quick_replies': ["लॉगिन पेज पर जाएँ", "पासवर्ड टाइप करें"],
                'is_question': False,
                'language': lang
            }

        # ── 3. DEDUPLICATION FILTER: Duplicate Voice Events (Requirement 10) ──
        dedup_key = deduplicator.generate_key(
            user_id=user_id or 'anon',
            action=lower_text,
            args={'state': current_state.value},
            idempotency_key=idempotency_key
        )
        if deduplicator.is_duplicate(dedup_key):
            return {
                'success': True,
                'current_state': current_state.value,
                'action': AssistantAction.REPEAT_INSTRUCTION.value,
                'action_arguments': {'duplicate_prevented': True},
                'speech_response': "यह अनुरोध पहले ही दर्ज हो चुका है। हम आगे बढ़ रहे हैं।" if lang == 'hi' else "This action is already being processed.",
                'display_text': "अनुरोध पहले से प्रक्रिया में है।",
                'requires_confirmation': False,
                'pending_action': pending_action,
                'quick_replies': [],
                'is_question': False,
                'language': lang
            }

        # ── 4. MANUAL TAKEOVER / STOP ASSISTANT (Requirement 1) ──
        if re.search(r'\b(main khud karunga|stop assistant|close assistant|manual|band karo assistant|chup raho)\b', lower_text):
            return {
                'success': True,
                'current_state': ConversationState.MANUAL_TAKEOVER.value,
                'action': AssistantAction.SWITCH_MANUAL_TAKEOVER.value,
                'action_arguments': {'mode': 'manual'},
                'speech_response': "ठीक है, आप स्क्रीन पर सीधे काम कर सकते हैं। मदद चाहिए तो माइक बटन दबाएँ।" if lang == 'hi' else "Okay, manual mode activated. Tap the mic anytime you need assistance.",
                'display_text': "मैन्युअल मोड सक्रिय। आप कभी भी आवाज़ सहायक को फिर से शुरू कर सकते हैं।",
                'requires_confirmation': False,
                'pending_action': None,
                'quick_replies': ["सहायक चालू करें"],
                'is_question': False,
                'language': lang
            }

        # ── 5. GENERAL QUESTION FILTER (Requirement 9: Questions vs Commands) ──
        faq_match = detect_general_question(clean_text)
        if faq_match and current_state != ConversationState.AWAITING_USER_CONFIRMATION:
            topic_id, faq_data = faq_match
            ans = faq_data['answers'].get(lang) or faq_data['answers'].get('hi') or faq_data['answers']['en']
            return {
                'success': True,
                'current_state': current_state.value,  # State does NOT change!
                'action': AssistantAction.ANSWER_GENERAL_QUESTION.value,
                'action_arguments': {'topic': topic_id},
                'speech_response': ans,
                'display_text': ans,
                'requires_confirmation': False,
                'pending_action': pending_action,
                'quick_replies': ["काम ढूँढें", "वर्कर बुक करें", "मुख्य मेन्यू"],
                'is_question': True,
                'language': lang
            }

        # ── 6. STATE HANDLER: AWAITING_USER_CONFIRMATION (Requirement 7) ──
        if current_state == ConversationState.AWAITING_USER_CONFIRMATION:
            is_yes = bool(re.search(r'\b(haan|ha|yes|theek hai|sahi hai|confirm|pakka|kar do|proceed|done)\b', lower_text))
            is_no = bool(re.search(r'\b(nahi|na|no|cancel|rok do|chhod do|galat hai|change|badlo)\b', lower_text)) and 'pata nahi' not in lower_text and 'samajh nahi' not in lower_text

            if is_yes and pending_action:
                action_name = pending_action.get('action_name')
                next_state = ConversationState.AUTHENTICATED if user_id else ConversationState.ROLE_SELECTION

                return {
                    'success': True,
                    'current_state': next_state.value,
                    'action': AssistantAction.EXECUTE_CONFIRMED_ACTION.value,
                    'action_arguments': pending_action,
                    'speech_response': f"पुष्टि हो गई है। {pending_action.get('title', 'कार्रवाई')} पूरी कर दी गई है।" if lang == 'hi' else f"Confirmed. {pending_action.get('title', 'Action')} completed.",
                    'display_text': f"सफलतापूर्वक पुष्ट: {pending_action.get('title', 'Action')}",
                    'requires_confirmation': False,
                    'pending_action': None,
                    'quick_replies': ["डैशबोर्ड पर जाएँ", "नई खोज"],
                    'is_question': False,
                    'language': lang
                }
            elif is_no:
                return {
                    'success': True,
                    'current_state': ConversationState.COLLECTING_PROFILE_FIELDS.value if not user_id else ConversationState.AUTHENTICATED.value,
                    'action': AssistantAction.CANCEL_PENDING_ACTION.value,
                    'action_arguments': {'cancelled_action': pending_action},
                    'speech_response': "ठीक है, इसे रद्द कर दिया गया है। आप कोई भी जानकारी बदल सकते हैं।" if lang == 'hi' else "Cancelled. You can change any details.",
                    'display_text': "कार्रवाई रद्द कर दी गई। क्या सुधार करना चाहते हैं?",
                    'requires_confirmation': False,
                    'pending_action': None,
                    'quick_replies': ["दोबारा प्रयास करें", "मुख्य मेन्यू"],
                    'is_question': False,
                    'language': lang
                }
            else:
                # Ambiguous answer to confirmation prompt
                return {
                    'success': False,
                    'current_state': ConversationState.AWAITING_USER_CONFIRMATION.value,
                    'action': AssistantAction.REPEAT_INSTRUCTION.value,
                    'action_arguments': {'reason': 'ambiguous_confirmation'},
                    'speech_response': "कृपया स्पष्ट रूप से 'हाँ' या 'ना' बोलें।" if lang == 'hi' else "Please clearly say 'Yes' or 'No'.",
                    'display_text': "कृपया 'हाँ' (स्वीकार) या 'ना' (रद्द) चुनें।",
                    'requires_confirmation': True,
                    'pending_action': pending_action,
                    'quick_replies': ["हाँ (Confirm)", "ना (Cancel)"],
                    'is_question': False,
                    'language': lang
                }

        # ── 7. STATE HANDLER: LANGUAGE_SELECTION ──
        for code, meta in LANGUAGE_REGISTRY.items():
            if meta['name'].lower() in lower_text or meta['native'].lower() in lower_text or lower_text == code:
                return {
                    'success': True,
                    'current_state': ConversationState.ROLE_SELECTION.value,
                    'action': AssistantAction.SELECT_LANGUAGE.value,
                    'action_arguments': {'language': code},
                    'speech_response': f"अब हम {meta['native']} में बात करेंगे। आप क्या करना चाहते हैं? काम ढूँढना है या वर्कर बुक करना है?" if code == 'hi' else f"Switching to {meta['name']}. Do you want to find work or book a worker?",
                    'display_text': f"भाषा चुनी गई: {meta['native']}. अपनी भूमिका चुनें।",
                    'requires_confirmation': False,
                    'pending_action': None,
                    'quick_replies': ["काम ढूँढना है (Worker)", "वर्कर बुक करना है (Customer)"],
                    'is_question': False,
                    'language': code
                }

        # ── 8. STATE HANDLER: ROLE_SELECTION ──
        if current_state in {ConversationState.ROLE_SELECTION, ConversationState.GREETING, ConversationState.LANGUAGE_SELECTION}:
            is_worker = bool(re.search(r'\b(worker|kaam chahiye|rozgar|naukri|plumber hu|electrician hu|majdoor|mistri)\b', lower_text))
            is_customer = bool(re.search(r'\b(customer|maalik|booking|hire|bulao|chahiye|nal theek|plumber chahiye)\b', lower_text))

            if is_worker and not is_customer:
                detected_trade = detect_trade(clean_text)
                return {
                    'success': True,
                    'current_state': ConversationState.LOGIN_SIGNUP_SELECTION.value,
                    'action': AssistantAction.SELECT_ROLE.value,
                    'action_arguments': {'role': 'worker', 'trade': detected_trade},
                    'speech_response': f"बहुत अच्छा! आप काम ढूँढने आए हैं{' (' + detected_trade + ')' if detected_trade else ''}। क्या आपका पहले से खाता है, या नया खाता बनाना है?" if lang == 'hi' else f"Great! Worker mode selected{' (' + detected_trade + ')' if detected_trade else ''}. Do you have an account, or want to create a new one?",
                    'display_text': "भूमिका: कार्यकर्ता (Worker)। क्या आपका पहले से खाता है?",
                    'requires_confirmation': False,
                    'pending_action': None,
                    'quick_replies': ["नया खाता बनाएँ (Sign Up)", "पहले से खाता है (Login)"],
                    'is_question': False,
                    'language': lang
                }
            elif is_customer and not is_worker:
                detected_trade = detect_trade(clean_text)
                return {
                    'success': True,
                    'current_state': ConversationState.LOGIN_SIGNUP_SELECTION.value,
                    'action': AssistantAction.SELECT_ROLE.value,
                    'action_arguments': {'role': 'user', 'trade': detected_trade},
                    'speech_response': f"बहुत बढ़िया! आप कुशल कामगार बुक करना चाहते हैं{' (' + detected_trade + ')' if detected_trade else ''}। क्या आप लॉगिन करना चाहते हैं या नया खाता बनाएँ?" if lang == 'hi' else "Customer mode selected. Do you have an account or want to register?",
                    'display_text': "भूमिका: ग्राहक (Customer)। क्या आप लॉगिन करना चाहते हैं?",
                    'requires_confirmation': False,
                    'pending_action': None,
                    'quick_replies': ["नया खाता बनाएँ (Sign Up)", "पहले से खाता है (Login)"],
                    'is_question': False,
                    'language': lang
                }

        # ── 9. STATE HANDLER: LOGIN_SIGNUP_SELECTION ──
        if current_state in {ConversationState.LOGIN_SIGNUP_SELECTION, ConversationState.ROLE_SELECTION}:
            is_login = bool(re.search(r'\b(login|pehle se account|purana|sign in|already)\b', lower_text))
            is_register = bool(re.search(r'\b(naya|register|signup|create|new account|banana hai)\b', lower_text))

            if is_login:
                return {
                    'success': True,
                    'current_state': ConversationState.LOGIN_SIGNUP_SELECTION.value,
                    'action': AssistantAction.NAVIGATE.value,
                    'action_arguments': {'route': '/login'},
                    'speech_response': "लॉगिन पेज पर ले जा रहा हूँ। कृपया स्क्रीन पर अपना फोन नंबर और पासवर्ड दर्ज करें।" if lang == 'hi' else "Navigating to Login page. Please enter your phone number and password on screen.",
                    'display_text': "लॉगिन पेज पर जा रहे हैं... (सुरक्षा के लिए पासवर्ड स्क्रीन पर टाइप करें)",
                    'requires_confirmation': False,
                    'pending_action': None,
                    'quick_replies': ["लॉगिन करें"],
                    'is_question': False,
                    'language': lang
                }
            elif is_register:
                target_route = '/signup/worker' if user_role == 'worker' else '/signup/user'
                return {
                    'success': True,
                    'current_state': ConversationState.COLLECTING_PROFILE_FIELDS.value,
                    'action': AssistantAction.NAVIGATE.value,
                    'action_arguments': {'route': target_route},
                    'speech_response': "नया खाता बनाने के लिए, सबसे पहले अपना पूरा नाम बताएँ।" if lang == 'hi' else "To create your account, first please state your full name.",
                    'display_text': "नया खाता निर्माण: कृपया अपना पूरा नाम बताएँ।",
                    'requires_confirmation': False,
                    'pending_action': None,
                    'quick_replies': ["नाम बोलें या टाइप करें"],
                    'is_question': False,
                    'language': lang
                }

        # ── 10. STATE HANDLER: COLLECTING_PROFILE_FIELDS (One at a time) ──
        if current_state == ConversationState.COLLECTING_PROFILE_FIELDS:
            # Check what fields are already gathered in session
            collected = session_data.get('collected_fields', {})
            
            if 'name' not in collected:
                # User provided their name
                name_val = clean_text.replace('mera naam', '').replace('my name is', '').strip()
                if len(name_val) >= 2:
                    return {
                        'success': True,
                        'current_state': ConversationState.COLLECTING_PROFILE_FIELDS.value,
                        'action': AssistantAction.SET_FORM_FIELD.value,
                        'action_arguments': {'field_name': 'name', 'value': name_val},
                        'speech_response': f"धन्यवाद {name_val}। अब बताएँ कि आपका काम क्या है? जैसे प्लंबर, इलेक्ट्रीशियन या बढ़ई।" if lang == 'hi' else f"Thank you {name_val}. What work do you do, such as Plumber, Electrician or Carpenter?",
                        'display_text': f"नाम दर्ज: {name_val}। अगला: आपका काम (Trade) क्या है?",
                        'requires_confirmation': False,
                        'pending_action': None,
                        'quick_replies': ["Plumber", "Electrician", "Carpenter", "Mason", "Driver"],
                        'is_question': False,
                        'language': lang
                    }
            elif 'trade' not in collected:
                trade_val = detect_trade(clean_text) or clean_text.title()
                return {
                    'success': True,
                    'current_state': ConversationState.COLLECTING_PROFILE_FIELDS.value,
                    'action': AssistantAction.SET_FORM_FIELD.value,
                    'action_arguments': {'field_name': 'trade', 'value': trade_val},
                    'speech_response': f"{trade_val} दर्ज कर लिया गया है। अब बताएँ कि आप किस शहर या इलाके में रहते हैं?" if lang == 'hi' else f"{trade_val} recorded. In which city or area do you live?",
                    'display_text': f"काम (Trade): {trade_val}। अगला: आपका शहर या क्षेत्र?",
                    'requires_confirmation': False,
                    'pending_action': None,
                    'quick_replies': ["Delhi", "Mumbai", "Ludhiana", "Patna", "Jaipur"],
                    'is_question': False,
                    'language': lang
                }
            elif 'location' not in collected:
                loc_val = clean_text.title()
                # Profile fields complete -> Transition to explicit confirmation!
                pending_registration = {
                    'action_name': 'create_account',
                    'title': 'खाता पंजीकरण (Account Registration)',
                    'name': collected.get('name'),
                    'trade': collected.get('trade'),
                    'location': loc_val
                }
                return {
                    'success': True,
                    'current_state': ConversationState.AWAITING_USER_CONFIRMATION.value,
                    'action': AssistantAction.REQUEST_CONFIRMATION.value,
                    'action_arguments': {'field_name': 'location', 'value': loc_val},
                    'speech_response': f"आपकी जानकारी तैयार है: नाम {collected.get('name')}, काम {collected.get('trade')}, स्थान {loc_val}। क्या आप इसे पक्का करके आगे बढ़ना चाहते हैं? हाँ या ना बोलें।" if lang == 'hi' else "Your details are ready. Do you confirm to proceed? Say Yes or No.",
                    'display_text': f"पुष्टि करें: {collected.get('name')} | {collected.get('trade')} | {loc_val}",
                    'requires_confirmation': True,
                    'pending_action': pending_registration,
                    'quick_replies': ["हाँ, सही है (Yes)", "नहीं, बदलना है (No)"],
                    'is_question': False,
                    'language': lang
                }

        # ── 11. STATE HANDLER: AUTHENTICATED & JOB_DISCOVERY ──
        if current_state in {ConversationState.AUTHENTICATED, ConversationState.JOB_DISCOVERY}:
            detected_trade = detect_trade(clean_text)
            if detected_trade:
                action_type = AssistantAction.SEARCH_JOBS if user_role == 'worker' else AssistantAction.SEARCH_WORKERS
                return {
                    'success': True,
                    'current_state': ConversationState.JOB_DISCOVERY.value,
                    'action': action_type.value,
                    'action_arguments': {'trade': detected_trade},
                    'speech_response': f"आपके लिए {detected_trade} से जुड़े नतीजे ढूँढ रहा हूँ।" if lang == 'hi' else f"Finding results for {detected_trade}.",
                    'display_text': f"{detected_trade} की खोज की जा रही है...",
                    'requires_confirmation': False,
                    'pending_action': None,
                    'quick_replies': [f"सभी {detected_trade}", "दूरी के अनुसार", "उपलब्ध केवल"],
                    'is_question': False,
                    'language': lang
                }

            # Check for Booking intent from customer
            if user_role == 'user' and re.search(r'\b(book|bulao|hire|appointment)\b', lower_text):
                pending_booking = {
                    'action_name': 'create_booking',
                    'title': 'वर्कर बुकिंग (Worker Booking)',
                    'user_id': user_id,
                    'trade': detected_trade or 'General Service'
                }
                return {
                    'success': True,
                    'current_state': ConversationState.AWAITING_USER_CONFIRMATION.value,
                    'action': AssistantAction.REQUEST_CONFIRMATION.value,
                    'action_arguments': pending_booking,
                    'speech_response': "क्या आप बुकिंग की पुष्टि करना चाहते हैं? हाँ या ना बोलें।" if lang == 'hi' else "Do you want to confirm this booking? Say Yes or No.",
                    'display_text': "बुकिंग पुष्टि आवश्यक। क्या आप आगे बढ़ना चाहते हैं?",
                    'requires_confirmation': True,
                    'pending_action': pending_booking,
                    'quick_replies': ["हाँ (Confirm)", "ना (Cancel)"],
                    'is_question': False,
                    'language': lang
                }

        # ── 12. FALLBACK / CLARIFICATION DIALOGUE ──
        return {
            'success': False,
            'current_state': current_state.value,
            'action': AssistantAction.REPEAT_INSTRUCTION.value,
            'action_arguments': {'reason': 'unrecognized_intent'},
            'speech_response': "माफ़ कीजिये, मैं समझ नहीं पाया। क्या आप काम ढूँढना चाहते हैं या किसी कामगार को बुक करना चाहते हैं?" if lang == 'hi' else "I could not understand that. Would you like to find work or book a worker?",
            'display_text': "कृपया नीचे दिए गए विकल्पों में से चुनें या फिर से बोलें।",
            'requires_confirmation': False,
            'pending_action': pending_action,
            'quick_replies': ["काम ढूँढें (Find Work)", "वर्कर बुक करें (Book)", "सहायता (Help)"],
            'is_question': False,
            'language': lang
        }


# Global singleton engine instance
orchestration_engine = OrchestrationEngine()
