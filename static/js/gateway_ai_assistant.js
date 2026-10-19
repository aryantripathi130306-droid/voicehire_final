/**
 * VoiceHire — Unified Persistent Voice Assistant & Onboarding Shell
 * ═══════════════════════════════════════════════════════════════════════════
 * Phase 14.1 Production Implementation:
 *  - Persistent conversation & onboarding state across navigation (Bug 1).
 *  - Worker profile creation & completion via backend APIs (Bug 2).
 *  - Hands-free auto-listening after speech + manual voice mode (Bug 3).
 *  - 12 Indian languages defaulting to Hindi (hi-IN).
 *  - Zero password / OTP collection over voice (Rule 8 Compliance).
 *  - Idempotent backend synchronization & authoritative verification.
 * ═══════════════════════════════════════════════════════════════════════════
 */

(function () {
  'use strict';

  // Guard against duplicate execution
  if (window.__VH_ASSISTANT_INITIALIZED__) return;
  window.__VH_ASSISTANT_INITIALIZED__ = true;
  window.__VH_AI_INIT__ = true; // Signals older legacy scripts to stand down

  /* ─────────────────────────────────────────────────────────────────────────
     1. ASSISTANT STATE MODEL
  ───────────────────────────────────────────────────────────────────────── */
  const States = {
    UNINITIALIZED:                 'UNINITIALIZED',
    AUTOPLAY_PROMPT:               'AUTOPLAY_PROMPT',
    GREETING:                      'GREETING',
    LANGUAGE_SELECT:               'LANGUAGE_SELECT',
    ROLE_SELECT:                   'ROLE_SELECT',
    ACTION_SELECT:                 'ACTION_SELECT',
    AUTH_IN_PROGRESS:              'AUTH_IN_PROGRESS',
    AUTHENTICATED:                 'AUTHENTICATED',
    CHECKING_PROFILE:              'CHECKING_PROFILE',
    COLLECTING_PROFILE_FIELDS:     'COLLECTING_PROFILE_FIELDS',
    SAVING_PROFILE:                'SAVING_PROFILE',
    AWAITING_PROFILE_CONFIRMATION: 'AWAITING_PROFILE_CONFIRMATION',
    PROFILE_COMPLETE:              'PROFILE_COMPLETE',
    DASHBOARD_GUIDANCE:            'DASHBOARD_GUIDANCE',
    NAVIGATING:                    'NAVIGATING',
    MANUAL_MODE:                   'MANUAL_MODE',
    RECOVERABLE_ERROR:             'RECOVERABLE_ERROR',
    IDLE:                          'IDLE'
  };

  /* ─────────────────────────────────────────────────────────────────────────
     2. VERIFIED LANGUAGE REGISTRY
  ───────────────────────────────────────────────────────────────────────── */
  const LANGUAGES = {
    hi: { code: 'hi', name: 'Hindi',     native: 'हिंदी',      speechCode: 'hi-IN', flag: '🇮🇳' },
    pa: { code: 'pa', name: 'Punjabi',   native: 'ਪੰਜਾਬੀ',    speechCode: 'pa-IN', flag: '🇮🇳' },
    en: { code: 'en', name: 'English',   native: 'English',    speechCode: 'en-IN', flag: '🇬🇧' },
    bn: { code: 'bn', name: 'Bengali',   native: 'বাংলা',      speechCode: 'bn-IN', flag: '🇧🇩' },
    mr: { code: 'mr', name: 'Marathi',   native: 'मराठी',      speechCode: 'mr-IN', flag: '🇮🇳' },
    ta: { code: 'ta', name: 'Tamil',     native: 'தமிழ்',      speechCode: 'ta-IN', flag: '🌟' },
    te: { code: 'te', name: 'Telugu',    native: 'తెలుగు',     speechCode: 'te-IN', flag: '🌟' },
    gu: { code: 'gu', name: 'Gujarati',  native: 'ગુજરાતી',   speechCode: 'gu-IN', flag: '🇮🇳' },
    kn: { code: 'kn', name: 'Kannada',   native: 'ಕನ್ನಡ',     speechCode: 'kn-IN', flag: '🌟' },
    ml: { code: 'ml', name: 'Malayalam', native: 'മലയാളം',     speechCode: 'ml-IN', flag: '🌟' },
    or: { code: 'or', name: 'Odia',      native: 'ଓଡ଼ିଆ',      speechCode: 'or-IN', flag: '🌟' },
    ur: { code: 'ur', name: 'Urdu',      native: 'اردو',       speechCode: 'ur-IN', flag: '🇮🇳' }
  };

  /* ─────────────────────────────────────────────────────────────────────────
     3. MULTILINGUAL DIALOGUE LIBRARY
  ───────────────────────────────────────────────────────────────────────── */
  const DIALOGUES = {
    greeting: {
      hi: "नमस्ते! मैं VoiceHire का आवाज़ सहायक हूँ। मैं आपको काम ढूँढने या वर्कर बुक करने में मदद कर सकता हूँ।",
      pa: "ਸਤਿ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ VoiceHire ਦਾ ਆਵਾਜ਼ ਸਹਾਇਕ ਹਾਂ। ਮੈਂ ਤੁਹਾਨੂੰ ਕੰਮ ਲੱਭਣ ਜਾਂ ਕਾਰੀਗਰ ਬੁੱਕ ਕਰਨ ਵਿੱਚ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ।",
      en: "Hello! I am your VoiceHire voice assistant. I can help you find local work or book skilled workers.",
      bn: "নমস্কার! আমি VoiceHire-এর ভয়েস সহকারী। আমি আপনাকে কাজ খুঁজতে বা কর্মী বুক করতে সাহায্য করতে পারি।",
      mr: "नमस्कार! मी VoiceHire चा आवाज सहाय्यक आहे. मी तुम्हाला काम शोधण्यात किंवा कारागीर बुक करण्यात मदत करू शकतो.",
      ta: "வணக்கம்! நான் VoiceHire-ன் குரல் உதவியாளர். வேலை தேட அல்லது தொழிலாளர்களை பதிவு செய்ய நான் உதவுவேன்.",
      te: "నమస్కారం! నేను VoiceHire వాయిస్ అసిస్టెంట్. పని వెతకడానికి లేదా వర్కర్‌ని బుక్ చేసుకోవడానికి నేను సహాయం చేస్తాను.",
      gu: "નમસ્તે! હું VoiceHire નો અવાજ સહાયક છું. હું તમને કામ શોધવામાં અથવા વર્કર બુક કરવામાં મદદ કરી શકું છું.",
      kn: "ನಮಸ್ಕಾರ! ನಾನು VoiceHire ಧ್ವನಿ ಸಹಾಯಕ. ಕೆಲಸ ಹುಡುಕಲು ಅಥವಾ ಕೆಲಸಗಾರರನ್ನು ಬುಕ್ ಮಾಡಲು ನಾನು ಸಹಾಯ ಮಾಡುತ್ತೇನೆ.",
      ml: "നമസ്കാരം! ഞാൻ VoiceHire-ന്റെ വോയ്‌സ് അസിസ്റ്റന്റാണ്. ജോലി കണ്ടെത്താനോ തൊഴിലാളികളെ ബുക്ക് ചെയ്യാനോ സഹായിക്കാം.",
      or: "ନମସ୍କାର! ମୁଁ VoiceHire ର ଭଏସ୍ ସହାୟକ। ମୁଁ ଆପଣଙ୍କୁ କାମ ଖୋଜିବା କିମ୍ବା ଶ୍ରମିକ ବୁକ୍ କରିବାରେ ସାହାଯ୍ୟ କରିପାରିବି।",
      ur: "سلام! میں VoiceHire کا آواز معاون ہوں۔ میں آپ کو کام تلاش کرنے یا ورکر بک کرنے میں مدد کر سکتا ہوں۔"
    },
    askLanguage: {
      hi: "आप किस भाषा में बात करना चाहते हैं? अपनी पसंद की भाषा चुनें।",
      pa: "ਤੁਸੀਂ ਕਿਸ ਭਾਸ਼ਾ ਵਿੱਚ ਗੱਲਬਾਤ ਕਰਨਾ ਚਾਹੁੰਦੇ ਹੋ? ਆਪਣੀ ਭਾਸ਼ਾ ਚੁਣੋ।",
      en: "Which language do you prefer? Please choose below.",
      bn: "আপনি কোন ভাষায় কথা বলতে চান? আপনার ভাষা বেছে নিন।",
      mr: "तुम्हाला कोणत्या भाषेत बोलायला आवडेल? कृपया तुमची भाषा निवडा.",
      ta: "நீங்கள் எந்த மொழியில் பேச விரும்புகிறீர்கள்? உங்கள் மொழியைத் தேர்ந்தெடுக்கவும்.",
      te: "మీరు ఏ భాషలో మాట్లాడాలనుకుంటున్నారు? దయచేసి ఎంచుకోండి.",
      gu: "તમે કઈ ભાષામાં વાત કરવા માંગો છો? તમારી ભાષા પસંદ કરો.",
      kn: "ನೀವು ಯಾವ ಭಾಷೆಯಲ್ಲಿ ಮಾತನಾಡಲು ಬಯಸುತ್ತೀರಿ? ದಯವಿಟ್ಟು ಆಯ್ಕೆಮಾಡಿ.",
      ml: "ഏത് ഭാഷയിലാണ് സംസാരിക്കാൻ ആഗ്രഹിക്കുന്നത്? ദയവായി തിരഞ്ഞെടുക്കുക.",
      or: "ଆପଣ କେଉଁ ଭାଷାରେ କଥା ହେବାକୁ ଚାହାଁନ୍ତି? ଆପଣଙ୍କର ଭାଷା ବାଛନ୍ତୁ।",
      ur: "آپ کس زبان میں بات کرنا چاہتے ہیں؟ براہ کرم اپنی زبان منتخب کریں۔"
    },
    langConfirmed: {
      hi: "बहुत अच्छा! अब हम हिंदी में बात करेंगे।",
      pa: "ਬਹੁਤ ਵਧੀਆ! ਹੁਣ ਅਸੀਂ ਪੰਜਾਬੀ ਵਿੱਚ ਗੱਲਬਾਤ ਕਰਾਂਗੇ।",
      en: "Great! We will continue in English.",
      bn: "খুব ভালো! এখন আমরা বাংলায় কথা বলব।",
      mr: "छान! आता आपण मराठीत बोलूया.",
      ta: "மிக நன்று! இப்போது தமிழில் தொடருவோம்.",
      te: "చాలా బాగుంది! ఇప్పుడు మనం తెలుగులో మాట్లాడదాం.",
      gu: "સરસ! હવે આપણે ગુજરાતીમાં વાત કરીશું.",
      kn: "ಉತ್ತಮ! ಈಗ ನಾವು ಕನ್ನಡದಲ್ಲಿ ಮಾತನಾಡೋಣ.",
      ml: "വളരെ നല്ലത്! ഇനി മലയാളത്തിൽ സംസാരിക്കാം.",
      or: "ବହୁତ ଭଲ! ଏବେ ଆମେ ଓଡ଼ିଆରେ କଥାବାର୍ତ୍ତା କରିବା।",
      ur: "بہت اچھا! اب ہم اردو میں بات کریں گے۔"
    },
    askRole: {
      hi: "क्या आपको काम चाहिए या आप किसी काम के लिए वर्कर को रखना चाहते हैं?",
      pa: "ਕੀ ਤੁਹਾਨੂੰ ਕੰਮ ਚਾਹੀਦਾ ਹੈ ਜਾਂ ਤੁਸੀਂ ਕਿਸੇ ਕੰਮ ਲਈ ਵਰਕਰ ਨੂੰ ਹਾਇਰ ਕਰਨਾ ਚਾਹੁੰਦੇ ਹੋ?",
      en: "Are you looking for work, or do you want to hire a worker?",
      bn: "আপনি কি কাজ খুঁজছেন, নাকি কাউকে কাজে নিয়োগ করতে চান?",
      mr: "तुम्हाला काम हवे आहे की कामासाठी कामगार ठेवायचा आहे?",
      ta: "நீங்கள் வேலை தேடுகிறீர்களா, அல்லது ஒரு தொழிலாளியை வேலைக்கு அமர்த்த விரும்புகிறீர்களா?",
      te: "మీరు పని కోసం చూస్తున్నారా, లేదా వర్కర్‌ని పనిలో పెట్టుకోవాలనుకుంటున్నారా?",
      gu: "શું તમે કામ શોધી રહ્યા છો, કે કોઈ વર્કરને કામે રાખવા માંગો છો?",
      kn: "ನೀವು ಕೆಲಸ ಹುಡುಕುತ್ತಿದ್ದೀರಾ ಅಥವಾ ಕೆಲಸಗಾರರನ್ನು ನೇಮಿಸಿಕೊಳ್ಳಲು ಬಯಸುವಿರಾ?",
      ml: "നിങ്ങൾ ജോലി അന്വേഷിക്കുകയാണോ, അതോ തൊഴിലാളിയെ നിയമിക്കാൻ ആഗ്രഹിക്കുന്നുണ്ടോ?",
      or: "ଆପଣ କାମ ଖୋଜୁଛନ୍ତି କିମ୍ବା କାମ ପାଇଁ ଶ୍ରମିକ ନିୟୋଜିତ କରିବାକୁ ଚାହାଁନ୍ତି?",
      ur: "کیا آپ کام تلاش کر رہے ہیں، یا کسی کام کے لیے ورکر رکھنا چاہتے ہیں؟"
    },
    roleWorker: {
      hi: "मुझे काम चाहिए (Worker)",
      pa: "ਮੈਨੂੰ ਕੰਮ ਚਾਹੀਦਾ ਹੈ (Worker)",
      en: "I Want Work (Worker)",
      bn: "আমি কাজ চাই (Worker)",
      mr: "मला काम हवे आहे (Worker)",
      ta: "எனக்கு வேலை வேண்டும் (Worker)",
      te: "నాకు పని కావాలి (Worker)",
      gu: "મને કામ જોઈએ છે (Worker)",
      kn: "ನನಗೆ ಕೆಲಸ ಬೇಕು (Worker)",
      ml: "എനിക്ക് ജോലി വേണം (Worker)",
      or: "ମୋତେ କାମ ଦରକାର (Worker)",
      ur: "مجھے کام چاہیے (Worker)"
    },
    roleWorkerSub: {
      hi: "लोकल नौकरियाँ व रोज़गार खोजें",
      pa: "ਸਥਾਨਕ ਨੌਕਰੀਆਂ ਤੇ ਰੋਜ਼ਗਾਰ ਲੱਭੋ",
      en: "Discover local job opportunities",
      bn: "স্থানীয় কাজের সুযোগ খুঁজুন",
      mr: "स्थानिक रोजगाराच्या संधी शोधा",
      ta: "உள்ளூர் வேலை வாய்ப்புகளைக் கண்டறியுங்கள்",
      te: "స్థానిక ఉద్యోగ అవకాశాలను కనుగొనండి",
      gu: "સ્થાનિક નોકરીઓ અને રોજગાર શોધો",
      kn: "ಸ್ಥಳೀಯ ಉದ್ಯೋಗಾವಕಾಶಗಳನ್ನು ಹುಡುಕಿ",
      ml: "പ്രാദേശിക തൊഴിലവസരങ്ങൾ കണ്ടെത്തുക",
      or: "ସ୍ଥାନୀୟ ରୋଜଗାର ସୁଯୋଗ ଖୋଜନ୍ତୁ",
      ur: "مقامی ملازمتوں کے مواقع تلاش کریں"
    },
    roleCustomer: {
      hi: "मुझे वर्कर चाहिए (Customer)",
      pa: "ਮੈਨੂੰ ਵਰਕਰ ਚਾਹੀਦਾ ਹੈ (Customer)",
      en: "I Want to Hire (Customer)",
      bn: "আমার কর্মী দরকার (Customer)",
      mr: "मला कामगार हवा आहे (Customer)",
      ta: "எனக்கு தொழிலாளி தேவை (Customer)",
      te: "నాకు వర్కర్ కావాలి (Customer)",
      gu: "મને વર્કર જોઈએ છે (Customer)",
      kn: "ನನಗೆ ಕೆಲಸಗಾರರು ಬೇಕು (Customer)",
      ml: "എനിക്ക് തൊഴിലാളികളെ വേണം (Customer)",
      or: "ମୋତେ ଶ୍ରମିକ ଦରକାର (Customer)",
      ur: "مجھے ورکر چاہیے (Customer)"
    },
    roleCustomerSub: {
      hi: "प्लंबर, इलेक्ट्रीशियन, हेल्पर बुक करें",
      pa: "ਪਲੰਬਰ, ਇਲੈਕਟ੍ਰੀਸ਼ੀਅਨ, ਹੈਲਪਰ ਬੁੱਕ ਕਰੋ",
      en: "Book verified plumbers, helpers & pros",
      bn: "প্লাম্বার, ইলেকট্রিশিয়ান ও হেল্পার বুক করুন",
      mr: "प्लंबर, इलेक्ट्रिशियन, मदतनीस बुक करा",
      ta: "பிளம்பர், எலக்ட்ரீஷியன், உதவியாளர்களை பதிவு செய்க",
      te: "ప్లంబర్, ఎలక్ట్రీషియన్, హెల్పర్లను బుక్ చేయండి",
      gu: "પ્લમ્બર, ઇલેક્ટ્રિશિયન, હેલ્પર બુક કરો",
      kn: "ಪ್ಲಂಬರ್, ಎಲೆಕ್ಟ್ರಿಷಿಯನ್, ಸಹಾಯಕವನ್ನು ಬುಕ್ ಮಾಡಿ",
      ml: "പ്ലംബർ, ഇലക്ട്രീഷ്യൻ എന്നിവരെ ബുക്ക് ചെയ്യുക",
      or: "ପ୍ଲମ୍ବର, ଇଲେକ୍ଟ୍ରିସିଆନ୍, ହେଲ୍ପର୍ ବୁକ୍ କରନ୍ତୁ",
      ur: "پلمبر، الیکٹریشن اور ہیلپر بک کریں"
    },
    askAction: {
      hi: "क्या आपका पहले से खाता है या आप नया खाता बनाना चाहते हैं?",
      pa: "ਕੀ ਤੁਹਾਡਾ ਪਹਿਲਾਂ ਤੋਂ ਖਾਤਾ ਹੈ ਜਾਂ ਤੁਸੀਂ ਨਵਾਂ ਖਾਤਾ ਬਣਾਉਣਾ ਚਾਹੁੰਦੇ ਹੋ?",
      en: "Do you already have an account, or would you like to create a new one?",
      bn: "আপনার কি আগে থেকেই অ্যাকাউন্ট আছে, নাকি নতুন অ্যাকাউন্ট খুলবেন?",
      mr: "तुमचे आधीच खाते आहे की तुम्हाला नवीन खाते तयार करायचे आहे?",
      ta: "உங்களுக்கு ஏற்கனவே கணக்கு உள்ளதா அல்லது புதிய கணக்கு தொடங்க வேண்டுமா?",
      te: "మీకు ఇప్పటికే ఖాతా ఉందా లేక కొత్త ఖాతా సృష్టించాలనుకుంటున్నారా?",
      gu: "શું તમારી પાસે પહેલેથી ખાતું છે કે નવું ખાતું બનાવવા માંગો છો?",
      kn: "ನಿಮ್ಮ ಬಳಿ ಈಗಾಗಲೇ ಖಾತೆ ಇದೆಯೇ ಅಥವಾ ಹೊಸ ಖಾತೆಯನ್ನು ರಚಿಸಲು ಬಯಸುವಿರಾ?",
      ml: "നിങ്ങൾക്ക് ഇതിനകം അക്കൗണ്ട് ഉണ്ടോ അതോ പുതിയ അക്കൗണ്ട് വേണമോ?",
      or: "ଆପଣଙ୍କର ପୂର୍ବରୁ ଖାତା ଅଛି କି ଆପଣ ନୂଆ ଖାତା ଖୋଲିବାକୁ ଚାହାଁନ୍ତି?",
      ur: "کیا آپ کا پہلے سے اکاؤنٹ ہے یا آپ نیا اکاؤنٹ بنانا چاہتے ہیں؟"
    },
    actionLogin: {
      hi: "लॉग इन करें (Login)",
      pa: "ਲੌਗ ਇਨ ਕਰੋ (Login)",
      en: "Log In",
      bn: "লগ ইন করুন (Login)",
      mr: "लॉग इन करा (Login)",
      ta: "உள்நுழைக (Login)",
      te: "లాగిన్ అవ్వండి (Login)",
      gu: "લૉગ ઇન કરો (Login)",
      kn: "ಲಾಗಿನ್ ಆಗಿ (Login)",
      ml: "ലോഗിൻ ചെയ്യുക (Login)",
      or: "ଲଗ୍ ଇନ୍ କରନ୍ତୁ (Login)",
      ur: "لاگ ان کریں (Login)"
    },
    actionLoginSub: {
      hi: "पहले से खाता मौजूद है",
      pa: "ਪਹਿਲਾਂ ਤੋਂ ਖਾਤਾ ਹੈ",
      en: "Already have an account",
      bn: "আগে থেকেই অ্যাকাউন্ট আছে",
      mr: "आधीच खाते अस्तित्वात आहे",
      ta: "ஏற்கனவே கணக்கு உள்ளது",
      te: "ఇప్పటికే ఖాతా ఉంది",
      gu: "પહેલેથી ખાતું મોજૂદ છે",
      kn: "ಈಗಾಗಲೇ ಖಾತೆ ಇದೆ",
      ml: "ഇതിനകം അക്കൗണ്ട് ഉണ്ട്",
      or: "ପୂର୍ବରୁ ଖାତା ଅଛି",
      ur: "پہلے سے اکاؤنٹ موجود ہے"
    },
    actionRegister: {
      hi: "नया खाता बनाएं (Create Account)",
      pa: "ਨਵਾਂ ਖਾਤਾ ਬਣਾਓ (Create Account)",
      en: "Create Account",
      bn: "নতুন অ্যাকাউন্ট তৈরি করুন",
      mr: "नवीन खाते तयार करा",
      ta: "புதிய கணக்கு தொடங்கு",
      te: "కొత్త ఖాతా సృష్టించండి",
      gu: "નવું ખાતું બનાવો",
      kn: "ಹೊಸ ಖಾತೆ ರಚಿಸಿ",
      ml: "പുതിയ അക്കൗണ്ട് ഉണ്ടാക്കുക",
      or: "ନୂଆ ଖାତା ତିଆରି କରନ୍ତୁ",
      ur: "نیا اکاؤنٹ بنائیں"
    },
    actionRegisterSub: {
      hi: "मुफ़्त प्रोफ़ाइल बनाएं",
      pa: "ਮੁਫ਼ਤ ਪ੍ਰੋਫਾਈਲ ਬਣਾਓ",
      en: "Register for free",
      bn: "বিনামূল্যে প্রোফাইল তৈরি করুন",
      mr: "मोफत प्रोफाईल तयार करा",
      ta: "இலவச சுயவிவரத்தை உருவாக்கவும்",
      te: "ఉచిత ప్రొఫైల్ సృష్టించండి",
      gu: "મફત પ્રોફાઇલ બનાવો",
      kn: "ಉಚಿತ ಪ್ರೊಫೈಲ್ ರಚಿಸಿ",
      ml: "സൗജന്യ പ്രൊഫൈൽ ഉണ്ടാക്കുക",
      or: "ମାଗଣାରେ ପ୍ରୋଫାଇଲ୍ ତିଆରି କରନ୍ତୁ",
      ur: "مفت پروفائل بنائیں"
    },
    navigating: {
      hi: "मैं आपको सही पेज पर ले जा रहा हूँ...",
      pa: "ਤੁਹਾਨੂੰ ਪੇਜ 'ਤੇ ਲਿਜਾਇਆ ਜਾ ਰਿਹਾ ਹੈ...",
      en: "Taking you to the page now...",
      bn: "আপনাকে সংশ্লিষ্ট পেজে নিয়ে যাওয়া হচ্ছে...",
      mr: "मी तुम्हाला योग्य पृष्ठावर घेऊन जात आहे...",
      ta: "உங்களை பக்கத்திற்கு அழைத்துச் செல்கிறேன்...",
      te: "మిమ్మల్ని పేజీకి తీసుకువెళుతున్నాను...",
      gu: "હું તમને પેજ પર લઈ જઈ રહ્યો છું...",
      kn: "ನಿಮ್ಮನ್ನು ಪುಟಕ್ಕೆ ಕರೆದೊಯ್ಯುತ್ತಿದ್ದೇನೆ...",
      ml: "നിങ്ങളെ പേജിലേക്ക് കൊണ്ടുപോകുന്നു...",
      or: "ଆପଣଙ୍କୁ ସଠିକ୍ ପୃଷ୍ଠାକୁ ନିଆଯାଉଛି...",
      ur: "میں آپ کو صفحے پر لے جا رہا ہوں..."
    },
    autoplayBlockedMsg: {
      hi: "आवाज़ सुनने और बात करने के लिए नीचे दिए गए बटन पर टैप करें।",
      pa: "ਆਵਾਜ਼ ਸੁਣਨ ਅਤੇ ਗੱਲ ਕਰਨ ਲਈ ਹੇਠਾਂ ਦਿੱਤੇ ਬਟਨ 'ਤੇ ਟੈਪ ਕਰੋ।",
      en: "Tap the button below to enable the voice assistant audio.",
      bn: "শব্দ শুনতে ও কথা বলতে নিচের বোতামে চাপ দিন।",
      mr: "आवाज ऐकण्यासाठी आणि बोलण्यासाठी खालील बटणावर टॅप करा.",
      ta: "குரலைக் கேட்க கீழே உள்ள பொத்தானைத் தட்டவும்.",
      te: "వాయిస్ వినడానికి క్రింది బటన్‌పై నొక్కండి.",
      gu: "અવાજ સાંભળવા માટે નીચેના બટન પર ટેપ કરો.",
      kn: "ಧ್ವನಿಯನ್ನು ಕೇಳಲು ಕೆಳಗಿನ ಬಟನ್ ಟ್ಯಾಪ್ ಮಾಡಿ.",
      ml: "ശബ്ദം കേൾക്കാൻ താഴെയുള്ള ബട്ടൺ ടാപ്പുചെയ്യുക.",
      or: "ଭଏସ୍ ଶୁଣିବା ପାଇଁ ତଳେ ଥିବା ବଟନ୍ ଟ୍ୟାପ୍ କରନ୍ତୁ।",
      ur: "آواز سننے اور بات کرنے کے لیے نیچے دیئے گئے بٹن پر ٹیپ کریں۔"
    },
    startVoiceBtn: {
      hi: "🔊 आवाज़ सहायक शुरू करें",
      pa: "🔊 ਆਵਾਜ਼ ਸਹਾਇਕ ਸ਼ੁਰੂ ਕਰੋ",
      en: "🔊 Start Voice Assistant",
      bn: "🔊 ভয়েস সহকারী শুরু করুন",
      mr: "🔊 आवाज सहाय्यक सुरू करा",
      ta: "🔊 குரல் உதவியாளரைத் தொடங்கு",
      te: "🔊 వాయిస్ అసిస్టెంట్‌ని ప్రారంభించండి",
      gu: "🔊 અવાજ સહાયક શરૂ કરો",
      kn: "🔊 ಧ್ವನಿ ಸಹಾಯಕವನ್ನು ಪ್ರಾರಂಭಿಸಿ",
      ml: "🔊 വോയ്‌സ് അസിസ്റ്റന്റ് ആരംഭിക്കുക",
      or: "🔊 ଭଏସ୍ ସହାୟକ ଆରମ୍ଭ କରନ୍ତୁ",
      ur: "🔊 آواز معاون شروع کریں"
    },
    micListening: {
      hi: "सुन रहा हूँ... बोलिए",
      pa: "ਸੁਣ ਰਿਹਾ ਹਾਂ... ਬੋਲੋ",
      en: "Listening... please speak",
      bn: "শুনছি... বলুন",
      mr: "ऐकत आहे... बोला",
      ta: "கேட்கிறேன்... பேசுங்கள்",
      te: "వింటున్నాను... మాట్లాడండి",
      gu: "સાંભળી રહ્યો છું... બોલો",
      kn: "ಕೇಳಿಸಿಕೊಳ್ಳುತ್ತಿದ್ದೇನೆ... ಮಾತನಾಡಿ",
      ml: "കേൾക്കുന്നു... സംസാരിക്കൂ",
      or: "ଶୁଣୁଛି... କୁହନ୍ତୁ",
      ur: "سن رہا ہوں... بولیے"
    },
    micDenied: {
      hi: "माइक्रोफ़ोन की अनुमति नहीं मिली। आप नीचे दिए गए बटन पर टैप कर सकते हैं या लिख सकते हैं।",
      pa: "ਮਾਈਕ੍ਰੋਫੋਨ ਦੀ ਇਜਾਜ਼ਤ ਨਹੀਂ ਮਿਲੀ। ਤੁਸੀਂ ਹੇਠਾਂ ਦਿੱਤੇ ਬਟਨਾਂ 'ਤੇ ਟੈਪ ਕਰ ਸਕਦੇ ਹੋ।",
      en: "Microphone permission was not granted. You can tap options below or type.",
      bn: "মাইক্রোফোনের অনুমতি পাওয়া যায়নি। আপনি নিচের অপশনে চাপ দিতে পারেন।",
      mr: "मायक्रोफोनची परवानगी मिळाली नाही. आपण खालील पर्यायांवर टॅप करू शकता.",
      ta: "மைக்ரோஃபோன் அனுமதி கிடைக்கவில்லை. நீங்கள் கீழே உள்ள விருப்பங்களை தேர்வு செய்யலாம்.",
      te: "మైక్రోఫోన్ అనుమతి లభించలేదు. మీరు క్రింది ఎంపికలను ఎంచుకోవచ్చు.",
      gu: "માઇક્રોફોનની મંજૂરી મળી નથી. તમે નીચે આપેલા બટન પર ટેપ કરી શકો છો.",
      kn: "ಮೈಕ್ರೋಫೋನ್ ಅನುಮತಿ ಲಭ್ಯವಾಗಿಲ್ಲ. ನೀವು ಕೆಳಗಿನ ಆಯ್ಕೆಗಳನ್ನು ಬಳಸಬಹುದು.",
      ml: "മൈക്രോഫോൺ അനുമതി ലഭിച്ചില്ല. താഴെയുള്ള ഓപ്ഷനുകൾ ഉപയോഗിക്കുക.",
      or: "ମାଇକ୍ରୋଫୋନ୍ ଅନୁମତି ମିଳିଲା ନାହିଁ। ଆପଣ ତଳେ ଥିବା ବଟନ୍ ବ୍ୟବହାର କରିପାରିବେ।",
      ur: "مائیکروفون کی اجازت نہیں ملی۔ آپ نیچے دیے گئے آپشنز پر ٹیپ کر سکتے ہیں۔"
    },

    // ── Phase 14.1 Worker Profile Dialogues ──────────────────────────────────
    workerProfileGreeting: {
      hi: "आइए मिलकर आपकी वर्कर प्रोफ़ाइल तैयार करते हैं ताकि आपको स्थानीय काम मिलना शुरू हो सके।",
      pa: "ਆਓ ਤੁਹਾਡੀ ਵਰਕਰ ਪ੍ਰੋਫਾਈਲ ਬਣਾਈਏ ਤਾਂ ਜੋ ਤੁਹਾਨੂੰ ਕੰਮ ਮਿਲਣਾ ਸ਼ੁਰੂ ਹੋ ਸਕੇ।",
      en: "Let's set up your worker profile so local customers can hire you.",
      bn: "আসুন আপনার কর্মী প্রোফাইল তৈরি করি যাতে আপনি কাজ পেতে পারেন।",
      mr: "चला तुमची कामगार प्रोफाईल तयार करूया जेणेकरून तुम्हाला काम मिळू शकेल.",
      ta: "உங்களுக்கு வேலை கிடைக்க உங்கள் சுயவிவரத்தை உருவாக்குவோம்.",
      te: "మీకు పని దొరకడానికి మీ వర్కర్ ప్రొఫైల్‌ను సిద్ధం చేద్దాం.",
      gu: "ચાલો તમારી વર્કર પ્રોફાઇલ બનાવીએ જેથી તમને કામ મળવાનું શરૂ થાય.",
      kn: "ನಿಮಗೆ ಕೆಲಸ ಸಿಗಲು ನಿಮ್ಮ ಪ್ರೊಫೈಲ್ ರಚಿಸೋಣ.",
      ml: "ജോലി ലഭിക്കുന്നതിനായി പ്രൊഫൈൽ തയ്യാറാക്കാം.",
      or: "ଆସନ୍ତୁ ଆପଣଙ୍କ ଶ୍ରମିକ ପ୍ରୋଫାଇଲ୍ ତିଆରି କରିବା ଯାହାଦ୍ୱାରା କାମ ମିଳିପାରିବ।",
      ur: "آئیے مل کر آپ کی ورکر پروفائل بناتے ہیں تاکہ آپ کو کام مل سکے۔"
    },
    askName: {
      hi: "आपका पूरा नाम क्या है?",
      pa: "ਤੁਹਾਡਾ ਪੂਰਾ ਨਾਮ ਕੀ ਹੈ?",
      en: "What is your full name?",
      bn: "আপনার পুরো নাম কী?",
      mr: "तुमचे पूर्ण नाव काय आहे?",
      ta: "உங்கள் முழு பெயர் என்ன?",
      te: "మీ పూర్తి పేరు ఏమిటి?",
      gu: "તમારું પૂરું નામ શું છે?",
      kn: "ನಿಮ್ಮ ಪೂರ್ಣ ಹೆಸರು ಏನು?",
      ml: "നിങ്ങളുടെ മുഴുവൻ പേര് എന്താണ്?",
      or: "ଆପଣଙ୍କର ପୂରା ନାମ କ'ଣ?",
      ur: "آپ کا پورا نام کیا ہے؟"
    },
    askTrade: {
      hi: "आपका मुख्य काम या पेशा क्या है? जैसे प्लंबर, इलेक्ट्रीशियन, पेंटर, या बढ़ई।",
      pa: "ਤੁਹਾਡਾ ਮੁੱਖ ਕੰਮ ਜਾਂ ਹੁਨਰ ਕੀ ਹੈ? ਜਿਵੇਂ ਕਿ ਪਲੰਬਰ, ਇਲੈਕਟ੍ਰੀਸ਼ੀਅਨ, ਪੇਂਟਰ, ਜਾਂ ਤਰਖਾਣ।",
      en: "What is your primary trade or skill? For example, Plumber, Electrician, Painter, or Carpenter.",
      bn: "আপনার প্রধান কাজ বা পেশা কী? যেমন প্লাম্বার, ইলেকট্রিশিয়ান, পেইন্টার বা ছুতোর।",
      mr: "तुमचे मुख्य काम काय आहे? जसे की प्लंबर, इलेक्ट्रिशियन, पेंटर, किंवा सुतार.",
      ta: "உங்கள் முதன்மை தொழில் என்ன? எ.கா. பிளம்பர், எலக்ட்ரீஷியன், பெயிண்டர்.",
      te: "మీ ప్రధాన వృత్తి ఏమిటి? ఉదాహరణకు ప్లంబర్, ఎలక్ట్రీషియన్, పెయింటర్.",
      gu: "તમારું મુખ્ય કામ શું છે? જેમ કે પ્લમ્બર, ઇલેક્ટ્રિશિયન, પેઇન્ટર કે સુથાર.",
      kn: "ನಿಮ್ಮ ಮುಖ್ಯ ವೃತ್ತಿ ಯಾವುದು? ಉದಾಹರಣೆಗೆ ಪ್ಲಂಬರ್, ಎಲೆಕ್ಟ್ರಿಷಿಯನ್.",
      ml: "നിങ്ങളുടെ പ്രധാന ജോലി എന്താണ്? ഉദാഹരണത്തിന് പ്ലംബർ, ഇലക്ട്രീഷ്യൻ.",
      or: "ଆପଣଙ୍କର ମୁଖ୍ୟ କାମ କ'ଣ? ଯେପରିକି ପ୍ଲମ୍ବର, ଇଲେକ୍ଟ୍ରିସିଆନ୍, ପେଣ୍ଟର୍ ବା ବଢ଼େଇ।",
      ur: "آپ کا بنیادی کام کیا ہے؟ جیسے پلمبر، الیکٹریشن، پینٹر یا بڑھئی۔"
    },
    askLocation: {
      hi: "आप किस शहर या इलाके में काम करना चाहते हैं?",
      pa: "ਤੁਸੀਂ ਕਿਸ ਸ਼ਹਿਰ ਜਾਂ ਇਲਾਕੇ ਵਿੱਚ ਕੰਮ ਕਰਨਾ ਚਾਹੁੰਦੇ ਹੋ?",
      en: "In which city or area do you want to work?",
      bn: "আপনি কোন শহর বা এলাকায় কাজ করতে চান?",
      mr: "तुम्हाला कोणत्या शहरात किंवा भागात काम करायचे आहे?",
      ta: "நீங்கள் எந்த நகரம் அல்லது பகுதியில் வேலை செய்ய விரும்புகிறீர்கள்?",
      te: "మీరు ఏ నగరం లేదా ప్రాంతంలో పని చేయాలనుకుంటున్నారు?",
      gu: "તમે કયા શહેરમાં કે વિસ્તારમાં કામ કરવા માંગો છો?",
      kn: "ನೀವು ಯಾವ ನಗರ ಅಥವಾ ಪ್ರದೇಶದಲ್ಲಿ ಕೆಲಸ ಮಾಡಲು ಬಯಸುತ್ತೀರಿ?",
      ml: "ഏത് നഗരത്തിലോ പ്രദേശത്തോ ആണ് ജോലി ചെയ്യാൻ ആഗ്രഹിക്കുന്നത്?",
      or: "ଆପଣ କେଉଁ ସହର କିମ୍ବା ଅଞ୍ଚଳରେ କାମ କରିବାକୁ ଚାହାଁନ୍ତି?",
      ur: "آپ کس شہر یا علاقے میں کام کرنا چاہتے ہیں؟"
    },
    askPrice: {
      hi: "आपकी दैनिक मजदूरी या रेट (रुपये प्रति दिन) क्या है?",
      pa: "ਤੁਹਾਡੀ ਰੋਜ਼ਾਨਾ ਦਿਹਾੜੀ ਜਾਂ ਰੇਟ (ਰੁਪਏ ਪ੍ਰਤੀ ਦਿਨ) ਕੀ ਹੈ?",
      en: "What is your daily wage or rate (in Rupees per day)?",
      bn: "আপনার দৈনিক মজুরি বা রেট (টাকা প্রতিদিন) কত?",
      mr: "तुमचा दैनंदिन दर (रुपये प्रति दिवस) काय आहे?",
      ta: "உங்கள் தினசரி கூலி (ரூபாய்/நாள்) எவ்வளவு?",
      te: "మీ రోజువారీ కూలీ (రూపాయలు/రోజు) ఎంత?",
      gu: "તમારો દૈનિક દર (રૂપિયા પ્રતિ દિવસ) કેટલો છે?",
      kn: "ನಿಮ್ಮ ದಿನಗೂಲಿ (ರೂಪಾಯಿ/ದಿನ) ಎಷ್ಟು?",
      ml: "നിങ്ങളുടെ ദിവസക്കൂലി (രൂപ/ദിവസം) എത്രയാണ്?",
      or: "ଆପଣଙ୍କ ଦୈନିକ ମଜୁରୀ (ଟଙ୍କା ପ୍ରତି ଦିନ) କେତେ?",
      ur: "آپ کی روزانہ مزدوری یا ریٹ (روپے فی دن) کیا ہے؟"
    },
    askExperience: {
      hi: "आपको इस काम में कितने वर्षों का अनुभव है?",
      pa: "ਤੁਹਾਨੂੰ ਇਸ ਕੰਮ ਵਿੱਚ ਕਿੰਨੇ ਸਾਲਾਂ ਦਾ ਤਜਰਬਾ ਹੈ?",
      en: "How many years of experience do you have in this trade?",
      bn: "এই কাজে আপনার কত বছরের অভিজ্ঞতা আছে?",
      mr: "या कामात तुम्हाला किती वर्षांचा अनुभव आहे?",
      ta: "இந்த தொழிலில் உங்களுக்கு எத்தனை ஆண்டுகள் அனுபவம் உள்ளது?",
      te: "ఈ పనిలో మీకు ఎన్ని సంవత్సరాల అనుభవం ఉంది?",
      gu: "આ કામમાં તમને કેટલા વર્ષનો અનુભવ છે?",
      kn: "ಈ ಕೆಲಸದಲ್ಲಿ ನಿಮಗೆ ಎಷ್ಟು ವರ್ಷಗಳ ಅನುಭವವಿದೆ?",
      ml: "ഈ ജോലിയിൽ എത്ര വർഷത്തെ പരിചയമുണ്ട്?",
      or: "ଏହି କାମରେ ଆପଣଙ୍କର କେତେ ବର୍ଷର ଅଭିଜ୍ଞତା ଅଛି?",
      ur: "آپ کو اس کام میں کتنے سال کا تجربہ ہے؟"
    },
    fieldSaved: {
      hi: "सफलतापूर्वक सुरक्षित हो गया!",
      pa: "ਸਫਲਤਾਪੂਰਵਕ ਸੁਰੱਖਿਅਤ ਹੋ ਗਿਆ!",
      en: "Successfully saved to your profile!",
      bn: "সফলভাবে সংরক্ষিত হয়েছে!",
      mr: "यशस्वीरित्या सेव्ह केले!",
      ta: "வெற்றிகரமாக சேமிக்கப்பட்டது!",
      te: "విజయవంతంగా సేవ్ చేయబడింది!",
      gu: "સફળતાપૂર્વક સાચવવામાં આવ્યું!",
      kn: "ಯಶಸ್ವಿಯಾಗಿ ಉಳಿಸಲಾಗಿದೆ!",
      ml: "വിജയകരമായി സംരക്ഷിച്ചു!",
      or: "ସଫଳତାର ସହ ସଂରକ୍ଷିତ ହେଲା!",
      ur: "کامیابی سے محفوظ ہو گیا!"
    },
    profileConfirmPrompt: {
      hi: "आपकी प्रोफ़ाइल तैयार है। क्या यह जानकारी सही है? पुष्टि के लिए 'हाँ' बोलें या नीचे कन्फर्म दबाएँ।",
      pa: "ਤੁਹਾਡੀ ਪ੍ਰੋਫਾਈਲ ਤਿਆਰ ਹੈ। ਕੀ ਇਹ ਜਾਣਕਾਰੀ ਸਹੀ ਹੈ? ਪੁਸ਼ਟੀ ਲਈ 'ਹਾਂ' ਕਹੋ ਜਾਂ ਕਨਫਰਮ ਦਬਾਓ।",
      en: "Your profile summary is ready. Is this correct? Say 'Yes' or tap Confirm to activate.",
      bn: "আপনার প্রোফাইল প্রস্তুত। তথ্য কি সঠিক? নিশ্চিত করতে 'হ্যাঁ' বলুন বা কনফার্ম চাপুন।",
      mr: "तुमची प्रोफाईल तयार आहे. ही माहिती बरोबर आहे का? खात्री करण्यासाठी 'हो' म्हणा किंवा कन्फर्म दाबा.",
      ta: "உங்கள் சுயவிவரம் தயார். இது சரியானதா? உறுதிப்படுத்த 'ஆம்' என்று சொல்லவும்.",
      te: "మీ ప్రొఫైల్ సిద్ధంగా ఉంది. వివరాలు సరైనవేనా? నిర్ధారించడానికి 'అవును' అనండి.",
      gu: "તમારી પ્રોફાઇલ તૈયાર છે. શું આ વિગત સાચી છે? પુષ્ટિ માટે 'હા' બોલો.",
      kn: "ನಿಮ್ಮ ಪ್ರೊಫೈಲ್ ಸಿದ್ಧವಾಗಿದೆ. ದೃಢೀಕರಿಸಲು 'ಹೌದು' ಎಂದು ಹೇಳಿ.",
      ml: "പ്രൊഫൈൽ തയ്യാറാണ്. ഇത് ശരിയാണോ? സ്ഥിരീകരിക്കാൻ 'ശരി' എന്ന് പറയുക.",
      or: "ଆପଣଙ୍କ ପ୍ରୋଫାଇଲ୍ ପ୍ରସ୍ତୁତ। ତଥ୍ୟ ଠିକ୍ ଅଛି କି? ନିଶ୍ଚିତ କରିବାକୁ 'ହଁ' କୁହନ୍ତୁ।",
      ur: "آپ کی پروفائل تیار ہے۔ کیا یہ معلومات درست ہیں؟ تصدیق کے لیے 'ہاں' کہیں۔"
    },
    profileCompleteCelebration: {
      hi: "बधाई हो! आपकी वर्कर प्रोफ़ाइल सक्रिय हो गई है। अब आप स्थानीय काम के लिए तैयार हैं।",
      pa: "ਵਧਾਈਆਂ! ਤੁਹਾਡੀ ਵਰਕਰ ਪ੍ਰੋਫਾਈਲ ਸਰਗਰਮ ਹੋ ਗਈ ਹੈ। ਹੁਣ ਤੁਸੀਂ ਕੰਮ ਲੈਣ ਲਈ ਤਿਆਰ ਹੋ।",
      en: "Congratulations! Your worker profile is now live and active. You are ready to get jobs.",
      bn: "অভিনন্দন! আপনার কর্মী প্রোফাইল এখন সক্রিয়। আপনি এখন কাজের জন্য প্রস্তুত।",
      mr: "अभिनंदन! तुमची कामगार प्रोफाईल आता सक्रिय झाली आहे. तुम्ही कामासाठी तयार आहात.",
      ta: "வாழ்த்துக்கள்! உங்கள் சுயவிவரம் இப்போது நேரலையில் உள்ளது.",
      te: "అభినందనలు! మీ వర్కర్ ప్రొఫైల్ సక్రియం చేయబడింది.",
      gu: "અભિનંદન! તમારી વર્કર પ્રોફાઇલ હવે સક્રિય થઈ ગઈ છે.",
      kn: "ಅಭಿನಂದನೆಗಳು! ನಿಮ್ಮ ಕೆಲಸಗಾರ ಪ್ರೊಫೈಲ್ ಈಗ ಸಕ್ರಿಯವಾಗಿದೆ.",
      ml: "അഭിനന്ദനങ്ങൾ! പ്രൊഫൈൽ ഇപ്പോൾ സജീവമാണ്.",
      or: "ଅଭିନନ୍ଦନ! ଆପଣଙ୍କ ଶ୍ରମିକ ପ୍ରୋଫାଇଲ୍ ଏବେ ସକ୍ରିୟ ହୋଇଛି।",
      ur: "مبارک ہو! آپ کی ورکر پروفائل اب فعال ہو گئی ہے۔"
    },
    loginGuidance: {
      hi: "लॉगिन पेज पर आपका स्वागत है। कृपया स्क्रीन पर अपना 10 अंकों का मोबाइल नंबर और पासवर्ड दर्ज करें। सुरक्षा के लिए पासवर्ड कभी बोलकर न बताएं।",
      pa: "ਲੌਗਇਨ ਪੇਜ 'ਤੇ ਤੁਹਾਡਾ ਸੁਆਗਤ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਸਕ੍ਰੀਨ 'ਤੇ ਆਪਣਾ ਮੋਬਾਈਲ ਨੰਬਰ ਅਤੇ ਪਾਸਵਰਡ ਦਰਜ ਕਰੋ।",
      en: "Welcome to Login. Please enter your mobile number and password on screen. For security, never speak passwords aloud.",
      bn: "লগইন পেজে স্বাগতম। দয়া করে স্ক্রিনে আপনার মোবাইল নম্বর এবং পাসওয়ার্ড টাইপ করুন।",
      mr: "लॉगिन पृष्ठावर आपले स्वागत आहे. कृपया स्क्रीनवर तुमचा मोबाईल नंबर आणि पासवर्ड टाका.",
      ta: "உள்நுழைவு பக்கத்திற்கு வரவேற்கிறோம். திரையில் கடவுச்சொல்லை தட்டச்சு செய்யவும்.",
      te: "లాగిన్ పేజీకి స్వాగతం. దయచేసి స్క్రీన్‌పై మొబైల్ నంబర్ మరియు పాస్‌వర్డ్ నమోదు చేయండి.",
      gu: "લૉગિન પેજ પર તમારું સ્વાગત છે. કૃપા કરીને સ્ક્રીન પર તમારો મોબાઈલ નંબર અને પાસવર્ડ લખો.",
      kn: "ಲಾಗಿನ್ ಪುಟಕ್ಕೆ ಸುಸ್ವಾಗತ. ದಯವಿಟ್ಟು ಪರದೆಯ ಮೇಲೆ ಮೊಬೈಲ್ ಸಂಖ್ಯೆ ಮತ್ತು ಪಾಸ್‌ವರ್ಡ್ ನಮೂದಿಸಿ.",
      ml: "ലോഗിൻ പേജിലേക്ക് സ്വാഗതം. ദയവായി സ്ക്രീനിൽ പാസ്‌വേഡ് ടൈപ്പ് ചെയ്യുക.",
      or: "ଲଗ୍ ଇନ୍ ପୃଷ୍ଠାକୁ ସ୍ୱାଗତ। ଦୟାକରି ସ୍କ୍ରିନ୍ରେ ମୋବାଇଲ୍ ନମ୍ବର ଏବଂ ପାସୱାର୍ଡ ଲେଖନ୍ତୁ।",
      ur: "لاگ ان صفحے پر خوش آمدید۔ برائے مہربانی اسکرین پر اپنا موبائل نمبر اور پاس ورڈ درج کریں۔"
    },
    signupGuidance: {
      hi: "पंजीकरण पेज पर आपका स्वागत है। आप अपना विवरण बोलकर भी बता सकते हैं। पासवर्ड स्क्रीन पर सुरक्षित रूप से टाइप करें।",
      pa: "ਰਜਿਸਟ੍ਰੇਸ਼ਨ ਪੇਜ 'ਤੇ ਤੁਹਾਡਾ ਸੁਆਗਤ ਹੈ। ਪਾਸਵਰਡ ਸਕ੍ਰੀਨ 'ਤੇ ਸੁਰੱਖਿਅਤ ਢੰਗ ਨਾਲ ਟਾਈਪ ਕਰੋ।",
      en: "Welcome to Sign Up. You can speak your basic details. Please type your password securely on screen.",
      bn: "নিবন্ধন পেজে স্বাগতম। আপনি আপনার বিবরণ মুখে বলতে পারেন। পাসওয়ার্ড স্ক্রিনে টাইপ করুন।",
      mr: "नोंदणी पृष्ठावर आपले स्वागत आहे. पासवर्ड स्क्रीनवर सुरक्षितपणे टाइप करा.",
      ta: "பதிவு பக்கத்திற்கு வரவேற்கிறோம். கடவுச்சொல்லை திரையில் பாதுகாப்பாக தட்டச்சு செய்யவும்.",
      te: "నమోదు పేజీకి స్వాగతం. పాస్‌వర్డ్‌ను స్క్రీన్‌పై సురక్షితంగా టైప్ చేయండి.",
      gu: "નોંધણી પેજ પર તમારું સ્વાગત છે. પાસવર્ડ સ્ક્રીન પર સુરક્ષિત રીતે લખો.",
      kn: "ನೋಂದಣಿ ಪುಟಕ್ಕೆ ಸುಸ್ವಾಗತ. ಪಾಸ್‌ವರ್ಡ್ ಅನ್ನು ಪರದೆಯ ಮೇಲೆ ಸುರಕ್ಷಿತವಾಗಿ ಟೈಪ್ ಮಾಡಿ.",
      ml: "രജിസ്ട്രേഷൻ പേജിലേക്ക് സ്വാഗതം. പാസ്‌വേഡ് സ്ക്രീനിൽ സുരക്ഷിതമായി ടൈപ്പ് ചെയ്യുക.",
      or: "ପଞ୍ଜୀକରଣ ପୃଷ୍ଠାକୁ ସ୍ୱାଗତ। ପାସୱାର୍ଡ ସ୍କ୍ରିନ୍ରେ ସୁରକ୍ଷିତ ଭାବରେ ଟାଇପ୍ କରନ୍ତୁ।",
      ur: "رجسٹریشن صفحے پر خوش آمدید۔ پاس ورڈ اسکرین پر محفوظ طریقے سے ٹائپ کریں۔"
    },
    restartNotice: {
      hi: "सहायक बातचीत को फिर से शुरू किया गया है।",
      pa: "ਸਹਾਇਕ ਗੱਲਬਾਤ ਮੁੜ ਸ਼ੁਰੂ ਕੀਤੀ ਗਈ ਹੈ।",
      en: "Assistant conversation restarted from beginning.",
      bn: "সহকারী কথোপকথন পুনরায় শুরু হয়েছে।",
      mr: "सहाय्यक संभाषण पुन्हा सुरू झाले आहे.",
      ta: "உரையாடல் மீண்டும் தொடங்கப்பட்டது.",
      te: "సంభాషణ మొదటి నుండి పునఃప్రారంభించబడింది.",
      gu: "સહાયક વાતચીત ફરીથી શરૂ કરવામાં આવી છે.",
      kn: "ಸಂಭಾಷಣೆಯನ್ನು ಮೊದಲಿನಿಂದ ಪ್ರಾರಂಭಿಸಲಾಗಿದೆ.",
      ml: "സംഭാഷണം വീണ്ടും ആരംഭിച്ചു.",
      or: "ସହାୟକ କଥାବାର୍ତ୍ତା ପୁନରାରମ୍ଭ ହେଲା।",
      ur: "معاون گفتگو کو دوبارہ شروع کر دیا گیا ہے۔"
    },
    manualModeEnabled: {
      hi: "मैनुअल मोड सक्रिय: बोलने के लिए माइक बटन दबाएं।",
      pa: "ਮੈਨੂਅਲ ਮੋਡ ਕਿਰਿਆਸ਼ੀਲ: ਬੋਲਣ ਲਈ ਮਾਈਕ ਬਟਨ ਦਬਾਓ।",
      en: "Manual Mode active: Tap the microphone button when you want to speak.",
      bn: "ম্যানুয়াল মোড সক্রিয়: কথা বলার জন্য মাইক বোতাম টিপুন।",
      mr: "मॅन्युअल मोड सक्रिय: बोलण्यासाठी माइक बटण दाबा.",
      ta: "கைமுறை பயன்முறை செயலில் உள்ளது: பேச மைக் பொத்தானை அழுத்தவும்.",
      te: "మాన్యువల్ మోడ్ సక్రియంగా ఉంది: మాట్లాడటానికి మైక్ బటన్‌ను నొక్కండి.",
      gu: "મેન્યુઅલ મોડ સક્રિય: બોલવા માટે માઇક બટન દબાવો.",
      kn: "ಹಸ್ತಚಾಲಿತ ಮೋಡ್ ಸಕ್ರಿಯವಾಗಿದೆ: ಮಾತನಾಡಲು ಮೈಕ್ ಬಟನ್ ಒತ್ತಿರಿ.",
      ml: "മാനുവൽ മോഡ് സജീവമാണ്: സംസാരിക്കാൻ മൈക്ക് ബട്ടൺ അമർത്തുക.",
      or: "ମାନୁଆଲ୍ ମୋଡ୍ ସକ୍ରିୟ: କହିବା ପାଇଁ ମାଇକ୍ ବଟନ୍ ଦବାନ୍ତୁ।",
      ur: "دستی موڈ فعال: بولنے کے لیے مائیک بٹن دبائیں۔"
    },
    handsFreeEnabled: {
      hi: "हैंड्स-फ्री मोड सक्रिय: सहायक के बोलने के बाद माइक खुद शुरू हो जाएगा।",
      pa: "ਹੈਂਡਸ-ਫ੍ਰੀ ਮੋਡ ਕਿਰਿਆਸ਼ੀਲ: ਸਹਾਇਕ ਦੇ ਬੋਲਣ ਤੋਂ ਬਾਅਦ ਮਾਈਕ ਆਪਣੇ ਆਪ ਸ਼ੁਰੂ ਹੋ ਜਾਵੇਗਾ।",
      en: "Hands-Free Mode active: Microphone will listen automatically after the assistant speaks.",
      bn: "হ্যান্ডস-ফ্রি মোড সক্রিয়: সহকারী কথা বলার পর মাইক নিজে থেকেই শুনবে।",
      mr: "हँड्स-फ्री मोड सक्रिय: सहाय्यक बोलल्यानंतर माइक आपोआप सुरू होईल.",
      ta: "ஹேண்ட்ஸ்-ஃப்ரீ பயன்முறை செயலில் உள்ளது: உதவியாளர் பேசிய பிறகு மைக் தானாக இயங்கும்.",
      te: "హ్యాండ్స్-ఫ్రీ మోడ్ సక్రియంగా ఉంది: అసిస్టెంట్ మాట్లాడిన తర్వాత మైక్ స్వయంచాలకంగా వింటుంది.",
      gu: "હેન્ડ્સ-ફ્રી મોડ સક્રિય: સહાયકના બોલ્યા પછી માઇક આપમેળે શરૂ થશે.",
      kn: "ಹ್ಯಾಂಡ್ಸ್-ಫ್ರೀ ಮೋಡ್ ಸಕ್ರಿಯವಾಗಿದೆ: ಸಹಾಯಕರು ಮಾತನಾಡಿದ ನಂತರ ಮೈಕ್ ಸ್ವಯಂಚಾಲಿತವಾಗಿ ಕೇಳುತ್ತದೆ.",
      ml: "ഹാൻഡ്സ്-ഫ്രീ മോഡ് സജീവമാണ്: അസിസ്റ്റന്റ് സംസാരിച്ച ശേഷം മൈക്ക് സ്വയമേവ കേൾക്കും.",
      or: "ହାଣ୍ଡସ୍-ଫ୍ରି ମୋଡ୍ ସକ୍ରିୟ: ସହାୟକ କହିବା ପରେ ମାଇକ୍ ଆପେ ଆପେ ଶୁଣିବ।",
      ur: "ہینڈز فری موڈ فعال: معاون کے بولنے کے بعد مائیک خود بخود سننا شروع کر دے گا۔"
    }
  };

  /* ─────────────────────────────────────────────────────────────────────────
     4. TRADE RECOGNITION KEYWORD MAPPING
  ───────────────────────────────────────────────────────────────────────── */
  const TRADE_MAP = {
    'plumber': 'Plumber',
    'plumbing': 'Plumber',
    'nal': 'Plumber',
    'nal mistri': 'Plumber',
    'plumber hu': 'Plumber',
    'electrician': 'Electrician',
    'bijli': 'Electrician',
    'bijli mistri': 'Electrician',
    'electrician hu': 'Electrician',
    'carpenter': 'Carpenter',
    'badhai': 'Carpenter',
    'carpenter hu': 'Carpenter',
    'painter': 'Painter',
    'rangai': 'Painter',
    'putai': 'Painter',
    'painter hu': 'Painter',
    'driver': 'Driver',
    'gadi': 'Driver',
    'driver hu': 'Driver',
    'cleaner': 'House Help / Maid',
    'maid': 'House Help / Maid',
    'safai': 'House Help / Maid',
    'security': 'Security Guard',
    'guard': 'Security Guard',
    'helper': 'Construction Helper',
    'majdoor': 'Construction Helper',
    'gardener': 'Gardener',
    'mali': 'Gardener',
    'tailor': 'Tailor',
    'darzi': 'Tailor',
    'cook': 'Cook / Helper',
    'khana': 'Cook / Helper'
  };

  function detectTradeFromText(text) {
    if (!text) return null;
    const lower = text.toLowerCase();
    for (const [key, trade] of Object.entries(TRADE_MAP)) {
      if (lower.includes(key)) return trade;
    }
    return null;
  }

  function extractDigits(text) {
    if (!text) return null;
    const match = text.match(/\d+/);
    return match ? parseInt(match[0], 10) : null;
  }

  /* ─────────────────────────────────────────────────────────────────────────
     5. VOICEHIRE ASSISTANT CORE CONTROLLER
  ───────────────────────────────────────────────────────────────────────── */
  class VoiceHireAssistant {
    constructor() {
      // Configuration & Preferences
      this.currentLang = localStorage.getItem('vh_lang') || (window.VH && window.VH.lang) || 'hi';
      if (!LANGUAGES[this.currentLang]) this.currentLang = 'hi';

      // Bug 3: Voice Interaction Modes ('hands_free' | 'manual')
      const savedMode = localStorage.getItem('vh_voice_mode');
      if (savedMode === 'manual') {
        this.voiceMode = 'manual';
      } else {
        this.voiceMode = 'hands_free'; // Default hands-free
      }

      this.isMuted = localStorage.getItem('vh_muted') === 'true';
      this.isDismissed = sessionStorage.getItem('vh_dismissed') === 'true';

      // State Machine (Phase 14.1)
      this.state = States.UNINITIALIZED;
      this.selectedRole = null;       // 'worker' | 'user'
      this.selectedAction = null;     // 'login' | 'register'
      this.lastInstruction = '';

      // Bug 2: Worker Profile Model (authoritative in-flight state)
      this.workerProfile = {
        name: '',
        work: '',
        location: '',
        price: '',
        experience_years: '',
        bio: '',
        isComplete: false,
        isConfirmed: false
      };
      this.workerProfilePendingField = null; // currently queried mandatory field

      // Production Voice Services Engine
      this.tts = new (window.VoiceHireVoice ? window.VoiceHireVoice.TextToSpeechService : Object)();
      this.stt = new (window.VoiceHireVoice ? window.VoiceHireVoice.SpeechRecognitionService : Object)();
      this.lastClickTime = 0;
      this.isSpeaking = false;
      this.isListening = false;
      this.isProcessing = false;
      this.micPermissionGranted = localStorage.getItem('vh_mic_granted') === 'true';

      // Message history cache
      this.messagesHistory = [];

      // DOM References
      this.dom = {};

      this.init();
    }

    init() {
      this.injectStyles();
      this.renderWidget();
      this.bindControls();
      this.initVoiceServices();
      this.setupSensitiveInputProtection();

      // Bug 1: Session recovery across routes and page refreshes
      const savedSession = this.getSavedSession();
      if (savedSession) {
        this.restoreSession(savedSession);
        return;
      }

      // Check whether user explicitly preferred manual mode
      if (this.voiceMode === 'manual') {
        this.updateStatus('Manual Mode', 'ready');
      }

      // If already dismissed for this tab session, do not auto-open
      if (this.isDismissed) {
        return;
      }

      // Brand new session on landing or home: auto-open and begin Hindi onboarding
      const path = window.location.pathname;
      const isGateway = path === '/' || path === '/gateway' || path === '/home';
      if (isGateway) {
        setTimeout(() => {
          this.open();
          this.startOnboarding();
        }, 750);
      } else {
        // Direct arrival on an interior page without prior session
        this.handleDirectPageVisit();
      }
    }

    /* ── Bug 1: State Persistence & Session Management ─────────────────── */
    getSavedSession() {
      try {
        const raw = sessionStorage.getItem('vh_assistant_session');
        if (!raw) return null;
        return JSON.parse(raw);
      } catch (e) {
        return null;
      }
    }

    saveSession() {
      try {
        // Sanitize: strictly strip passwords, tokens, pins, credentials
        const safeMessages = (this.messagesHistory || []).slice(-25).map(m => ({
          text: String(m.text || '').substring(0, 300),
          sender: m.sender === 'user' ? 'user' : 'bot'
        }));

        const payload = {
          state: this.state,
          currentLang: this.currentLang,
          selectedRole: this.selectedRole,
          selectedAction: this.selectedAction,
          workerProfile: this.workerProfile,
          workerProfilePendingField: this.workerProfilePendingField,
          voiceMode: this.voiceMode,
          isMuted: this.isMuted,
          lastRoute: window.location.pathname,
          lastInstruction: this.lastInstruction,
          messages: safeMessages,
          timestamp: Date.now()
        };
        sessionStorage.setItem('vh_assistant_session', JSON.stringify(payload));
      } catch (e) {
        console.warn('[Assistant Session Save Warning]', e);
      }
    }

    clearSession() {
      try {
        sessionStorage.removeItem('vh_assistant_session');
      } catch (e) {}
    }

    restoreSession(saved) {
      if (!saved) return;
      this.currentLang = saved.currentLang || this.currentLang;
      this.selectedRole = saved.selectedRole || (window.VH && window.VH.role) || null;
      this.selectedAction = saved.selectedAction || null;
      this.state = saved.state || States.IDLE;
      if (saved.voiceMode) this.voiceMode = saved.voiceMode;
      if (saved.workerProfile) this.workerProfile = Object.assign(this.workerProfile, saved.workerProfile);
      this.workerProfilePendingField = saved.workerProfilePendingField || null;

      // Update toolbar UI for restored preferences
      this.updateModeButtonUI();
      this.setLanguage(this.currentLang, false);

      // Re-populate chat history
      if (Array.isArray(saved.messages) && saved.messages.length > 0) {
        this.messagesHistory = saved.messages;
        saved.messages.forEach(m => {
          this.renderBubbleToDOM(m.text, m.sender);
        });
      }

      const currentPath = window.location.pathname;
      const lastPath = saved.lastRoute || '';

      // Check whether user is authenticated via server session
      const isAuthenticated = Boolean(window.VH && window.VH.userId);
      const isWorker = (window.VH && window.VH.role === 'worker') || this.selectedRole === 'worker';

      // Always open panel if user had an in-progress onboarding or arrived on auth/dashboard
      if (this.state !== States.IDLE && !this.isDismissed) {
        this.open();
      }

      // Handle Route Change vs Explicit Restart
      if (currentPath !== lastPath) {
        // User navigated to a new page!
        if (currentPath === '/login') {
          this.state = States.AUTH_IN_PROGRESS;
          const loginPrompt = DIALOGUES.loginGuidance[this.currentLang] || DIALOGUES.loginGuidance.hi;
          this.addMessage(loginPrompt, 'bot');
          this.lastInstruction = loginPrompt;
          this.speak(loginPrompt, this.currentLang);
        } else if (currentPath === '/signup/worker') {
          this.state = States.AUTH_IN_PROGRESS;
          this.selectedRole = 'worker';
          const signupPrompt = DIALOGUES.signupGuidance[this.currentLang] || DIALOGUES.signupGuidance.hi;
          this.addMessage(signupPrompt, 'bot');
          this.lastInstruction = signupPrompt;
          this.speak(signupPrompt, this.currentLang);
        } else if (currentPath === '/signup/user') {
          this.state = States.AUTH_IN_PROGRESS;
          this.selectedRole = 'user';
          const signupPrompt = DIALOGUES.signupGuidance[this.currentLang] || DIALOGUES.signupGuidance.hi;
          this.addMessage(signupPrompt, 'bot');
          this.lastInstruction = signupPrompt;
          this.speak(signupPrompt, this.currentLang);
        } else if (currentPath === '/dashboard/worker' || (isAuthenticated && isWorker)) {
          // Returning from auth / arrived on Worker Dashboard!
          this.state = States.CHECKING_PROFILE;
          this.saveSession();
          this.checkWorkerProfileOnServer();
        } else if (currentPath === '/dashboard/user' || (isAuthenticated && !isWorker)) {
          this.state = States.DASHBOARD_GUIDANCE;
          const msg = this.currentLang === 'hi' ? "डैशबोर्ड पर आपका स्वागत है। आप यहाँ से वर्कर ढूँढ सकते हैं।" : "Welcome to your dashboard. You can search and book workers.";
          this.addMessage(msg, 'bot');
          this.speak(msg, this.currentLang);
        }
      } else {
        // Page was refreshed on the same URL: safely resume where left off
        if (this.state === States.COLLECTING_PROFILE_FIELDS && this.workerProfilePendingField) {
          this.askWorkerProfileField(this.workerProfilePendingField, false);
        } else if (this.state === States.AWAITING_PROFILE_CONFIRMATION) {
          this.showProfileSummaryAndConfirm(false);
        } else if (isAuthenticated && isWorker && currentPath === '/dashboard/worker') {
          this.checkWorkerProfileOnServer();
        }
      }

      this.saveSession();
    }

    handleDirectPageVisit() {
      const path = window.location.pathname;
      const isAuthenticated = Boolean(window.VH && window.VH.userId);
      const isWorker = (window.VH && window.VH.role === 'worker');

      if (path === '/login') {
        this.open();
        this.state = States.AUTH_IN_PROGRESS;
        const msg = DIALOGUES.loginGuidance[this.currentLang] || DIALOGUES.loginGuidance.hi;
        this.addMessage(msg, 'bot');
        this.lastInstruction = msg;
        this.speak(msg, this.currentLang);
      } else if (path === '/signup/worker') {
        this.open();
        this.state = States.AUTH_IN_PROGRESS;
        this.selectedRole = 'worker';
        const msg = DIALOGUES.signupGuidance[this.currentLang] || DIALOGUES.signupGuidance.hi;
        this.addMessage(msg, 'bot');
        this.lastInstruction = msg;
        this.speak(msg, this.currentLang);
      } else if (isAuthenticated && isWorker) {
        this.open();
        this.state = States.CHECKING_PROFILE;
        this.checkWorkerProfileOnServer();
      }
      this.saveSession();
    }

    restartConversation() {
      // Explicit user-initiated conversation restart
      this.cancelVoice();
      this.clearSession();
      this.clearMessagesDOM();
      this.messagesHistory = [];
      this.selectedRole = null;
      this.selectedAction = null;
      this.workerProfile = { name: '', work: '', location: '', price: '', experience_years: '', bio: '', isComplete: false, isConfirmed: false };
      this.workerProfilePendingField = null;

      const notice = DIALOGUES.restartNotice[this.currentLang] || DIALOGUES.restartNotice.hi;
      this.addMessage(`🔄 ${notice}`, 'bot');
      setTimeout(() => {
        this.startOnboarding();
      }, 350);
    }

    /* ── DOM & Styling ─────────────────────────────────────────────────── */
    injectStyles() {
      if (document.getElementById('vh-assistant-styles')) return;
      const s = document.createElement('style');
      s.id = 'vh-assistant-styles';
      s.textContent = `
        /* VoiceHire Assistant Container */
        #vh-assistant-root {
          position: fixed;
          bottom: 24px;
          right: 24px;
          z-index: 999999;
          font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          pointer-events: none;
        }

        /* Floating Action Button (FAB) */
        .vh-fab {
          pointer-events: auto;
          position: absolute;
          bottom: 0;
          right: 0;
          width: 60px;
          height: 60px;
          border-radius: 50%;
          background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
          border: 3px solid #FFFFFF;
          color: #FFFFFF;
          box-shadow: 0 8px 24px rgba(37, 99, 235, 0.35);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1.5rem;
          transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease;
        }
        .vh-fab:hover {
          transform: scale(1.08);
          box-shadow: 0 12px 32px rgba(37, 99, 235, 0.45);
        }
        .vh-fab-pulse {
          position: absolute;
          top: -2px;
          right: -2px;
          width: 14px;
          height: 14px;
          border-radius: 50%;
          background: #16A34A;
          border: 2px solid #FFFFFF;
          animation: vh-pulse-ring 2s infinite;
        }
        @keyframes vh-pulse-ring {
          0% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.6); opacity: 0.5; }
          100% { transform: scale(1); opacity: 1; }
        }

        /* Main Assistant Window Panel */
        .vh-panel {
          pointer-events: auto;
          position: absolute;
          bottom: 74px;
          right: 0;
          width: 390px;
          max-width: calc(100vw - 32px);
          max-height: 85vh;
          background: #FFFFFF;
          border-radius: 20px;
          border: 1px solid #E2E8F0;
          box-shadow: 0 20px 48px rgba(15, 23, 42, 0.18), 0 8px 16px rgba(15, 23, 42, 0.08);
          display: flex;
          flex-direction: column;
          overflow: hidden;
          opacity: 0;
          transform: scale(0.85) translateY(20px);
          transform-origin: bottom right;
          transition: transform 0.28s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.22s ease;
          display: none;
        }
        .vh-panel.is-open {
          display: flex;
          opacity: 1;
          transform: scale(1) translateY(0);
        }

        /* Header */
        .vh-header {
          background: linear-gradient(135deg, #1E40AF 0%, #2563EB 100%);
          color: #FFFFFF;
          padding: 14px 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-top-left-radius: 20px;
          border-top-right-radius: 20px;
        }
        .vh-header-info {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .vh-header-avatar {
          width: 42px;
          height: 42px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.2);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1.3rem;
          position: relative;
        }
        .vh-header-ring {
          position: absolute;
          inset: -3px;
          border-radius: 50%;
          border: 2px solid transparent;
          transition: all 0.3s ease;
        }
        .vh-header-ring.speaking {
          border-color: #38BDF8;
          animation: vh-spin 3s linear infinite;
        }
        .vh-header-ring.listening {
          border-color: #EF4444;
          box-shadow: 0 0 12px rgba(239, 68, 68, 0.6);
          animation: vh-pulse 1s infinite alternate;
        }
        @keyframes vh-spin { 100% { transform: rotate(360deg); } }
        @keyframes vh-pulse { from { opacity: 0.6; transform: scale(0.98); } to { opacity: 1; transform: scale(1.08); } }

        .vh-header-title {
          font-weight: 700;
          font-size: 0.95rem;
          line-height: 1.2;
        }
        .vh-header-status {
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.85);
          display: flex;
          align-items: center;
          gap: 6px;
          margin-top: 2px;
        }
        .vh-status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #4ADE80;
        }
        .vh-status-dot.speaking { background: #38BDF8; }
        .vh-status-dot.listening { background: #EF4444; }
        .vh-status-dot.processing { background: #FBBF24; }

        .vh-toolbar {
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .vh-tool-btn {
          background: rgba(255, 255, 255, 0.15);
          border: none;
          color: #FFFFFF;
          width: 30px;
          height: 30px;
          border-radius: 8px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.825rem;
          transition: background 0.2s ease;
        }
        .vh-tool-btn:hover { background: rgba(255, 255, 255, 0.3); }
        .vh-tool-btn.active { background: #10B981; }

        /* Language Drawer */
        .vh-lang-drawer {
          background: #F8FAFC;
          border-bottom: 1px solid #E2E8F0;
          padding: 12px;
          display: none;
          max-height: 200px;
          overflow-y: auto;
        }
        .vh-lang-drawer.is-open { display: block; }
        .vh-lang-drawer-title {
          font-size: 0.75rem;
          font-weight: 600;
          color: #64748B;
          margin-bottom: 8px;
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .vh-lang-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 6px;
        }
        .vh-lang-card {
          background: #FFFFFF;
          border: 1px solid #CBD5E1;
          border-radius: 8px;
          padding: 6px 10px;
          display: flex;
          align-items: center;
          gap: 8px;
          cursor: pointer;
          transition: all 0.18s ease;
          text-align: left;
        }
        .vh-lang-card:hover {
          border-color: #2563EB;
          background: #EFF6FF;
        }
        .vh-lang-card.selected {
          border-color: #2563EB;
          background: #DBEAFE;
          font-weight: 600;
        }
        .vh-lang-native { font-size: 0.85rem; color: #0F172A; }
        .vh-lang-name { font-size: 0.72rem; color: #64748B; }

        /* Autoplay Blocked Banner */
        .vh-autoplay-banner {
          background: #FEF3C7;
          border-bottom: 1px solid #F59E0B;
          padding: 10px 14px;
          display: none;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
        }
        .vh-autoplay-banner.is-visible { display: flex; }
        .vh-autoplay-text {
          font-size: 0.8rem;
          color: #92400E;
          font-weight: 500;
          line-height: 1.3;
        }
        .vh-autoplay-btn {
          background: #D97706;
          color: #FFFFFF;
          border: none;
          padding: 6px 12px;
          border-radius: 6px;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer;
          white-space: nowrap;
        }
        .vh-autoplay-btn:hover { background: #B45309; }

        /* Messages Stream */
        .vh-messages {
          flex: 1;
          padding: 14px;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 12px;
          background: #F8FAFC;
          min-height: 220px;
          max-height: 380px;
        }
        .vh-bubble {
          max-width: 86%;
          padding: 10px 14px;
          border-radius: 14px;
          font-size: 0.875rem;
          line-height: 1.45;
          word-break: break-word;
          animation: vh-fade-in 0.2s ease;
        }
        @keyframes vh-fade-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        .vh-bubble.bot {
          align-self: flex-start;
          background: #FFFFFF;
          color: #1E293B;
          border: 1px solid #E2E8F0;
          border-bottom-left-radius: 4px;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        }
        .vh-bubble.user {
          align-self: flex-end;
          background: #2563EB;
          color: #FFFFFF;
          border-bottom-right-radius: 4px;
          box-shadow: 0 1px 4px rgba(37, 99, 235, 0.25);
        }

        /* Choices Container & Buttons */
        .vh-choices {
          display: flex;
          flex-direction: column;
          gap: 8px;
          margin-top: 4px;
          animation: vh-fade-in 0.2s ease;
        }
        .vh-choice-btn {
          background: #FFFFFF;
          border: 1.5px solid #CBD5E1;
          color: #1E293B;
          padding: 10px 12px;
          border-radius: 10px;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 0.85rem;
          font-weight: 500;
          transition: all 0.16s ease;
          text-align: left;
        }
        .vh-choice-btn:hover {
          border-color: #2563EB;
          background: #EFF6FF;
          transform: translateY(-1px);
        }
        .vh-choice-btn.primary {
          background: #2563EB;
          border-color: #2563EB;
          color: #FFFFFF;
        }
        .vh-choice-btn.primary:hover {
          background: #1D4ED8;
          border-color: #1D4ED8;
        }
        .vh-choice-icon {
          font-size: 1.2rem;
          flex-shrink: 0;
        }
        .vh-choice-content {
          display: flex;
          flex-direction: column;
        }
        .vh-choice-title { font-weight: 600; }
        .vh-choice-sub { font-size: 0.725rem; opacity: 0.85; }

        /* Profile Summary Card */
        .vh-profile-summary-card {
          background: #FFFFFF;
          border: 1.5px solid #10B981;
          border-radius: 12px;
          padding: 12px;
          margin-top: 6px;
          box-shadow: 0 4px 12px rgba(16, 185, 129, 0.15);
        }
        .vh-summary-title {
          font-weight: 700;
          color: #065F46;
          font-size: 0.85rem;
          margin-bottom: 8px;
          border-bottom: 1px solid #E2E8F0;
          padding-bottom: 4px;
        }
        .vh-summary-row {
          display: flex;
          justify-content: space-between;
          font-size: 0.8rem;
          padding: 3px 0;
          color: #334155;
        }
        .vh-summary-row strong { color: #0F172A; }
        .vh-summary-actions {
          display: flex;
          gap: 8px;
          margin-top: 10px;
        }
        .vh-saved-badge {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          background: #D1FAE5;
          color: #065F46;
          font-size: 0.72rem;
          font-weight: 600;
          padding: 2px 8px;
          border-radius: 6px;
          margin-top: 4px;
        }

        /* Interim recognition display */
        .vh-interim {
          background: #FEF3C7;
          border-left: 3px solid #F59E0B;
          color: #78350F;
          padding: 6px 12px;
          font-size: 0.8rem;
          font-style: italic;
          display: none;
        }
        .vh-interim.is-active { display: block; }

        /* Footer Controls */
        .vh-footer {
          background: #FFFFFF;
          border-top: 1px solid #E2E8F0;
          padding: 12px 14px;
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .vh-mic-action {
          width: 50px;
          height: 50px;
          border-radius: 50%;
          background: #2563EB;
          color: #FFFFFF;
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1.3rem;
          box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
          transition: all 0.2s ease;
          flex-shrink: 0;
        }
        .vh-mic-action:hover {
          transform: scale(1.05);
          background: #1D4ED8;
        }
        .vh-mic-action.is-listening {
          background: #DC2626;
          box-shadow: 0 0 16px rgba(220, 38, 38, 0.5);
          animation: vh-mic-pulse 1.2s infinite alternate;
        }
        @keyframes vh-mic-pulse { from { transform: scale(1); } to { transform: scale(1.1); } }

        .vh-footer-info {
          flex: 1;
          display: flex;
          flex-direction: column;
        }
        .vh-mic-hint {
          font-size: 0.85rem;
          font-weight: 600;
          color: #0F172A;
        }
        .vh-mic-subhint {
          font-size: 0.72rem;
          color: #64748B;
        }

        .vh-repeat-btn {
          background: #F1F5F9;
          border: 1px solid #CBD5E1;
          color: #475569;
          padding: 6px 10px;
          border-radius: 8px;
          font-size: 0.75rem;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .vh-repeat-btn:hover { background: #E2E8F0; color: #0F172A; }

        /* Sound Wave Indicator */
        .vh-wave-wrap {
          display: flex;
          align-items: center;
          gap: 2px;
          height: 12px;
          margin-top: 3px;
          display: none;
        }
        .vh-wave-wrap.is-active { display: flex; }
        .vh-wave-bar {
          width: 3px;
          height: 100%;
          background: #2563EB;
          border-radius: 2px;
          animation: vh-wave 0.8s ease-in-out infinite alternate;
        }
        .vh-wave-bar:nth-child(2) { animation-delay: 0.15s; height: 70%; }
        .vh-wave-bar:nth-child(3) { animation-delay: 0.3s; height: 100%; }
        .vh-wave-bar:nth-child(4) { animation-delay: 0.45s; height: 60%; }
        .vh-wave-bar:nth-child(5) { animation-delay: 0.6s; height: 80%; }
        @keyframes vh-wave { from { transform: scaleY(0.2); } to { transform: scaleY(1); } }

        /* Typed input row */
        .vh-typed-row {
          display: flex;
          border-top: 1px solid #F1F5F9;
          padding: 8px 12px;
          background: #FFFFFF;
          gap: 6px;
        }
        .vh-typed-input {
          flex: 1;
          border: 1px solid #CBD5E1;
          border-radius: 8px;
          padding: 6px 10px;
          font-size: 0.8rem;
          outline: none;
        }
        .vh-typed-input:focus { border-color: #2563EB; }
        .vh-typed-send {
          background: #2563EB;
          border: none;
          color: #FFFFFF;
          width: 32px;
          height: 32px;
          border-radius: 8px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
        }
      `;
      document.head.appendChild(s);
    }

    renderWidget() {
      ['vh-assistant-root', 'vhai-root', 'vgb-root', 'vh-gateway-bot'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.remove();
      });

      const root = document.createElement('div');
      root.id = 'vh-assistant-root';

      const langCardsHtml = Object.values(LANGUAGES).map(l => `
        <button class="vh-lang-card ${l.code === this.currentLang ? 'selected' : ''}" data-code="${l.code}">
          <span class="vh-lang-flag">${l.flag}</span>
          <div>
            <div class="vh-lang-native">${l.native}</div>
            <div class="vh-lang-name">${l.name}</div>
          </div>
        </button>
      `).join('');

      root.innerHTML = `
        <!-- Floating FAB -->
        <button class="vh-fab" id="vh-fab-trigger" title="VoiceHire Voice Assistant" aria-label="Open VoiceHire Assistant">
          <i class="fa-solid fa-microphone-lines"></i>
          <span class="vh-fab-pulse"></span>
        </button>

        <!-- Main Panel -->
        <div class="vh-panel" id="vh-main-panel" role="dialog" aria-label="VoiceHire Voice Assistant">
          
          <!-- Header -->
          <div class="vh-header">
            <div class="vh-header-info">
              <div class="vh-header-avatar">
                <i class="fa-solid fa-robot"></i>
                <div class="vh-header-ring" id="vh-status-ring"></div>
              </div>
              <div>
                <div class="vh-header-title">VoiceHire Assistant</div>
                <div class="vh-header-status">
                  <span class="vh-status-dot" id="vh-status-dot"></span>
                  <span id="vh-status-text">Ready</span>
                </div>
              </div>
            </div>

            <div class="vh-toolbar">
              <!-- Restart button (Bug 1: Deliberate conversation restart) -->
              <button class="vh-tool-btn" id="vh-btn-restart" title="Restart Assistant / शुरुआत से शुरू करें" aria-label="Restart Assistant">
                <i class="fa-solid fa-rotate-left"></i>
              </button>
              <!-- Voice Mode Toggle (Bug 3: Hands-Free vs Manual) -->
              <button class="vh-tool-btn ${this.voiceMode === 'hands_free' ? 'active' : ''}" id="vh-btn-mode" title="Toggle Hands-Free / Manual Mode" aria-label="Voice Interaction Mode">
                <i class="fa-solid ${this.voiceMode === 'hands_free' ? 'fa-headset' : 'fa-hand'}"></i>
              </button>
              <!-- Language Drawer Toggle -->
              <button class="vh-tool-btn" id="vh-btn-lang" title="Change Language / भाषा बदलें">
                <i class="fa-solid fa-language"></i>
              </button>
              <!-- Sound Mute/Unmute -->
              <button class="vh-tool-btn ${this.isMuted ? 'active' : ''}" id="vh-btn-sound" title="${this.isMuted ? 'Unmute Voice' : 'Mute Voice'}">
                <i class="fa-solid ${this.isMuted ? 'fa-volume-xmark' : 'fa-volume-high'}"></i>
              </button>
              <!-- Minimize & Close -->
              <button class="vh-tool-btn" id="vh-btn-min" title="Minimize">
                <i class="fa-solid fa-window-minimize"></i>
              </button>
              <button class="vh-tool-btn" id="vh-btn-close" title="Close">
                <i class="fa-solid fa-xmark"></i>
              </button>
            </div>
          </div>

          <!-- Language Selection Drawer -->
          <div class="vh-lang-drawer" id="vh-lang-drawer">
            <div class="vh-lang-drawer-title">🌐 Choose Language / अपनी भाषा चुनें</div>
            <div class="vh-lang-grid" id="vh-lang-grid">
              ${langCardsHtml}
            </div>
          </div>

          <!-- Autoplay Blocked Banner -->
          <div class="vh-autoplay-banner" id="vh-autoplay-banner">
            <div class="vh-autoplay-text" id="vh-autoplay-text">
              आवाज़ सुनने के लिए यहाँ टैप करें
            </div>
            <button class="vh-autoplay-btn" id="vh-start-voice-btn">
              <i class="fa-solid fa-volume-high"></i> Start
            </button>
          </div>

          <!-- Message History Stream -->
          <div class="vh-messages" id="vh-messages-stream"></div>

          <!-- Interim Speech Transcript -->
          <div class="vh-interim" id="vh-interim-box"></div>

          <!-- Footer Action Bar -->
          <div class="vh-footer">
            <button class="vh-mic-action" id="vh-mic-btn" title="Tap to Speak / बोलने के लिए टैप करें">
              <i class="fa-solid fa-microphone"></i>
            </button>
            <div class="vh-footer-info">
              <div class="vh-mic-hint" id="vh-mic-hint">${this.voiceMode === 'hands_free' ? 'Hands-Free Active' : 'Tap to Speak'}</div>
              <div class="vh-mic-subhint" id="vh-mic-subhint">${this.voiceMode === 'hands_free' ? 'Auto-listens after speaking' : 'Tap mic when ready'}</div>
              <div class="vh-wave-wrap" id="vh-wave-indicator">
                <div class="vh-wave-bar"></div>
                <div class="vh-wave-bar"></div>
                <div class="vh-wave-bar"></div>
                <div class="vh-wave-bar"></div>
                <div class="vh-wave-bar"></div>
              </div>
            </div>
            <button class="vh-repeat-btn" id="vh-repeat-btn" title="Repeat Prompt">
              <i class="fa-solid fa-rotate-right"></i>
            </button>
          </div>

          <!-- Typed Input Fallback -->
          <div class="vh-typed-row" id="vh-typed-row">
            <input type="text" class="vh-typed-input" id="vh-typed-input" placeholder="यहाँ टाइप करें / Type message..." aria-label="Type message fallback">
            <button class="vh-typed-send" id="vh-typed-send" title="Send" aria-label="Send message">
              <i class="fa-solid fa-paper-plane"></i>
            </button>
          </div>

        </div>
      `;

      document.body.appendChild(root);

      this.dom = {
        root: document.getElementById('vh-assistant-root'),
        fab: document.getElementById('vh-fab-trigger'),
        panel: document.getElementById('vh-main-panel'),
        statusRing: document.getElementById('vh-status-ring'),
        statusDot: document.getElementById('vh-status-dot'),
        statusText: document.getElementById('vh-status-text'),
        btnRestart: document.getElementById('vh-btn-restart'),
        btnMode: document.getElementById('vh-btn-mode'),
        btnLang: document.getElementById('vh-btn-lang'),
        btnSound: document.getElementById('vh-btn-sound'),
        btnMin: document.getElementById('vh-btn-min'),
        btnClose: document.getElementById('vh-btn-close'),
        langDrawer: document.getElementById('vh-lang-drawer'),
        autoplayBanner: document.getElementById('vh-autoplay-banner'),
        autoplayText: document.getElementById('vh-autoplay-text'),
        startVoiceBtn: document.getElementById('vh-start-voice-btn'),
        messages: document.getElementById('vh-messages-stream'),
        interim: document.getElementById('vh-interim-box'),
        micBtn: document.getElementById('vh-mic-btn'),
        micHint: document.getElementById('vh-mic-hint'),
        micSubhint: document.getElementById('vh-mic-subhint'),
        wave: document.getElementById('vh-wave-indicator'),
        repeatBtn: document.getElementById('vh-repeat-btn'),
        typedRow: document.getElementById('vh-typed-row'),
        typedInput: document.getElementById('vh-typed-input'),
        typedSend: document.getElementById('vh-typed-send')
      };
    }

    bindControls() {
      // FAB open toggle
      this.dom.fab.addEventListener('click', () => {
        if (this.dom.panel.classList.contains('is-open')) {
          this.close();
        } else {
          this.open();
          if (this.state === States.UNINITIALIZED || this.state === States.IDLE) {
            this.startOnboarding();
          }
        }
      });

      // Header controls
      this.dom.btnRestart.addEventListener('click', () => this.restartConversation());
      this.dom.btnMode.addEventListener('click', () => this.toggleVoiceMode());
      this.dom.btnLang.addEventListener('click', () => this.toggleLangDrawer());
      this.dom.btnSound.addEventListener('click', () => this.toggleSound());
      this.dom.btnMin.addEventListener('click', () => this.minimize());
      this.dom.btnClose.addEventListener('click', () => this.dismiss());

      // Language cards
      this.dom.langDrawer.querySelectorAll('.vh-lang-card').forEach(btn => {
        btn.addEventListener('click', () => {
          const code = btn.dataset.code;
          this.setLanguage(code, true);
          this.dom.langDrawer.classList.remove('is-open');
        });
      });

      // Autoplay unblock button
      this.dom.startVoiceBtn.addEventListener('click', () => {
        this.dom.autoplayBanner.classList.remove('is-visible');
        this.micPermissionGranted = true;
        localStorage.setItem('vh_mic_granted', 'true');
        this.speakCurrentInstruction();
      });

      // Typed Input fallback handling
      if (this.dom.typedSend && this.dom.typedInput) {
        this.dom.typedSend.addEventListener('click', () => this.handleTypedInput());
        this.dom.typedInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            this.handleTypedInput();
          }
        });
      }

      // Mic button (Bug 3: Stop listening or manual speak)
      this.dom.micBtn.addEventListener('click', () => {
        const now = Date.now();
        if (now - this.lastClickTime < 300) return;
        this.lastClickTime = now;

        if (this.isListening) {
          // Explicit Stop Listening
          this.stopListening();
        } else {
          // Manual Voice Input activation
          this.startListening();
        }
      });

      // Repeat button
      this.dom.repeatBtn.addEventListener('click', () => {
        this.speakCurrentInstruction();
      });
    }

    /* ── Voice Services & STT/TTS Layer ───────────────────────────────── */
    initVoiceServices() {
      if (!this.stt || !this.stt.isSupported || !this.stt.isSupported()) {
        this.showTypedFallbackNotice();
        return;
      }

      this.stt.onStateChange = (state) => {
        const VS = window.VoiceHireVoice ? window.VoiceHireVoice.VoiceStates : {};
        if (state === (VS.LISTENING || 'LISTENING')) {
          this.isListening = true;
          this.dom.micBtn.classList.add('is-listening');
          this.dom.statusRing.className = 'vh-header-ring listening';
          this.dom.statusDot.className = 'vh-status-dot listening';
          const listeningText = DIALOGUES.micListening[this.currentLang] || 'Listening...';
          this.dom.statusText.textContent = listeningText;
          this.dom.micHint.textContent = listeningText;
          this.dom.micSubhint.textContent = 'Tap red button to stop';
          this.dom.interim.classList.add('is-active');
          this.dom.interim.textContent = '';
        } else {
          this.isListening = false;
          this.dom.micBtn.classList.remove('is-listening');
          this.dom.statusRing.className = 'vh-header-ring';
          this.dom.statusDot.className = 'vh-status-dot';
          this.dom.statusText.textContent = 'Ready';
          this.dom.micHint.textContent = this.voiceMode === 'hands_free' ? 'Hands-Free Active' : 'Tap to Speak';
          this.dom.micSubhint.textContent = this.voiceMode === 'hands_free' ? 'Auto-listens after speaking' : 'Tap mic when ready';
          this.dom.interim.classList.remove('is-active');
        }
      };

      this.stt.onInterim = (text) => {
        if (this.dom.interim) {
          this.dom.interim.textContent = text;
        }
      };

      this.stt.onFinal = (text, confidence) => {
        if (!text || !text.trim()) return;
        this.stopListening();
        this.processUserUtterance(text.trim(), confidence);
      };

      this.stt.onPermissionDenied = () => {
        const denied = DIALOGUES.micDenied[this.currentLang] || DIALOGUES.micDenied.hi;
        this.addMessage(denied, 'bot');
        this.showTypedFallbackNotice();
      };

      this.stt.onError = (errType, msg) => {
        if (errType !== 'aborted' && errType !== 'canceled') {
          console.warn('[Assistant STT Error]', errType, msg);
        }
      };
    }

    // Bug 3: Hands-Free auto-restart vs Manual Mode
    toggleVoiceMode() {
      if (this.voiceMode === 'hands_free') {
        this.voiceMode = 'manual';
        this.stopListening();
        const notice = (DIALOGUES.manualModeEnabled && (DIALOGUES.manualModeEnabled[this.currentLang] || DIALOGUES.manualModeEnabled.hi)) || "Manual Mode active: Tap the microphone button when you want to speak.";
        this.addMessage(`✋ ${notice}`, 'bot');
        this.speak(notice, this.currentLang);
      } else {
        this.voiceMode = 'hands_free';
        const notice = (DIALOGUES.handsFreeEnabled && (DIALOGUES.handsFreeEnabled[this.currentLang] || DIALOGUES.handsFreeEnabled.hi)) || "Hands-Free Mode active: Microphone will listen automatically after the assistant speaks.";
        this.addMessage(`🎧 ${notice}`, 'bot');
        this.speak(notice, this.currentLang);
      }
      localStorage.setItem('vh_voice_mode', this.voiceMode);
      this.updateModeButtonUI();
      this.saveSession();
    }

    updateModeButtonUI() {
      if (!this.dom.btnMode) return;
      if (this.voiceMode === 'hands_free') {
        this.dom.btnMode.classList.add('active');
        this.dom.btnMode.innerHTML = '<i class="fa-solid fa-headset"></i>';
        this.dom.btnMode.title = 'Hands-Free Mode Active (Click to switch to Manual)';
        this.dom.micHint.textContent = 'Hands-Free Active';
        this.dom.micSubhint.textContent = 'Auto-listens after speaking';
      } else {
        this.dom.btnMode.classList.remove('active');
        this.dom.btnMode.innerHTML = '<i class="fa-solid fa-hand"></i>';
        this.dom.btnMode.title = 'Manual Mode Active (Click to switch to Hands-Free)';
        this.dom.micHint.textContent = 'Tap to Speak';
        this.dom.micSubhint.textContent = 'Tap mic when ready';
      }
    }

    startListening() {
      if (this.isSpeaking || this.isProcessing) return;
      if (this.isMuted) return;

      // Sensitive input guard: never listen when focused on password or OTP
      if (this.isFocusedOnSensitiveField()) return;

      if (!this.stt || !this.stt.isSupported || !this.stt.isSupported()) {
        this.showTypedFallbackNotice();
        return;
      }
      this.micPermissionGranted = true;
      localStorage.setItem('vh_mic_granted', 'true');
      this.stt.start(this.currentLang);
    }

    stopListening() {
      if (this.stt && this.stt.stop) {
        this.stt.stop();
      }
      this.isListening = false;
      this.dom.micBtn.classList.remove('is-listening');
      this.dom.statusRing.className = 'vh-header-ring';
      this.dom.statusDot.className = 'vh-status-dot';
      this.dom.statusText.textContent = 'Ready';
      this.dom.interim.classList.remove('is-active');
    }

    cancelVoice() {
      if (this.stt && this.stt.cancel) this.stt.cancel();
      if (this.tts && this.tts.cancel) this.tts.cancel();
      this.stopListening();
      this.stopSpeaking();
    }

    speak(text, langCode) {
      if (!text || this.isMuted) return Promise.resolve();

      this.stopListening();
      this.isSpeaking = true;
      this.updateSpeakingIndicators(true);

      const chosenLang = langCode || this.currentLang || 'hi';

      return new Promise((resolve) => {
        if (this.tts && this.tts.speak) {
          this.tts.speak(text, chosenLang).then(() => {
            this.handleSpeechCompleted();
            resolve();
          }).catch((err) => {
            if (err === 'autoplay_blocked') {
              this.showAutoplayBlockedBanner();
            }
            this.handleSpeechCompleted();
            resolve();
          });
        } else {
          this.handleSpeechCompleted();
          resolve();
        }
      });
    }

    // Bug 3: Trigger hands-free auto-listening after speech completes
    handleSpeechCompleted() {
      this.isSpeaking = false;
      this.updateSpeakingIndicators(false);

      if (this.voiceMode === 'hands_free' && !this.isMuted && !this.isProcessing) {
        // Echo cancellation delay: allow room audio to settle before opening mic
        setTimeout(() => {
          if (!this.isSpeaking && !this.isProcessing && this.dom.panel.classList.contains('is-open')) {
            this.startListening();
          }
        }, 350);
      }
    }

    speakCurrentInstruction() {
      if (this.lastInstruction) {
        this.speak(this.lastInstruction, this.currentLang);
      }
    }

    stopSpeaking() {
      if (this.tts && this.tts.cancel) {
        this.tts.cancel();
      }
      this.isSpeaking = false;
      this.updateSpeakingIndicators(false);
    }

    setupSensitiveInputProtection() {
      // Rule 8 & Security: Pause voice & stop microphone when touching password/OTP fields
      document.addEventListener('focusin', (e) => {
        const target = e.target;
        if (!target) return;
        const type = (target.getAttribute('type') || '').toLowerCase();
        const id = (target.id || '').toLowerCase();
        const name = (target.name || '').toLowerCase();
        const isSensitive = type === 'password' || id.includes('password') || id.includes('otp') || id.includes('pin') ||
                            name.includes('password') || name.includes('otp') || name.includes('pin');
        if (isSensitive) {
          this.stopListening();
          this.stopSpeaking();
          this.updateStatus('Sensitive Field (Voice Paused)', 'processing');
        }
      }, true);

      document.addEventListener('focusout', (e) => {
        const target = e.target;
        if (!target) return;
        const type = (target.getAttribute('type') || '').toLowerCase();
        if (type === 'password') {
          this.updateStatus('Ready', 'ready');
        }
      }, true);
    }

    isFocusedOnSensitiveField() {
      const el = document.activeElement;
      if (!el) return false;
      const type = (el.getAttribute('type') || '').toLowerCase();
      const id = (el.id || '').toLowerCase();
      const name = (el.name || '').toLowerCase();
      return type === 'password' || id.includes('password') || id.includes('otp') || id.includes('pin') ||
             name.includes('password') || name.includes('otp') || name.includes('pin');
    }

    /* ── Conversational Orchestration & Utterance Processing ─────────── */
    handleTypedInput() {
      if (!this.dom.typedInput) return;
      const text = this.dom.typedInput.value.trim();
      if (!text) return;
      this.dom.typedInput.value = '';
      this.processUserUtterance(text, 1.0);
    }

    processUserUtterance(text, confidence = 1.0) {
      if (!text) return;
      this.addMessage(text, 'user');
      this.saveSession();

      // State machine branching
      if (this.state === States.GREETING || this.state === States.LANGUAGE_SELECT) {
        this.handleLanguageChoiceUtterance(text);
      } else if (this.state === States.ROLE_SELECT) {
        this.handleRoleChoiceUtterance(text);
      } else if (this.state === States.ACTION_SELECT) {
        this.handleActionChoiceUtterance(text);
      } else if (this.state === States.COLLECTING_PROFILE_FIELDS && this.workerProfilePendingField) {
        this.handleWorkerProfileAnswer(text);
      } else if (this.state === States.AWAITING_PROFILE_CONFIRMATION) {
        this.handleProfileConfirmationAnswer(text);
      } else {
        // General conversational turn through Orchestration Engine API
        this.executeGeneralVoiceIntent(text, confidence);
      }
    }

    /* ── Phase 14.1 Worker Profile Creation & Completion (Bug 2) ─────── */
    async checkWorkerProfileOnServer() {
      this.updateStatus('Checking Profile...', 'processing');

      try {
        const res = await fetch('/api/worker/profile', {
          headers: { 'Accept': 'application/json' }
        });
        const data = await res.json();

        if (res.status === 404 || (data && data.exists === false)) {
          // No profile row exists yet: initiate creation!
          this.state = States.COLLECTING_PROFILE_FIELDS;
          const greeting = DIALOGUES.workerProfileGreeting[this.currentLang] || DIALOGUES.workerProfileGreeting.hi;
          this.addMessage(greeting, 'bot');
          this.speak(greeting, this.currentLang).then(() => {
            this.askNextWorkerProfileField();
          });
          return;
        }

        if (res.ok && data) {
          // Profile exists: inspect mandatory attributes
          this.workerProfile = {
            name: data.name || '',
            work: data.work || '',
            location: data.location || '',
            price: data.price ? String(data.price) : '',
            experience_years: data.experience_years ? String(data.experience_years) : '',
            bio: data.bio || '',
            isComplete: (data.completeness && data.completeness.score >= 50),
            isConfirmed: Boolean(data.is_available)
          };

          // Update visible dashboard progress bar and checklist if present on page
          this.syncDashboardDOM(data);

          const missingField = this.findMissingMandatoryField();
          if (missingField) {
            this.state = States.COLLECTING_PROFILE_FIELDS;
            const msg = this.currentLang === 'hi' 
              ? "आपकी प्रोफ़ाइल में कुछ ज़रूरी विवरण बाकी हैं। आइए इन्हें पूरा करते हैं।"
              : "Some mandatory details are missing from your profile. Let's complete them.";
            this.addMessage(msg, 'bot');
            this.speak(msg, this.currentLang).then(() => {
              this.askWorkerProfileField(missingField);
            });
          } else {
            // Profile is already complete!
            this.state = States.DASHBOARD_GUIDANCE;
            this.workerProfile.isComplete = true;
            const readyMsg = DIALOGUES.profileCompleteCelebration[this.currentLang] || DIALOGUES.profileCompleteCelebration.hi;
            this.addMessage(`🎉 ${readyMsg}`, 'bot');
            this.showProfileSummaryCard(true);
            this.speak(readyMsg, this.currentLang);
          }
        }
      } catch (err) {
        console.warn('[Assistant Profile Check Error]', err);
        // Fallback: start interactive collection
        this.state = States.COLLECTING_PROFILE_FIELDS;
        this.askNextWorkerProfileField();
      }
      this.saveSession();
    }

    findMissingMandatoryField() {
      const order = ['name', 'work', 'location', 'price', 'experience_years'];
      for (const field of order) {
        const val = this.workerProfile[field];
        if (!val || val === 'New Worker' || val === 'General Helper' || val === '0' || val === 0) {
          return field;
        }
      }
      return null;
    }

    askNextWorkerProfileField() {
      const field = this.findMissingMandatoryField();
      if (!field) {
        // All fields gathered: show summary and request explicit confirmation
        this.showProfileSummaryAndConfirm();
      } else {
        this.askWorkerProfileField(field);
      }
    }

    askWorkerProfileField(field, doSpeak = true) {
      this.workerProfilePendingField = field;
      this.state = States.COLLECTING_PROFILE_FIELDS;

      let question = '';
      if (field === 'name') question = DIALOGUES.askName[this.currentLang] || DIALOGUES.askName.hi;
      else if (field === 'work') question = DIALOGUES.askTrade[this.currentLang] || DIALOGUES.askTrade.hi;
      else if (field === 'location') question = DIALOGUES.askLocation[this.currentLang] || DIALOGUES.askLocation.hi;
      else if (field === 'price') question = DIALOGUES.askPrice[this.currentLang] || DIALOGUES.askPrice.hi;
      else if (field === 'experience_years') question = DIALOGUES.askExperience[this.currentLang] || DIALOGUES.askExperience.hi;

      this.addMessage(question, 'bot');
      this.lastInstruction = question;
      this.saveSession();

      if (doSpeak) {
        this.speak(question, this.currentLang);
      }
    }

    async handleWorkerProfileAnswer(answer) {
      const field = this.workerProfilePendingField;
      if (!field) return;

      this.isProcessing = true;
      this.updateStatus('Saving to Server...', 'processing');

      let cleanVal = answer.trim();
      let updatePayload = {};

      if (field === 'name') {
        cleanVal = cleanVal.replace(/mera naam|my name is/i, '').trim();
        if (cleanVal.length < 2) {
          this.isProcessing = false;
          const retryMsg = this.currentLang === 'hi' ? "कृपया अपना सही नाम बताएँ।" : "Please provide a valid full name.";
          this.addMessage(retryMsg, 'bot');
          this.speak(retryMsg, this.currentLang);
          return;
        }
        updatePayload.name = cleanVal;
      } else if (field === 'work') {
        const detected = detectTradeFromText(cleanVal);
        cleanVal = detected || cleanVal;
        updatePayload.work = cleanVal;
        updatePayload.trade = cleanVal;
      } else if (field === 'location') {
        cleanVal = cleanVal.replace(/main|me rehta hu|locality|city/i, '').trim();
        updatePayload.location = cleanVal;
      } else if (field === 'price') {
        const num = extractDigits(cleanVal);
        if (!num || num <= 0) {
          this.isProcessing = false;
          const retryMsg = this.currentLang === 'hi' ? "कृपया अंकों में अपनी दिहाड़ी बताएँ, जैसे 500 रुपये।" : "Please specify your daily rate in numbers, e.g. 500.";
          this.addMessage(retryMsg, 'bot');
          this.speak(retryMsg, this.currentLang);
          return;
        }
        cleanVal = String(num);
        updatePayload.price = num;
      } else if (field === 'experience_years') {
        const num = extractDigits(cleanVal) || 1;
        cleanVal = String(num);
        updatePayload.experience_years = num;
      }

      try {
        // Authorized Server-Side Persistence (Bug 2)
        const res = await fetch('/api/worker/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(updatePayload)
        });
        const data = await res.json();

        if (res.ok) {
          this.workerProfile[field] = cleanVal;
          if (field === 'work') this.workerProfile.trade = cleanVal;

          // Verify saved response and update UI
          const savedBadge = `<span class="vh-saved-badge"><i class="fa-solid fa-check"></i> ${DIALOGUES.fieldSaved[this.currentLang] || 'Saved'}</span>`;
          this.addMessage(`${cleanVal} ${savedBadge}`, 'bot');

          // Sync with visible form inputs if present on page
          this.syncFormFieldDOM(field, cleanVal);
          if (data.completeness) {
            this.syncDashboardDOM(data);
          }

          this.isProcessing = false;
          this.saveSession();

          // Move to next missing field
          this.askNextWorkerProfileField();
        } else {
          this.isProcessing = false;
          const errText = data.error || 'Server error saving detail.';
          this.addMessage(`⚠️ ${errText}`, 'bot');
          this.speak(errText, this.currentLang);
        }
      } catch (e) {
        this.isProcessing = false;
        console.error('[Worker Profile Save Error]', e);
        const errMsg = this.currentLang === 'hi' ? "सर्वर से संपर्क नहीं हो पाया। पुनः प्रयास करें।" : "Network error. Please try again.";
        this.addMessage(errMsg, 'bot');
        this.speak(errMsg, this.currentLang);
      }
    }

    showProfileSummaryAndConfirm(doSpeak = true) {
      this.state = States.AWAITING_PROFILE_CONFIRMATION;
      this.workerProfilePendingField = null;

      const card = document.createElement('div');
      card.className = 'vh-profile-summary-card';
      card.innerHTML = `
        <div class="vh-summary-title">📋 ${this.currentLang === 'hi' ? 'आपकी प्रोफ़ाइल का सारांश' : 'Profile Summary'}</div>
        <div class="vh-summary-row"><strong>नाम (Name):</strong> <span>${this.workerProfile.name || '—'}</span></div>
        <div class="vh-summary-row"><strong>काम (Trade):</strong> <span>${this.workerProfile.work || this.workerProfile.trade || '—'}</span></div>
        <div class="vh-summary-row"><strong>इलाका (Area):</strong> <span>${this.workerProfile.location || '—'}</span></div>
        <div class="vh-summary-row"><strong>दर (Daily Rate):</strong> <span>₹${this.workerProfile.price || '500'}/day</span></div>
        <div class="vh-summary-row"><strong>अनुभव (Experience):</strong> <span>${this.workerProfile.experience_years || '1'} वर्ष (Years)</span></div>
        <div class="vh-summary-actions">
          <button class="vh-choice-btn primary" id="vh-confirm-profile-btn" style="flex:1;">
            <i class="fa-solid fa-check"></i> ${this.currentLang === 'hi' ? 'हाँ, पक्का करें (Confirm)' : 'Confirm & Publish'}
          </button>
          <button class="vh-choice-btn" id="vh-edit-profile-btn">
            <i class="fa-solid fa-pen"></i> ${this.currentLang === 'hi' ? 'बदलें (Edit)' : 'Edit'}
          </button>
        </div>
      `;

      this.dom.messages.appendChild(card);
      this.scrollToBottom();

      card.querySelector('#vh-confirm-profile-btn').addEventListener('click', () => {
        this.confirmAndActivateWorkerProfile();
      });

      card.querySelector('#vh-edit-profile-btn').addEventListener('click', () => {
        this.workerProfile.name = '';
        this.askNextWorkerProfileField();
      });

      const prompt = DIALOGUES.profileConfirmPrompt[this.currentLang] || DIALOGUES.profileConfirmPrompt.hi;
      this.lastInstruction = prompt;
      this.saveSession();

      if (doSpeak) {
        this.speak(prompt, this.currentLang);
      }
    }

    handleProfileConfirmationAnswer(answer) {
      const lower = answer.toLowerCase();
      if (/haan|ha|yes|theek|sahi|confirm|pakka|kar do|proceed|done/.test(lower)) {
        this.confirmAndActivateWorkerProfile();
      } else if (/nahi|na|no|cancel|badlo|change|galat/.test(lower)) {
        const msg = this.currentLang === 'hi' ? "ठीक है, आप क्या बदलना चाहते हैं?" : "Okay, what detail would you like to edit?";
        this.addMessage(msg, 'bot');
        this.speak(msg, this.currentLang);
        this.workerProfile.name = '';
        this.askNextWorkerProfileField();
      } else {
        const prompt = DIALOGUES.profileConfirmPrompt[this.currentLang] || DIALOGUES.profileConfirmPrompt.hi;
        this.speak(prompt, this.currentLang);
      }
    }

    async confirmAndActivateWorkerProfile() {
      this.isProcessing = true;
      this.updateStatus('Publishing Profile...', 'processing');

      try {
        const res = await fetch('/api/worker/profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            is_available: true,
            is_published: true
          })
        });
        const data = await res.json();

        this.isProcessing = false;
        this.state = States.PROFILE_COMPLETE;
        this.workerProfile.isComplete = true;
        this.workerProfile.isConfirmed = true;

        const celebration = DIALOGUES.profileCompleteCelebration[this.currentLang] || DIALOGUES.profileCompleteCelebration.hi;
        this.addMessage(`🎉 ${celebration}`, 'bot');
        this.speak(celebration, this.currentLang);

        if (data.completeness) {
          this.syncDashboardDOM(data);
        }

        this.saveSession();

        // If not already on worker dashboard, navigate to it to showcase saved status
        if (window.location.pathname !== '/dashboard/worker') {
          setTimeout(() => {
            window.location.href = '/dashboard/worker';
          }, 1500);
        } else {
          this.state = States.DASHBOARD_GUIDANCE;
          this.saveSession();
        }
      } catch (err) {
        this.isProcessing = false;
        console.error('[Worker Profile Publish Error]', err);
      }
    }

    syncFormFieldDOM(field, val) {
      const selectors = [
        `input[name="${field}"]`, `input[id="${field}"]`,
        `select[name="${field}"]`, `select[id="${field}"]`,
        `textarea[name="${field}"]`, `textarea[id="${field}"]`
      ];
      selectors.forEach(sel => {
        const el = document.querySelector(sel);
        if (el) {
          el.value = val;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
    }

    syncDashboardDOM(data) {
      if (!data) return;
      const comp = data.completeness || {};
      const score = comp.score || data.profile_completeness || 100;

      const badge = document.getElementById('wp-completeness-badge');
      if (badge) badge.textContent = `${score}%`;

      const fill = document.getElementById('wp-completeness-fill');
      if (fill) fill.style.width = `${score}%`;

      const listContainer = document.getElementById('wp-completeness-checklist');
      if (listContainer && Array.isArray(comp.checklist)) {
        listContainer.innerHTML = comp.checklist.map(item => `
          <div style="background:${item.completed ? '#D1FAE5' : '#F1F5F9'}; color:${item.completed ? '#065F46' : '#64748B'}; padding:4px 8px; border-radius:6px; font-weight:500;">
            <i class="fa-solid ${item.completed ? 'fa-check' : 'fa-clock'} mr-1"></i> ${item.item}
          </div>
        `).join('');
      }
    }

    showProfileSummaryCard(isFinal = false) {
      const card = document.createElement('div');
      card.className = 'vh-profile-summary-card';
      card.innerHTML = `
        <div class="vh-summary-title">
          <i class="fa-solid fa-circle-check text-success"></i> ${this.currentLang === 'hi' ? 'सक्रिय प्रोफ़ाइल' : 'Active Profile'}
        </div>
        <div class="vh-summary-row"><strong>नाम (Name):</strong> <span>${this.workerProfile.name || 'Worker'}</span></div>
        <div class="vh-summary-row"><strong>काम (Trade):</strong> <span>${this.workerProfile.work || this.workerProfile.trade || 'General'}</span></div>
        <div class="vh-summary-row"><strong>स्थान (Area):</strong> <span>${this.workerProfile.location || 'Delhi NCR'}</span></div>
        <div class="vh-summary-row"><strong>रेट (Rate):</strong> <span>₹${this.workerProfile.price || '500'}/day</span></div>
        <div class="vh-summary-row"><strong>स्थिति (Status):</strong> <span class="badge badge-success" style="background:#10B981;color:#fff;padding:2px 6px;border-radius:4px;font-size:0.75rem;">Active & Visible</span></div>
      `;
      this.dom.messages.appendChild(card);
      this.scrollToBottom();
    }

    /* ── Initial Onboarding Sequence (Gateway / First Visit) ─────────── */
    startOnboarding() {
      this.setState(States.GREETING);
      const greetingHi = DIALOGUES.greeting.hi;
      this.addMessage(greetingHi, 'bot');
      this.lastInstruction = greetingHi;

      this.speak(greetingHi, 'hi').then(() => {
        this.showLanguageSelection();
      });
    }

    showLanguageSelection() {
      this.setState(States.LANGUAGE_SELECT);
      const askText = DIALOGUES.askLanguage.hi;
      this.addMessage(askText, 'bot');
      this.lastInstruction = askText;

      const choicesContainer = document.createElement('div');
      choicesContainer.className = 'vh-choices';

      const orderedCodes = ['hi', 'pa', 'en', 'bn', 'mr', 'ta', 'te', 'gu', 'kn', 'ml', 'or', 'ur'];
      const grid = document.createElement('div');
      grid.style.cssText = 'display:grid; grid-template-columns: repeat(2, 1fr); gap: 8px; margin-top: 6px;';

      orderedCodes.forEach(code => {
        const lang = LANGUAGES[code];
        if (!lang) return;
        const btn = document.createElement('button');
        btn.className = `vh-choice-btn ${code === this.currentLang ? 'primary' : ''}`;
        btn.innerHTML = `
          <div class="vh-choice-icon">${lang.flag}</div>
          <div class="vh-choice-content">
            <span class="vh-choice-title">${lang.native}</span>
            <span class="vh-choice-sub">${lang.name}</span>
          </div>
        `;
        btn.addEventListener('click', () => {
          this.addMessage(`${lang.flag} ${lang.native} (${lang.name})`, 'user');
          this.setLanguage(code, false);
          const confirmText = DIALOGUES.langConfirmed[code] || DIALOGUES.langConfirmed.hi;
          this.addMessage(confirmText, 'bot');
          this.speak(confirmText, code).then(() => {
            this.showRoleSelection();
          });
        });
        grid.appendChild(btn);
      });

      choicesContainer.appendChild(grid);
      this.dom.messages.appendChild(choicesContainer);
      this.scrollToBottom();

      this.speak(askText, 'hi');
    }

    handleLanguageChoiceUtterance(text) {
      const lower = text.toLowerCase();
      for (const [code, meta] of Object.entries(LANGUAGES)) {
        if (lower.includes(meta.name.toLowerCase()) || lower.includes(meta.native.toLowerCase()) || lower === code) {
          this.setLanguage(code, false);
          const confirmText = DIALOGUES.langConfirmed[code] || DIALOGUES.langConfirmed.hi;
          this.addMessage(confirmText, 'bot');
          this.speak(confirmText, code).then(() => {
            this.showRoleSelection();
          });
          return;
        }
      }
      // If language not cleanly resolved, fall back to general intent
      this.executeGeneralVoiceIntent(text);
    }

    showRoleSelection() {
      this.setState(States.ROLE_SELECT);
      const lang = this.currentLang;
      const askRoleText = DIALOGUES.askRole[lang] || DIALOGUES.askRole.hi;
      this.addMessage(askRoleText, 'bot');
      this.lastInstruction = askRoleText;

      const workerTitle = DIALOGUES.roleWorker[lang] || DIALOGUES.roleWorker.hi;
      const workerSub   = DIALOGUES.roleWorkerSub[lang] || DIALOGUES.roleWorkerSub.hi;
      const custTitle   = DIALOGUES.roleCustomer[lang] || DIALOGUES.roleCustomer.hi;
      const custSub     = DIALOGUES.roleCustomerSub[lang] || DIALOGUES.roleCustomerSub.hi;

      const choices = document.createElement('div');
      choices.className = 'vh-choices';

      const btnWorker = document.createElement('button');
      btnWorker.className = 'vh-choice-btn primary';
      btnWorker.innerHTML = `
        <div class="vh-choice-icon">👷</div>
        <div class="vh-choice-content">
          <span class="vh-choice-title">${workerTitle}</span>
          <span class="vh-choice-sub">${workerSub}</span>
        </div>
      `;
      btnWorker.addEventListener('click', () => {
        this.selectedRole = 'worker';
        this.addMessage(workerTitle, 'user');
        this.showActionSelection();
      });

      const btnCustomer = document.createElement('button');
      btnCustomer.className = 'vh-choice-btn primary';
      btnCustomer.innerHTML = `
        <div class="vh-choice-icon">🏢</div>
        <div class="vh-choice-content">
          <span class="vh-choice-title">${custTitle}</span>
          <span class="vh-choice-sub">${custSub}</span>
        </div>
      `;
      btnCustomer.addEventListener('click', () => {
        this.selectedRole = 'user';
        this.addMessage(custTitle, 'user');
        this.showActionSelection();
      });

      choices.appendChild(btnWorker);
      choices.appendChild(btnCustomer);
      this.dom.messages.appendChild(choices);
      this.scrollToBottom();

      this.speak(askRoleText, lang);
    }

    handleRoleChoiceUtterance(text) {
      const lower = text.toLowerCase();
      if (/worker|kaam|rozgar|naukri|mistri|plumber|electrician|helper/.test(lower)) {
        this.selectedRole = 'worker';
        const title = DIALOGUES.roleWorker[this.currentLang] || 'Worker';
        this.showActionSelection();
      } else if (/customer|maalik|booking|hire|bulao|chahiye/.test(lower)) {
        this.selectedRole = 'user';
        this.showActionSelection();
      } else {
        this.executeGeneralVoiceIntent(text);
      }
    }

    showActionSelection() {
      this.setState(States.ACTION_SELECT);
      const lang = this.currentLang;
      const askActionText = DIALOGUES.askAction[lang] || DIALOGUES.askAction.hi;
      this.addMessage(askActionText, 'bot');
      this.lastInstruction = askActionText;

      const loginTitle = DIALOGUES.actionLogin[lang] || DIALOGUES.actionLogin.hi;
      const loginSub   = DIALOGUES.actionLoginSub[lang] || DIALOGUES.actionLoginSub.hi;
      const regTitle   = DIALOGUES.actionRegister[lang] || DIALOGUES.actionRegister.hi;
      const regSub     = DIALOGUES.actionRegisterSub[lang] || DIALOGUES.actionRegisterSub.hi;

      const choices = document.createElement('div');
      choices.className = 'vh-choices';

      const btnLogin = document.createElement('button');
      btnLogin.className = 'vh-choice-btn';
      btnLogin.innerHTML = `
        <div class="vh-choice-icon">🔑</div>
        <div class="vh-choice-content">
          <span class="vh-choice-title">${loginTitle}</span>
          <span class="vh-choice-sub">${loginSub}</span>
        </div>
      `;
      btnLogin.addEventListener('click', () => {
        this.selectedAction = 'login';
        this.addMessage(loginTitle, 'user');
        this.navigateToTargetPage();
      });

      const btnRegister = document.createElement('button');
      btnRegister.className = 'vh-choice-btn primary';
      btnRegister.innerHTML = `
        <div class="vh-choice-icon">✨</div>
        <div class="vh-choice-content">
          <span class="vh-choice-title">${regTitle}</span>
          <span class="vh-choice-sub">${regSub}</span>
        </div>
      `;
      btnRegister.addEventListener('click', () => {
        this.selectedAction = 'register';
        this.addMessage(regTitle, 'user');
        this.navigateToTargetPage();
      });

      choices.appendChild(btnLogin);
      choices.appendChild(btnRegister);
      this.dom.messages.appendChild(choices);
      this.scrollToBottom();

      this.speak(askActionText, lang);
    }

    handleActionChoiceUtterance(text) {
      const lower = text.toLowerCase();
      if (/login|pehle|purana|sign in|already/.test(lower)) {
        this.selectedAction = 'login';
        this.navigateToTargetPage();
      } else if (/naya|register|signup|create|new/.test(lower)) {
        this.selectedAction = 'register';
        this.navigateToTargetPage();
      } else {
        this.executeGeneralVoiceIntent(text);
      }
    }

    navigateToTargetPage() {
      this.setState(States.NAVIGATING);
      const lang = this.currentLang;
      const navText = DIALOGUES.navigating[lang] || DIALOGUES.navigating.hi;
      this.addMessage(navText, 'bot');

      let targetUrl = '/';
      const role = this.selectedRole || 'worker';

      if (this.selectedAction === 'login') {
        targetUrl = `/login?role=${role}`;
      } else {
        targetUrl = role === 'worker' ? '/signup/worker' : '/signup/user';
      }

      this.saveSession();

      this.speak(navText, lang).finally(() => {
        setTimeout(() => {
          window.location.href = targetUrl;
        }, 400);
      });
    }

    /* ── General Intent API Bridge ────────────────────────────────────── */
    async executeGeneralVoiceIntent(text, confidence = 1.0) {
      if (!text) return;

      this.isProcessing = true;
      this.updateStatus('Thinking...', 'processing');

      let turn = null;
      if (window.VoiceHireVoice && window.VoiceHireVoice.VoiceIntentService && window.VoiceHireVoice.VoiceIntentService.orchestrateTurn) {
        turn = await window.VoiceHireVoice.VoiceIntentService.orchestrateTurn(
          text,
          this.state || 'greeting',
          this.currentLang
        );
      }

      this.isProcessing = false;
      this.updateStatus('Ready', 'ready');

      if (!turn) return;

      const displayMsg = turn.display_text || turn.speech_response;
      if (displayMsg) {
        this.addMessage(displayMsg, 'bot');
        this.lastInstruction = displayMsg;
      }

      const speechMsg = turn.speech_response || displayMsg;
      if (speechMsg) {
        this.speak(speechMsg, this.currentLang);
      }

      if (turn.current_state) {
        this.state = turn.current_state;
      }

      const action = turn.action;
      const args = turn.action_arguments || {};

      if (action === 'select_language' && args.language) {
        this.setLanguage(args.language, false);
      }
      if (action === 'select_role' && args.role) {
        this.selectedRole = args.role;
      }
      if (action === 'set_form_field' && args.field_name && args.value) {
        this.syncFormFieldDOM(args.field_name, args.value);
      }

      this.saveSession();
    }

    /* ── UI Utilities ─────────────────────────────────────────────────── */
    addMessage(text, sender = 'bot') {
      this.messagesHistory.push({ text, sender });
      this.renderBubbleToDOM(text, sender);
      this.scrollToBottom();
    }

    renderBubbleToDOM(text, sender = 'bot') {
      if (!this.dom.messages) return;
      const bubble = document.createElement('div');
      bubble.className = `vh-bubble ${sender}`;
      bubble.innerHTML = text;
      this.dom.messages.appendChild(bubble);
    }

    clearMessagesDOM() {
      if (this.dom.messages) this.dom.messages.innerHTML = '';
    }

    scrollToBottom() {
      if (this.dom.messages) {
        this.dom.messages.scrollTop = this.dom.messages.scrollHeight;
      }
    }

    setState(newState) {
      this.state = newState;
      this.saveSession();
    }

    updateSpeakingIndicators(speaking) {
      if (speaking) {
        this.dom.statusRing.className = 'vh-header-ring speaking';
        this.dom.statusDot.className = 'vh-status-dot speaking';
        this.dom.statusText.textContent = 'Speaking...';
        this.dom.wave.classList.add('is-active');
      } else {
        this.dom.statusRing.className = 'vh-header-ring';
        this.dom.statusDot.className = 'vh-status-dot';
        this.dom.statusText.textContent = 'Ready';
        this.dom.wave.classList.remove('is-active');
      }
    }

    updateStatus(text, type = 'ready') {
      if (!this.dom.statusText) return;
      this.dom.statusText.textContent = text;
      this.dom.statusDot.className = `vh-status-dot ${type}`;
    }

    setLanguage(code, announce = false) {
      if (!LANGUAGES[code]) return;
      this.currentLang = code;
      localStorage.setItem('vh_lang', code);

      // Set cookie for server sync
      document.cookie = `voicehire_lang=${code}; path=/; max-age=2592000; SameSite=Lax`;

      // Synchronize with server session & database via AJAX
      try {
        fetch('/set_lang/' + encodeURIComponent(code), {
          headers: { 'Accept': 'application/json' }
        }).catch(() => {});
      } catch (e) {}

      // Synchronize global window.VH
      if (window.VH) {
        window.VH.lang = code;
      }

      // Update navbar language label if present
      const langLabel = document.getElementById('current-lang-label');
      if (langLabel) {
        langLabel.textContent = (code || 'hi').toUpperCase();
      }

      // Update drawer cards
      if (this.dom.langDrawer) {
        this.dom.langDrawer.querySelectorAll('.vh-lang-card').forEach(c => {
          c.classList.toggle('selected', c.dataset.code === code);
        });
      }

      // Live-translate current page elements without reload
      this.liveTranslatePage(code);

      if (announce) {
        const confirmText = DIALOGUES.langConfirmed[code] || DIALOGUES.langConfirmed.hi;
        this.addMessage(confirmText, 'bot');
        this.speak(confirmText, code);
      }
      this.saveSession();
    }

    liveTranslatePage(code) {
      if (!code || typeof document === 'undefined' || typeof window === 'undefined' || !window.location || !window.location.origin) return;
      const url = window.location.origin + '/api/translations?lang=' + encodeURIComponent(code);
      fetch(url)
        .then(res => res.json())
        .then(data => {
          if (!data || !data.translations) return;
          const tr = data.translations;

          // 1. Elements with data-i18n
          document.querySelectorAll('[data-i18n]').forEach(el => {
            const k = el.getAttribute('data-i18n');
            if (tr[k]) {
              if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') el.placeholder = tr[k];
              else el.textContent = tr[k];
            }
          });

          // 2. Headings, labels, buttons, links, paragraphs (skip assistant widget)
          const candidates = document.querySelectorAll('h1, h2, h3, h4, h5, p, span, a, label, button, .section-label, .hero-badge, .nav-item, .stat-label, .step-card p, .trust-item p, .feature-card p');
          candidates.forEach(el => {
            if (el.closest('#vh-assistant-root')) return;
            if (el.children.length === 0) {
              if (!el.getAttribute('data-i18n-src')) {
                const initialText = el.textContent.trim();
                if (initialText) el.setAttribute('data-i18n-src', initialText);
              }
              const srcKey = el.getAttribute('data-i18n-src');
              if (srcKey && tr[srcKey]) {
                el.textContent = tr[srcKey];
              }
            }
          });

          // 3. Inputs with placeholders
          document.querySelectorAll('input[placeholder], textarea[placeholder]').forEach(el => {
            if (el.closest('#vh-assistant-root')) return;
            if (!el.getAttribute('data-i18n-p-src')) {
              const p = el.getAttribute('placeholder');
              if (p) el.setAttribute('data-i18n-p-src', p.trim());
            }
            const pKey = el.getAttribute('data-i18n-p-src');
            if (pKey && tr[pKey]) {
              el.setAttribute('placeholder', tr[pKey]);
            }
          });
        })
        .catch(e => console.warn('[VoiceHire Live Translate Error]', e));
    }

    toggleLangDrawer() {
      this.dom.langDrawer.classList.toggle('is-open');
    }

    toggleSound() {
      this.isMuted = !this.isMuted;
      localStorage.setItem('vh_muted', this.isMuted ? 'true' : 'false');
      if (this.isMuted) {
        this.stopSpeaking();
        this.stopListening();
        this.dom.btnSound.classList.add('active');
        this.dom.btnSound.innerHTML = '<i class="fa-solid fa-volume-xmark"></i>';
        this.dom.btnSound.title = 'Unmute Voice';
      } else {
        this.dom.btnSound.classList.remove('active');
        this.dom.btnSound.innerHTML = '<i class="fa-solid fa-volume-high"></i>';
        this.dom.btnSound.title = 'Mute Voice';
        this.speakCurrentInstruction();
      }
      this.saveSession();
    }

    showAutoplayBlockedBanner() {
      this.dom.autoplayBanner.classList.add('is-visible');
      const text = DIALOGUES.autoplayBlockedMsg[this.currentLang] || DIALOGUES.autoplayBlockedMsg.hi;
      const btnText = DIALOGUES.startVoiceBtn[this.currentLang] || DIALOGUES.startVoiceBtn.hi;
      this.dom.autoplayText.textContent = text;
      this.dom.startVoiceBtn.innerHTML = btnText;
    }

    showTypedFallbackNotice() {
      if (this.dom.typedInput) {
        if (typeof this.dom.typedInput.focus === 'function') {
          this.dom.typedInput.focus();
        }
        if (this.dom.micSubhint) {
          this.dom.micSubhint.textContent = 'Please type below';
        }
      }
    }

    open() {
      this.dom.panel.classList.add('is-open');
      this.dom.panel.setAttribute('aria-hidden', 'false');
    }

    minimize() {
      this.stopSpeaking();
      this.stopListening();
      this.dom.panel.classList.remove('is-open');
      this.dom.panel.setAttribute('aria-hidden', 'true');
    }

    close() {
      this.minimize();
    }

    dismiss() {
      this.close();
      sessionStorage.setItem('vh_dismissed', 'true');
    }
  }

  /* ── Initialize Assistant on DOM Ready ──────────────────────────────── */
  function bootAssistant() {
    window.VHAssistant = new VoiceHireAssistant();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootAssistant);
  } else {
    bootAssistant();
  }

  // Export class for Node.js automated testing
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      VoiceHireAssistant: VoiceHireAssistant,
      States: States,
      LANGUAGES: LANGUAGES,
      DIALOGUES: DIALOGUES,
      TRADE_MAP: TRADE_MAP,
      detectTradeFromText: detectTradeFromText,
      extractDigits: extractDigits
    };
  }

})();
