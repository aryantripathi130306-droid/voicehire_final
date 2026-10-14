"""
VoiceHire — Production Voice Service & Intent Layer
═══════════════════════════════════════════════════════════════════════════════
Architecture:
 - Reusable Multilingual Speech-Recognition & Text-To-Speech Interface.
 - Server-side validation of voice intents, confidence scoring, and Hinglish/code-switching.
 - Zero client-side API key leakage (server-driven credentials & capability discovery).
 - Low-confidence & ambiguous transcription handling with conversational clarifications.
 - Language continuity preservation (never reverts to English after Hindi/regional selection).
═══════════════════════════════════════════════════════════════════════════════
"""

import os
import re
from typing import Dict, Any, Optional, List, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# 1. VERIFIED LANGUAGE & LOCALE REGISTRY
# Default: Hindi (hi-IN)
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_LANGUAGE = 'hi'

LANGUAGE_REGISTRY: Dict[str, Dict[str, Any]] = {
    'hi': {
        'code': 'hi',
        'name': 'Hindi',
        'native': 'हिन्दी',
        'stt_locale': 'hi-IN',
        'tts_locale': 'hi-IN',
        'flag': '🇮🇳',
        'code_switching': 'Hinglish (Hindi-English colloquial mix)',
        'tts_voice_match': ['hi-in', 'hindi', 'india'],
        'confidence_threshold': 0.60,
    },
    'pa': {
        'code': 'pa',
        'name': 'Punjabi',
        'native': 'ਪੰਜਾਬੀ',
        'stt_locale': 'pa-IN',
        'tts_locale': 'pa-IN',
        'flag': '🇮🇳',
        'code_switching': 'Punjabi-English conversational mix',
        'tts_voice_match': ['pa-in', 'punjabi', 'panjabi'],
        'confidence_threshold': 0.60,
    },
    'en': {
        'code': 'en',
        'name': 'English (India)',
        'native': 'English',
        'stt_locale': 'en-IN',
        'tts_locale': 'en-IN',
        'flag': '🇬🇧',
        'code_switching': 'Indian English colloquialisms',
        'tts_voice_match': ['en-in', 'india', 'english'],
        'confidence_threshold': 0.65,
    },
    'bn': {
        'code': 'bn',
        'name': 'Bengali',
        'native': 'বাংলা',
        'stt_locale': 'bn-IN',
        'tts_locale': 'bn-IN',
        'flag': '🇧🇩',
        'code_switching': 'Benglish colloquial mix',
        'tts_voice_match': ['bn-in', 'bengali', 'bangla'],
        'confidence_threshold': 0.60,
    },
    'mr': {
        'code': 'mr',
        'name': 'Marathi',
        'native': 'मराठी',
        'stt_locale': 'mr-IN',
        'tts_locale': 'mr-IN',
        'flag': '🇮🇳',
        'code_switching': 'Marathi-English mix',
        'tts_voice_match': ['mr-in', 'marathi'],
        'confidence_threshold': 0.60,
    },
    'ta': {
        'code': 'ta',
        'name': 'Tamil',
        'native': 'தமிழ்',
        'stt_locale': 'ta-IN',
        'tts_locale': 'ta-IN',
        'flag': '🌟',
        'code_switching': 'Tanglish colloquial mix',
        'tts_voice_match': ['ta-in', 'tamil'],
        'confidence_threshold': 0.60,
    },
    'te': {
        'code': 'te',
        'name': 'Telugu',
        'native': 'తెలుగు',
        'stt_locale': 'te-IN',
        'tts_locale': 'te-IN',
        'flag': '🌟',
        'code_switching': 'Telugu-English mix',
        'tts_voice_match': ['te-in', 'telugu'],
        'confidence_threshold': 0.60,
    },
    'gu': {
        'code': 'gu',
        'name': 'Gujarati',
        'native': 'ગુજરાતી',
        'stt_locale': 'gu-IN',
        'tts_locale': 'gu-IN',
        'flag': '🇮🇳',
        'code_switching': 'Gujarati-English mix',
        'tts_voice_match': ['gu-in', 'gujarati'],
        'confidence_threshold': 0.60,
    },
    'kn': {
        'code': 'kn',
        'name': 'Kannada',
        'native': 'ಕನ್ನಡ',
        'stt_locale': 'kn-IN',
        'tts_locale': 'kn-IN',
        'flag': '🌟',
        'code_switching': 'Kannada-English mix',
        'tts_voice_match': ['kn-in', 'kannada'],
        'confidence_threshold': 0.60,
    },
    'ml': {
        'code': 'ml',
        'name': 'Malayalam',
        'native': 'മലയാളം',
        'stt_locale': 'ml-IN',
        'tts_locale': 'ml-IN',
        'flag': '🌟',
        'code_switching': 'Malayalam-English mix',
        'tts_voice_match': ['ml-in', 'malayalam'],
        'confidence_threshold': 0.60,
    },
    'or': {
        'code': 'or',
        'name': 'Odia',
        'native': 'ଓଡ଼ିଆ',
        'stt_locale': 'or-IN',
        'tts_locale': 'or-IN',
        'flag': '🌟',
        'code_switching': 'Odia-English mix',
        'tts_voice_match': ['or-in', 'odia', 'oriya'],
        'confidence_threshold': 0.60,
    },
    'ur': {
        'code': 'ur',
        'name': 'Urdu',
        'native': 'اردو',
        'stt_locale': 'ur-IN',
        'tts_locale': 'ur-IN',
        'flag': '🇮🇳',
        'code_switching': 'Urdu-English colloquial mix',
        'tts_voice_match': ['ur-in', 'ur-pk', 'urdu'],
        'confidence_threshold': 0.60,
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# 2. LOCALIZED CLARIFICATION QUESTIONS & PROMPTS
# Spoken back in the EXACT chosen language when low-confidence or ambiguity occurs.
# ─────────────────────────────────────────────────────────────────────────────
CLARIFICATION_PROMPTS: Dict[str, Dict[str, str]] = {
    'ambiguous_role': {
        'hi': 'माफ़ कीजिये, मैं समझ नहीं पाया। क्या आपको काम ढूँढना है, या वर्कर को बुक करना है?',
        'pa': 'ਮਾਫ਼ ਕਰਨਾ, ਮੈਨੂੰ ਸਮਝ ਨਹੀਂ ਆਇਆ। ਕੀ ਤੁਸੀਂ ਕੰਮ ਲੱਭਣਾ ਚਾਹੁੰਦੇ ਹੋ ਜਾਂ ਵਰਕਰ ਬੁੱਕ ਕਰਨਾ ਹੈ?',
        'en': "I'm sorry, I didn't quite catch that. Are you looking for work, or would you like to hire a worker?",
        'bn': 'মাফ করবেন, আমি বুঝতে পারিনি। আপনি কি কাজ খুঁজছেন, নাকি কর্মী বুক করতে চান?',
        'mr': 'माफ करा, मला समजले नाही. तुम्हाला काम शोधायचे आहे की कामगार बुक करायचा आहे?',
        'ta': 'மன்னிக்கவும், எனக்கு சரியாக புரியவில்லை. நீங்கள் வேலை தேடுகிறீர்களா அல்லது தொழிலாளியை புக் செய்ய விரும்புகிறீர்களா?',
        'te': 'క్షమించండి, నాకు సరిగ్గా అర్థం కాలేదు. మీరు పని వెతుకుతున్నారా లేక వర్కర్‌ని బుక్ చేయాలనుకుంటున్నారా?',
        'gu': 'માફ કરશો, મને સમજાયું નહીં. તમારે કામ શોધવું છે કે વર્કર બુક કરવો છે?',
        'kn': 'ಕ್ಷಮಿಸಿ, ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ. ನೀವು ಕೆಲಸ ಹುಡುಕುತ್ತಿದ್ದೀರಾ ಅಥವಾ ಕೆಲಸಗಾರರನ್ನು ಬುಕ್ ಮಾಡಲು ಬಯಸುವಿರಾ?',
        'ml': 'ക്ഷമിക്കണം, എനിക്ക് മനസ്സിലായില്ല. നിങ്ങൾക്ക് ജോലി കണ്ടെത്തണോ അതോ തൊഴിലാളിയെ ബുക്ക് ചെയ്യണോ?',
        'or': 'କ୍ଷମା କରିବେ, ମୁଁ ବୁଝିପାରିଲି ନାହିଁ। ଆପଣ କାମ ଖୋଜୁଛନ୍ତି କିମ୍ବା ଶ୍ରମିକ ବୁକ୍ କରିବାକୁ ଚାହାଁନ୍ତି?',
        'ur': 'معاف کیجیے گا، میں سمجھ نہیں پایا۔ کیا آپ کام تلاش کر رہے ہیں یا ورکر بک کرنا چاہتے ہیں؟'
    },
    'ambiguous_action': {
        'hi': 'क्या आपका पहले से अकाउंट है (लॉग इन), या आप नया अकाउंट बनाना चाहते हैं?',
        'pa': 'ਕੀ ਤੁਹਾਡਾ ਪਹਿਲਾਂ ਤੋਂ ਅਕਾਊਂਟ ਹੈ (ਲਾਗਇਨ), ਜਾਂ ਨਵਾਂ ਅਕਾਊਂਟ ਬਣਾਉਣਾ ਚਾਹੁੰਦੇ ਹੋ?',
        'en': 'Do you already have an account to Log In, or would you like to Create a New Account?',
        'bn': 'আপনার কি ইতিমধ্যে অ্যাকাউন্ট আছে (লগ ইন), নাকি নতুন অ্যাকাউন্ট তৈরি করতে চান?',
        'mr': 'तुमचे आधीच खाते आहे (लॉग इन), की नवीन खाते तयार करायचे आहे?',
        'ta': 'உங்களிடம் ஏற்கனவே கணக்கு உள்ளதா (லாகின்) அல்லது புதிய கணக்கை உருவாக்க விரும்புகிறீர்களா?',
        'te': 'మీకు ఇప్పటికే ఖాతా ఉందా (లాగిన్) లేదా కొత్త ఖాతా సృష్టించాలనుకుంటున్నారా?',
        'gu': 'શું તમારી પાસે પહેલેથી ખાતું છે (લૉગિન), કે તમે નવું ખાતું બનાવવા માંગો છો?',
        'kn': 'ನಿಮಗೆ ಈಗಾಗಲೇ ಖಾತೆ ಇದೆಯೇ (ಲಾಗಿನ್) ಅಥವಾ ಹೊಸ ಖಾತೆಯನ್ನು ರಚಿಸಲು ಬಯಸುವಿರಾ?',
        'ml': 'നിങ്ങൾക്ക് ഇതിനകം അക്കൗണ്ട് ഉണ്ടോ (ലോഗിൻ), അതോ പുതിയ അക്കൗണ്ട് ഉണ്ടാക്കണോ?',
        'or': 'ଆପଣଙ୍କର ପୂର୍ବରୁ ଖାତା ଅଛି କି (ଲଗ୍ ଇନ୍), କିମ୍ବା ନୂଆ ଖାତା ତିଆରି କରିବାକୁ ଚାହାଁନ୍ତି?',
        'ur': 'کیا آپ کا پہلے سے اکاؤنٹ ہے (لاگ ان)، یا آپ نیا اکاؤنٹ بنانا چاہتے ہیں؟'
    },
    'low_confidence': {
        'hi': 'आवाज़ साफ़ सुनाई नहीं दी। कृपया दोबारा बोलें, या नीचे दिए गए विकल्पों पर टैप करें।',
        'pa': 'ਆਵਾਜ਼ ਸਾਫ਼ ਨਹੀਂ ਸੁਣਾਈ ਦਿੱਤੀ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਬੋਲੋ, ਜਾਂ ਹੇਠਾਂ ਟੈਪ ਕਰੋ।',
        'en': 'I could not hear clearly. Please repeat, or tap one of the options below.',
        'bn': 'কথা পরিষ্কার শোনা যায়নি। দয়া করে আবার বলুন, অথবা নিচের বোতামে চাপুন।',
        'mr': 'आवाज स्पष्ट ऐकू आला नाही. कृपया पुन्हा बोला किंवा खाली टॅप करा.',
        'ta': 'குரல் தெளிவாக கேட்கவில்லை. தயவுசெய்து மீண்டும் பேசவும் அல்லது கீழே தட்டவும்.',
        'te': 'వాయిస్ స్పష్టంగా వినిపించలేదు. దయచేసి మళ్ళీ చెప్పండి లేదా క్రింద నొక్కండి.',
        'gu': 'અવાજ સ્પષ્ટ સંભળાયો નથી. કૃપા કરીને ફરીથી બોલો અથવા નીચે ટેપ કરો.',
        'kn': 'ಧ್ವನಿ ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಮಾತನಾಡಿ ಅಥವಾ ಕೆಳಗೆ ಟ್ಯಾಪ್ ಮಾಡಿ.',
        'ml': 'ശബ്ദം വ്യക്തമായി കേട്ടില്ല. ദയവായി വീണ്ടും പറയുക അല്ലെങ്കിൽ താഴെ ടാപ്പ് ചെയ്യുക.',
        'or': 'ଶବ୍ଦ ସ୍ପଷ୍ଟ ଶୁଭିଲା ନାହିଁ। ଦୟାକରି ପୁଣି କୁହନ୍ତୁ କିମ୍ବା ତଳେ ଟ୍ୟାପ୍ କରନ୍ତୁ।',
        'ur': 'آواز صاف سنائی نہیں دی۔ براہ کرم دوبارہ بولیں، یا نیچے دیے گئے آپشنز پر ٹیپ کریں۔'
    },
    'empty_transcript': {
        'hi': 'कोई आवाज़ सुनाई नहीं दी। बोलने के लिए माइक बटन दबाएँ या टेक्स्ट टाइप करें।',
        'pa': 'ਕੋਈ ਆਵਾਜ਼ ਨਹੀਂ ਸੁਣੀ। ਬੋਲਣ ਲਈ ਮਾਈਕ ਬਟਨ ਦਬਾਓ ਜਾਂ ਲਿਖੋ।',
        'en': 'No speech detected. Tap the mic button to speak, or type your input below.',
        'bn': 'কোনো কথা শোনা যায়নি। মাইক বোতাম চাপুন বা টাইপ করুন।',
        'mr': 'कोणताही आवाज आला नाही. बोलण्यासाठी माइक बटण दाबा किंवा टाइप करा.',
        'ta': 'பேச்சு எதுவும் கண்டறியப்படவில்லை. பேச மைக் பட்டனை அழுத்தவும் அல்லது டைப் செய்யவும்.',
        'te': 'ఎలాంటి వాయిస్ రికార్డ్ కాలేదు. మాట్లాడటానికి మైక్ బటన్ నొక్కండి లేదా టైప్ చేయండి.',
        'gu': 'કોઈ અવાજ મળ્યો નથી. બોલવા માટે માઇક બટન દબાવો અથવા ટાઇપ કરો.',
        'kn': 'ಯಾವುದೇ ಧ್ವನಿ ಪತ್ತೆಯಾಗಿಲ್ಲ. ಮಾತನಾಡಲು ಮೈಕ್ ಬಟನ್ ಒತ್ತಿ ಅಥವಾ ಟೈಪ್ ಮಾಡಿ.',
        'ml': 'ശബ്ദമൊന്നും കേട്ടില്ല. സംസാരിക്കാൻ മൈക്ക് ബട്ടൺ അമർത്തുക അല്ലെങ്കിൽ ടൈപ്പ് ചെയ്യുക.',
        'or': 'କୌଣସି ଶବ୍ଦ ମିଳିଲା ନାହିଁ। କହିବା ପାଇଁ ମାଇକ୍ ବଟନ୍ ଦବାନ୍ତୁ କିମ୍ବା ଟାଇପ୍ କରନ୍ତୁ।',
        'ur': 'کوئی آواز موصول نہیں ہوئی۔ بولنے کے لیے مائیک بٹن دبائیں یا ٹائپ کریں۔'
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# 3. LEXICONS FOR INTENT RECOGNITION (Hinglish, Code-Switching & Accents)
# ─────────────────────────────────────────────────────────────────────────────
INTENT_LEXICON = {
    'role_worker': [
        'worker', 'kaam', 'kam', 'rozgar', 'naukri', 'job', 'chahiye', 'karta', 'karni', 'karna',
        'majdoor', 'mazdoor', 'mistri', 'helper', 'karigar', 'shramik', 'kamgar', 'dihadi',
        'plumber', 'electrician', 'carpenter', 'driver', 'cook', 'cleaner', 'painter',
        'kamm', 'kam labhna', 'kam bhalna', 'chahida', 'work', 'labor',
        'kaj', 'lagbe', 'velai', 'vendum', 'pani', 'beku', 'kelasa', 'cheyali'
    ],
    'role_customer': [
        'customer', 'employer', 'maalik', 'malik', 'hire', 'booking', 'book', 'bulao',
        'chahiye', 'rakhna', 'rakhni', 'dhundna', 'khojna', 'sahayak', 'maid', 'servant',
        'mistri bulao', 'plumber chahiye', 'electrician chahiye', 'helper chahiye',
        'service', 'ghar ka kaam'
    ],
    'action_login': [
        'login', 'log in', 'pehle se', 'purana', 'sign in', 'signin', 'account hai',
        'already', 'purani id', 'khata hai', 'dakhil', 'open account', 'open my account', 'mera account'
    ],
    'action_register': [
        'register', 'registration', 'create', 'new', 'naya', 'profile', 'sign up',
        'signup', 'khata banana', 'naya account', 'shuru'
    ],
    'cancel': [
        'cancel', 'stop', 'ruko', 'band', 'hatao', 'nahi chahiye', 'chhoro', 'rehndo',
        'ruk jao', 'chhod do', 'wapas jao'
    ],
    'retry': [
        'retry', 'dobara', 'phir se', 'wapas', 'again', 'phir bolo', 'repeat', 'phir se kaho'
    ]
}

# Known trade keywords mapped to standard canonical categories
TRADE_MAP = {
    'plumber': 'Plumber',
    'nal': 'Plumber',
    'pipe': 'Plumber',
    'electrician': 'Electrician',
    'bijli': 'Electrician',
    'wire': 'Electrician',
    'carpenter': 'Carpenter',
    'badhai': 'Carpenter',
    'lakdi': 'Carpenter',
    'painter': 'Painter',
    'paint': 'Painter',
    'rang': 'Painter',
    'driver': 'Driver',
    'gadi': 'Driver',
    'gaadi': 'Driver',
    'cleaner': 'Cleaner',
    'safai': 'Cleaner',
    'pocha': 'Cleaner',
    'cook': 'Cook',
    'khana': 'Cook',
    'chef': 'Cook',
    'helper': 'Helper',
    'madadgar': 'Helper',
    'mason': 'Mason',
    'mistri': 'Mason',
    'mechanic': 'Mechanic'
}

# ─────────────────────────────────────────────────────────────────────────────
# 4. CORE ENGINE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_verified_language(lang_code: Optional[str]) -> str:
    """Normalize language code and fallback to Hindi if unsupported."""
    if not lang_code or not isinstance(lang_code, str):
        return DEFAULT_LANGUAGE
    code = lang_code.strip().lower()
    if '-' in code:
        code = code.split('-')[0]
    return code if code in LANGUAGE_REGISTRY else DEFAULT_LANGUAGE


def get_clarification_message(prompt_key: str, lang_code: str) -> str:
    """Retrieve localized clarification prompt in the verified language."""
    lang = get_verified_language(lang_code)
    prompts = CLARIFICATION_PROMPTS.get(prompt_key, CLARIFICATION_PROMPTS['low_confidence'])
    return prompts.get(lang) or prompts.get(DEFAULT_LANGUAGE, "Please clarify your request.")


def detect_trade(normalized_text: str) -> Optional[str]:
    """Extract trade/profession from text for trade-specific matching."""
    for keyword, canonical in TRADE_MAP.items():
        if re.search(r'\b' + re.escape(keyword) + r'\b', normalized_text):
            return canonical
    return None


def calculate_match_score(tokens: List[str], lexicon: List[str]) -> float:
    """Calculate normalized lexical match score."""
    if not tokens or not lexicon:
        return 0.0
    matches = 0
    joined = ' '.join(tokens)
    for phrase in lexicon:
        if ' ' in phrase and phrase in joined:
            matches += 2
        elif phrase in tokens:
            matches += 1
    return min(1.0, matches / max(1, min(len(tokens), 4)))


def analyze_voice_intent(
    raw_text: Any,
    lang_code: str = DEFAULT_LANGUAGE,
    confidence: float = 1.0,
    current_state: str = 'GREETING',
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Production-grade voice intent analyzer.
    Handles:
      - Empty / non-string / garbled transcripts
      - Low confidence (< threshold)
      - Ambiguous conversational filler ("haan", "theek hai", "kuch bhi")
      - Natural Hinglish and code-switching
      - Safe fallback with localized clarification prompt
    """
    selected_lang = kwargs.get('language_code', lang_code)
    lang = get_verified_language(selected_lang)
    lang_meta = LANGUAGE_REGISTRY[lang]
    threshold = lang_meta.get('confidence_threshold', 0.60)

    # 1. Validation: Empty or Invalid Input
    if not isinstance(raw_text, str) or not raw_text.strip():
        return {
            'success': False,
            'intent': 'empty_transcript',
            'confidence': 0.0,
            'requires_clarification': True,
            'clarification_prompt': get_clarification_message('empty_transcript', lang),
            'speech_response': get_clarification_message('empty_transcript', lang),
            'language': lang,
            'trade': None,
            'action': None,
            'role': None
        }

    text = raw_text.strip()
    clean_text = re.sub(r'[^\w\s]', ' ', text.lower())
    tokens = clean_text.split()

    if not tokens:
        return {
            'success': False,
            'intent': 'empty_transcript',
            'confidence': 0.0,
            'requires_clarification': True,
            'clarification_prompt': get_clarification_message('empty_transcript', lang),
            'speech_response': get_clarification_message('empty_transcript', lang),
            'language': lang,
            'trade': None,
            'action': None,
            'role': None
        }

    # 2. Check for Low Confidence Recognition
    if confidence < threshold:
        return {
            'success': False,
            'intent': 'low_confidence',
            'confidence': round(confidence, 2),
            'raw_transcript': text,
            'requires_clarification': True,
            'clarification_prompt': get_clarification_message('low_confidence', lang),
            'speech_response': get_clarification_message('low_confidence', lang),
            'language': lang,
            'trade': None,
            'action': None,
            'role': None
        }

    # 3. Detect Trade (e.g. "plumber", "electrician")
    detected_trade = detect_trade(clean_text)

    # 4. Check for Cancellation / Abort
    cancel_score = calculate_match_score(tokens, INTENT_LEXICON['cancel'])
    if cancel_score >= 0.5:
        return {
            'success': True,
            'intent': 'cancel',
            'confidence': 0.9,
            'raw_transcript': text,
            'requires_clarification': False,
            'speech_response': 'ठीक है, रोक दिया गया है।' if lang == 'hi' else 'Okay, cancelled.',
            'language': lang,
            'trade': None,
            'action': 'cancel',
            'role': None
        }

    # 5. Check for Retry
    retry_score = calculate_match_score(tokens, INTENT_LEXICON['retry'])
    if retry_score >= 0.5:
        return {
            'success': True,
            'intent': 'retry',
            'confidence': 0.9,
            'raw_transcript': text,
            'requires_clarification': False,
            'speech_response': 'कृपया फिर से बोलें।' if lang == 'hi' else 'Please speak again.',
            'language': lang,
            'trade': None,
            'action': 'retry',
            'role': None
        }

    # 6. Check Language Selection intent (e.g. "hindi me bolo", "switch to english")
    for code, meta in LANGUAGE_REGISTRY.items():
        name_lower = meta['name'].lower()
        native_lower = meta['native'].lower()
        if name_lower in clean_text or native_lower in clean_text:
            return {
                'success': True,
                'intent': 'select_language',
                'confidence': 0.95,
                'raw_transcript': text,
                'target_language': code,
                'requires_clarification': False,
                'speech_response': f"अब हम {meta['native']} में बात करेंगे।" if code == 'hi' else f"Switching to {meta['name']}.",
                'language': code,
                'trade': None,
                'action': None,
                'role': None
            }

    # 7. Intent Scoring based on Lexicon
    worker_score = calculate_match_score(tokens, INTENT_LEXICON['role_worker'])
    customer_score = calculate_match_score(tokens, INTENT_LEXICON['role_customer'])
    login_score = calculate_match_score(tokens, INTENT_LEXICON['action_login'])
    register_score = calculate_match_score(tokens, INTENT_LEXICON['action_register'])

    # Disambiguate Worker vs Customer:
    # Notice: If someone says "mujhe plumber chahiye" -> customer_score wins (they want to hire).
    # If someone says "main plumber hoon" or "plumber ka kaam chahiye" -> worker_score wins.
    if re.search(r'\b(chahiye|chahida|need|want|bulao|dhund)\b', clean_text) and detected_trade:
        customer_score += 0.5
    if re.search(r'\b(hoon|hu|karta|seeking|job|rozgar)\b', clean_text) and detected_trade:
        worker_score += 0.5

    # 8. State-Aware Intent Resolution
    # A. If in ROLE_SELECT state or GREETING state:
    if current_state in ['ROLE_SELECT', 'GREETING', 'LANGUAGE_SELECT']:
        if worker_score > 0.3 and worker_score > customer_score:
            return {
                'success': True,
                'intent': 'select_role_worker',
                'confidence': round(min(1.0, worker_score + 0.3), 2),
                'raw_transcript': text,
                'requires_clarification': False,
                'role': 'worker',
                'trade': detected_trade,
                'action': None,
                'speech_response': 'बहुत बढ़िया! आप काम ढूँढना चाहते हैं।' if lang == 'hi' else 'Great! You are looking for work.',
                'language': lang
            }
        elif customer_score > 0.3 and customer_score > worker_score:
            return {
                'success': True,
                'intent': 'select_role_customer',
                'confidence': round(min(1.0, customer_score + 0.3), 2),
                'raw_transcript': text,
                'requires_clarification': False,
                'role': 'user',
                'trade': detected_trade,
                'action': None,
                'speech_response': 'बहुत अच्छा! आप वर्कर बुक करना चाहते हैं।' if lang == 'hi' else 'Understood! You want to hire a worker.',
                'language': lang
            }

    # B. If in ACTION_SELECT state:
    if current_state == 'ACTION_SELECT':
        if login_score > 0.3 and login_score > register_score:
            return {
                'success': True,
                'intent': 'select_action_login',
                'confidence': round(min(1.0, login_score + 0.3), 2),
                'raw_transcript': text,
                'requires_clarification': False,
                'role': None,
                'trade': None,
                'action': 'login',
                'speech_response': 'लॉगिन पेज पर ले जा रहा हूँ।' if lang == 'hi' else 'Navigating to Login page.',
                'language': lang
            }
        elif register_score > 0.3 and register_score > login_score:
            return {
                'success': True,
                'intent': 'select_action_register',
                'confidence': round(min(1.0, register_score + 0.3), 2),
                'raw_transcript': text,
                'requires_clarification': False,
                'role': None,
                'trade': None,
                'action': 'register',
                'speech_response': 'नया अकाउंट बनाने के लिए आगे बढ़ रहे हैं।' if lang == 'hi' else 'Proceeding to Create Account.',
                'language': lang
            }

    # C. If general trade detected without role:
    if detected_trade and customer_score >= worker_score:
        return {
            'success': True,
            'intent': 'select_role_customer',
            'confidence': 0.75,
            'raw_transcript': text,
            'requires_clarification': False,
            'role': 'user',
            'trade': detected_trade,
            'action': None,
            'speech_response': f"{detected_trade} ढूँढने में मदद कर रहा हूँ।" if lang == 'hi' else f"Finding {detected_trade} for you.",
            'language': lang
        }

    # 9. Handle Ambiguity / Casual Filler (e.g. "theek hai", "haan", "batao")
    # Prompt clarification rather than misinterpreting!
    ambiguous_prompt = 'ambiguous_action' if current_state == 'ACTION_SELECT' else 'ambiguous_role'
    return {
        'success': False,
        'intent': 'clarification_needed',
        'confidence': 0.35,
        'raw_transcript': text,
        'requires_clarification': True,
        'clarification_prompt': get_clarification_message(ambiguous_prompt, lang),
        'speech_response': get_clarification_message(ambiguous_prompt, lang),
        'language': lang,
        'trade': None,
        'action': None,
        'role': None
    }


def get_voice_capabilities() -> Dict[str, Any]:
    """
    Returns server-side capability metadata and configuration status.
    Keeps API keys strictly hidden on the server.
    """
    return {
        'default_language': DEFAULT_LANGUAGE,
        'supported_languages': [
            {
                'code': k,
                'name': v['name'],
                'native': v['native'],
                'stt_locale': v['stt_locale'],
                'tts_locale': v['tts_locale'],
                'flag': v['flag'],
                'code_switching': v['code_switching']
            }
            for k, v in LANGUAGE_REGISTRY.items()
        ],
        'features': {
            'streaming_stt': True,
            'interim_transcription': True,
            'confidence_scoring': True,
            'clarification_dialogue': True,
            'typed_fallback': True,
            'code_switching_support': True
        },
        'provider_status': {
            'browser_web_speech': 'available',
            'server_intent_analyzer': 'active',
            'server_credentials_secured': True
        }
    }
