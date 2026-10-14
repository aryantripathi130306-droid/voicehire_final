/**
 * VoiceHire — Unified Voice Assistant & Onboarding Shell
 * ═══════════════════════════════════════════════════════════════════════════
 * Complies with Master Engineering Rules (Rule 1-14):
 *  - High-accessibility voice & visual onboarding for informal workforce.
 *  - Browser Web Speech API (SpeechRecognition + SpeechSynthesis).
 *  - Handles audio autoplay blocking with non-intrusive activation button.
 *  - Requests microphone permission only when voice input is initiated.
 *  - Explicit Assistant State Model (no scattered boolean flags).
 *  - Zero password collection via voice (Strict Rule 8 Compliance).
 *  - Preserves existing UI and full manual navigation alternative.
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
    UNINITIALIZED:    'UNINITIALIZED',
    AUTOPLAY_PROMPT:  'AUTOPLAY_PROMPT',
    GREETING:         'GREETING',
    LANGUAGE_SELECT:  'LANGUAGE_SELECT',
    ROLE_SELECT:      'ROLE_SELECT',
    ACTION_SELECT:    'ACTION_SELECT',
    NAVIGATING:       'NAVIGATING',
    IDLE:             'IDLE'
  };

  /* ─────────────────────────────────────────────────────────────────────────
     2. VERIFIED LANGUAGE REGISTRY
     Prioritizes Hindi, Punjabi, and English first, followed by verified Indian languages.
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
      hi: "माइक्रोफ़ोन की अनुमति नहीं मिली। आप नीचे दिए गए बटन पर टैप कर सकते हैं।",
      pa: "ਮਾਈਕ੍ਰੋਫੋਨ ਦੀ ਇਜਾਜ਼ਤ ਨਹੀਂ ਮਿਲੀ। ਤੁਸੀਂ ਹੇਠਾਂ ਦਿੱਤੇ ਬਟਨਾਂ 'ਤੇ ਟੈਪ ਕਰ ਸਕਦੇ ਹੋ।",
      en: "Microphone permission was not granted. You can tap any option below.",
      bn: "মাইক্রোফোনের অনুমতি পাওয়া যায়নি। আপনি নিচের অপশনে চাপ দিতে পারেন।",
      mr: "मायक्रोफोनची परवानगी मिळाली नाही. आपण खालील पर्यायांवर टॅप करू शकता.",
      ta: "மைக்ரோஃபோன் அனுமதி கிடைக்கவில்லை. நீங்கள் கீழே உள்ள விருப்பங்களை தேர்வு செய்யலாம்.",
      te: "మైక్రోఫోన్ అనుమతి లభించలేదు. మీరు క్రింది ఎంపికలను ఎంచుకోవచ్చు.",
      gu: "માઇક્રોફોનની મંજૂરી મળી નથી. તમે નીચે આપેલા બટન પર ટેપ કરી શકો છો.",
      kn: "ಮೈಕ್ರೋಫೋನ್ ಅನುಮತಿ ಲಭ್ಯವಾಗಿಲ್ಲ. ನೀವು ಕೆಳಗಿನ ಆಯ್ಕೆಗಳನ್ನು ಬಳಸಬಹುದು.",
      ml: "മൈക്രോഫോൺ അനുമതി ലഭിച്ചില്ല. താഴെയുള്ള ഓപ്ഷനുകൾ ഉപയോഗിക്കുക.",
      or: "ମାଇକ୍ରୋଫୋନ୍ ଅନୁମତି ମିଳିଲା ନାହିଁ। ଆପଣ ତଳେ ଥିବା ବଟନ୍ ବ୍ୟବହାର କରିପାରିବେ।",
      ur: "مائیکروفون کی اجازت نہیں ملی۔ آپ نیچے دیے گئے آپشنز پر ٹیپ کر سکتے ہیں۔"
    }
  };

  /* ─────────────────────────────────────────────────────────────────────────
     4. VOICEHIRE ASSISTANT CORE CONTROLLER
  ───────────────────────────────────────────────────────────────────────── */
  class VoiceHireAssistant {
    constructor() {
      // Configuration & Preferences
      this.currentLang = localStorage.getItem('vh_lang') || (window.VH && window.VH.lang) || 'hi';
      if (!LANGUAGES[this.currentLang]) this.currentLang = 'hi';

      this.isManualMode = localStorage.getItem('vh_manual_mode') === 'true';
      this.isMuted = localStorage.getItem('vh_muted') === 'true';
      this.isDismissed = sessionStorage.getItem('vh_dismissed') === 'true';

      // State Management
      this.state = States.UNINITIALIZED;
      this.selectedRole = null;       // 'worker' | 'user'
      this.selectedAction = null;     // 'login' | 'register'
      this.lastInstruction = '';

      // Production Voice Services Engine
      this.tts = new (window.VoiceHireVoice ? window.VoiceHireVoice.TextToSpeechService : Object)();
      this.stt = new (window.VoiceHireVoice ? window.VoiceHireVoice.SpeechRecognitionService : Object)();
      this.lastClickTime = 0;
      this.isSpeaking = false;
      this.isListening = false;
      this.isProcessing = false;

      // DOM References
      this.dom = {};

      this.init();
    }

    init() {
      this.injectStyles();
      this.renderWidget();
      this.bindControls();
      this.initVoiceServices();

      // Check whether user explicitly preferred manual mode
      if (this.isManualMode) {
        this.updateStatus('Manual Mode', 'ready');
        return; // Stays minimized as floating FAB
      }

      // If already dismissed for this tab session, do not auto-open
      if (this.isDismissed) {
        return;
      }

      // Auto-open for new visitor after short delay
      setTimeout(() => {
        this.open();
        this.startOnboarding();
      }, 750);
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
          width: 380px;
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

        /* Panel Header */
        .vh-header {
          background: linear-gradient(135deg, #0F172A 0%, #1E293B 100%);
          color: #FFFFFF;
          padding: 12px 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        .vh-header-info {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .vh-header-avatar {
          position: relative;
          width: 38px;
          height: 38px;
          border-radius: 50%;
          background: #2563EB;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1.15rem;
          color: #FFFFFF;
        }
        .vh-header-ring {
          position: absolute;
          inset: -4px;
          border-radius: 50%;
          border: 2px solid transparent;
          transition: all 0.3s ease;
        }
        .vh-header-ring.speaking {
          border-color: #F59E0B;
          animation: vh-spin 1.5s linear infinite;
        }
        .vh-header-ring.listening {
          border-color: #10B981;
          animation: vh-spin 1s linear infinite;
        }
        @keyframes vh-spin { to { transform: rotate(360deg); } }

        .vh-header-title {
          font-size: 0.9375rem;
          font-weight: 700;
          line-height: 1.2;
        }
        .vh-header-status {
          font-size: 0.75rem;
          color: #94A3B8;
          display: flex;
          align-items: center;
          gap: 5px;
          margin-top: 2px;
        }
        .vh-status-dot {
          width: 7px;
          height: 7px;
          border-radius: 50%;
          background: #10B981;
          display: inline-block;
        }
        .vh-status-dot.speaking { background: #F59E0B; }
        .vh-status-dot.listening { background: #2563EB; animation: vh-pulse 1s infinite; }
        .vh-status-dot.processing { background: #8B5CF6; }

        /* Header Control Toolbar */
        .vh-toolbar {
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .vh-tool-btn {
          background: rgba(255, 255, 255, 0.12);
          border: none;
          color: #E2E8F0;
          width: 30px;
          height: 30px;
          border-radius: 8px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.8125rem;
          transition: background 0.15s ease, color 0.15s ease;
        }
        .vh-tool-btn:hover {
          background: rgba(255, 255, 255, 0.25);
          color: #FFFFFF;
        }
        .vh-tool-btn.active {
          background: #2563EB;
          color: #FFFFFF;
        }

        /* Language Drawer */
        .vh-lang-drawer {
          background: #F8FAFC;
          border-bottom: 1px solid #E2E8F0;
          padding: 12px 14px;
          display: none;
          max-height: 220px;
          overflow-y: auto;
        }
        .vh-lang-drawer.is-open { display: block; }
        .vh-lang-drawer-title {
          font-size: 0.75rem;
          font-weight: 700;
          color: #64748B;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin-bottom: 8px;
        }
        .vh-lang-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 6px;
        }
        .vh-lang-card {
          background: #FFFFFF;
          border: 1.5px solid #E2E8F0;
          border-radius: 10px;
          padding: 8px 6px;
          text-align: center;
          cursor: pointer;
          font-family: inherit;
          transition: all 0.15s ease;
        }
        .vh-lang-card:hover, .vh-lang-card.selected {
          border-color: #2563EB;
          background: #EFF6FF;
          color: #2563EB;
          font-weight: 700;
        }
        .vh-lang-flag { font-size: 1.1rem; display: block; margin-bottom: 2px; }
        .vh-lang-native { font-size: 0.8125rem; font-weight: 600; display: block; }
        .vh-lang-name { font-size: 0.6875rem; color: #64748B; display: block; }

        /* Autoplay Blocked Banner */
        .vh-autoplay-banner {
          background: #FEF3C7;
          border-bottom: 1px solid #FDE68A;
          padding: 12px 16px;
          display: none;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
        }
        .vh-autoplay-banner.is-visible { display: flex; }
        .vh-autoplay-text {
          font-size: 0.8125rem;
          color: #92400E;
          font-weight: 500;
          line-height: 1.4;
        }
        .vh-autoplay-btn {
          background: #D97706;
          color: #FFFFFF;
          border: none;
          border-radius: 8px;
          padding: 6px 12px;
          font-size: 0.75rem;
          font-weight: 700;
          cursor: pointer;
          white-space: nowrap;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .vh-autoplay-btn:hover { background: #B45309; }

        /* Conversation Messages Area */
        .vh-messages {
          flex: 1;
          padding: 16px;
          overflow-y: auto;
          display: flex;
          flex-direction: column;
          gap: 12px;
          background: #F8FAFC;
          min-height: 240px;
          max-height: 380px;
        }
        .vh-bubble {
          max-width: 90%;
          padding: 12px 14px;
          border-radius: 14px;
          font-size: 0.875rem;
          line-height: 1.5;
          animation: vh-fade-in 0.25s ease;
        }
        @keyframes vh-fade-in {
          from { opacity: 0; transform: translateY(6px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .vh-bubble.bot {
          background: #FFFFFF;
          color: #0F172A;
          border: 1px solid #E2E8F0;
          border-top-left-radius: 4px;
          align-self: flex-start;
          box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .vh-bubble.user {
          background: #2563EB;
          color: #FFFFFF;
          border-top-right-radius: 4px;
          align-self: flex-end;
          font-weight: 500;
        }

        /* Large Interactive Choices Area */
        .vh-choices {
          display: flex;
          flex-direction: column;
          gap: 8px;
          margin-top: 4px;
        }
        .vh-choice-btn {
          background: #FFFFFF;
          border: 2px solid #E2E8F0;
          border-radius: 12px;
          padding: 12px 14px;
          text-align: left;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 12px;
          transition: all 0.16s ease;
          width: 100%;
        }
        .vh-choice-btn:hover {
          border-color: #2563EB;
          background: #EFF6FF;
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(37, 99, 235, 0.1);
        }
        .vh-choice-btn.primary {
          border-color: #BFDBFE;
        }
        .vh-choice-icon {
          font-size: 1.6rem;
          flex-shrink: 0;
          width: 40px;
          height: 40px;
          border-radius: 10px;
          background: #F1F5F9;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .vh-choice-btn:hover .vh-choice-icon {
          background: #DBEAFE;
        }
        .vh-choice-content {
          flex: 1;
        }
        .vh-choice-title {
          font-size: 0.9375rem;
          font-weight: 700;
          color: #0F172A;
          display: block;
        }
        .vh-choice-sub {
          font-size: 0.75rem;
          color: #64748B;
          display: block;
          margin-top: 2px;
        }

        /* Speaking Wave Indicator */
        .vh-wave-wrap {
          display: flex;
          align-items: center;
          gap: 4px;
          height: 18px;
          padding: 0 4px;
          display: none;
        }
        .vh-wave-wrap.is-active { display: flex; }
        .vh-wave-bar {
          width: 3.5px;
          height: 4px;
          border-radius: 3px;
          background: #2563EB;
          animation: vh-wave-anim 1s ease-in-out infinite;
        }
        .vh-wave-bar:nth-child(1) { animation-delay: 0.0s; }
        .vh-wave-bar:nth-child(2) { animation-delay: 0.15s; }
        .vh-wave-bar:nth-child(3) { animation-delay: 0.3s; }
        .vh-wave-bar:nth-child(4) { animation-delay: 0.45s; }
        .vh-wave-bar:nth-child(5) { animation-delay: 0.3s; }
        .vh-wave-bar:nth-child(6) { animation-delay: 0.15s; }
        @keyframes vh-wave-anim {
          0%, 100% { height: 4px; }
          50% { height: 18px; }
        }

        /* Interim Speech Preview */
        .vh-interim {
          font-size: 0.8125rem;
          font-style: italic;
          color: #64748B;
          padding: 6px 10px;
          background: #F1F5F9;
          border-radius: 8px;
          display: none;
        }
        .vh-interim.is-active { display: block; }

        /* Panel Footer & Controls */
        .vh-footer {
          background: #FFFFFF;
          border-top: 1px solid #E2E8F0;
          padding: 10px 14px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
        }
        .vh-mic-action {
          width: 44px;
          height: 44px;
          border-radius: 50%;
          background: #2563EB;
          color: #FFFFFF;
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 1.15rem;
          transition: all 0.2s ease;
          position: relative;
        }
        .vh-mic-action:hover { background: #1D4ED8; transform: scale(1.05); }
        .vh-mic-action.is-listening {
          background: #DC2626;
          animation: vh-mic-pulse 1.2s infinite;
        }
        @keyframes vh-mic-pulse {
          0% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.4); }
          70% { box-shadow: 0 0 0 10px rgba(220, 38, 38, 0); }
          100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); }
        }
        .vh-footer-info {
          flex: 1;
        }
        .vh-mic-hint {
          font-size: 0.8125rem;
          font-weight: 600;
          color: #1E293B;
          line-height: 1.2;
        }
        .vh-mic-subhint {
          font-size: 0.6875rem;
          color: #64748B;
        }
        .vh-repeat-btn {
          background: #F1F5F9;
          border: 1px solid #E2E8F0;
          color: #475569;
          padding: 7px 11px;
          border-radius: 8px;
          font-size: 0.75rem;
          font-weight: 600;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 6px;
          white-space: nowrap;
          transition: all 0.15s ease;
        }
        .vh-repeat-btn:hover {
          background: #E2E8F0;
          color: #0F172A;
        }

        /* Typed Input Fallback */
        .vh-typed-row {
          display: flex;
          gap: 8px;
          padding: 8px 14px 12px 14px;
          background: #FFFFFF;
          border-top: 1px dashed #E2E8F0;
        }
        .vh-typed-input {
          flex: 1;
          border: 1px solid #CBD5E1;
          border-radius: 8px;
          padding: 7px 12px;
          font-size: 0.8125rem;
          font-family: inherit;
          outline: none;
          transition: border-color 0.15s ease;
        }
        .vh-typed-input:focus {
          border-color: #2563EB;
        }
        .vh-typed-send {
          background: #2563EB;
          color: #FFFFFF;
          border: none;
          border-radius: 8px;
          padding: 0 14px;
          cursor: pointer;
          font-size: 0.8125rem;
          transition: background 0.15s ease;
        }
        .vh-typed-send:hover {
          background: #1D4ED8;
        }

        /* Transcript Confirmation & Correction Card */
        .vh-confirm-card {
          background: #F8FAFC;
          border: 1px solid #CBD5E1;
          border-radius: 12px;
          padding: 10px 12px;
          margin: 6px 0;
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .vh-confirm-header {
          font-size: 0.75rem;
          color: #64748B;
          display: flex;
          align-items: center;
          gap: 6px;
        }
        .vh-confirm-text {
          font-size: 0.875rem;
          font-weight: 600;
          color: #0F172A;
          word-break: break-word;
        }
        .vh-confirm-edit-input {
          width: 100%;
          border: 1px solid #3B82F6;
          border-radius: 6px;
          padding: 6px 8px;
          font-size: 0.8125rem;
          font-family: inherit;
          outline: none;
        }
        .vh-confirm-actions {
          display: flex;
          gap: 6px;
          margin-top: 2px;
        }
        .vh-confirm-btn {
          padding: 5px 9px;
          border-radius: 6px;
          font-size: 0.6875rem;
          font-weight: 600;
          cursor: pointer;
          border: 1px solid transparent;
          display: flex;
          align-items: center;
          gap: 4px;
          transition: all 0.15s ease;
        }
        .vh-confirm-btn.primary {
          background: #2563EB;
          color: #FFFFFF;
        }
        .vh-confirm-btn.secondary {
          background: #FFFFFF;
          border-color: #CBD5E1;
          color: #334155;
        }
        .vh-confirm-btn:hover {
          filter: brightness(0.95);
        }

        /* Mobile Adjustments */
        @media (max-width: 480px) {
          #vh-assistant-root { bottom: 16px; right: 16px; }
          .vh-panel {
            width: calc(100vw - 32px);
            bottom: 70px;
            right: 0;
            max-height: 80vh;
          }
          .vh-lang-grid { grid-template-columns: repeat(2, 1fr); }
        }
      `;
      document.head.appendChild(s);
    }

    renderWidget() {
      // Remove any lingering legacy nodes if present
      ['vh-assistant-root', 'vhai-root', 'vgb-root', 'vh-gateway-bot'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.remove();
      });

      const root = document.createElement('div');
      root.id = 'vh-assistant-root';

      // Generate language cards HTML
      const langCardsHtml = Object.values(LANGUAGES).map(l => `
        <button class="vh-lang-card ${l.code === this.currentLang ? 'selected' : ''}" data-code="${l.code}">
          <span class="vh-lang-flag">${l.flag}</span>
          <span class="vh-lang-native">${l.native}</span>
          <span class="vh-lang-name">${l.name}</span>
        </button>
      `).join('');

      root.innerHTML = `
        <!-- Floating Toggle Trigger -->
        <button class="vh-fab" id="vh-fab-trigger" title="VoiceHire Voice Assistant" aria-label="Open VoiceHire Assistant">
          <i class="fa-solid fa-microphone-lines"></i>
          <span class="vh-fab-pulse"></span>
        </button>

        <!-- Main Assistant Panel -->
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
              <button class="vh-tool-btn" id="vh-btn-lang" title="Change Language / भाषा बदलें">
                <i class="fa-solid fa-language"></i>
              </button>
              <button class="vh-tool-btn ${this.isMuted ? 'active' : ''}" id="vh-btn-sound" title="${this.isMuted ? 'Unmute Voice' : 'Mute Voice'}">
                <i class="fa-solid ${this.isMuted ? 'fa-volume-xmark' : 'fa-volume-high'}"></i>
              </button>
              <button class="vh-tool-btn ${this.isManualMode ? 'active' : ''}" id="vh-btn-manual" title="Manual Mode (Disable auto-voice)">
                <i class="fa-solid fa-hand"></i>
              </button>
              <button class="vh-tool-btn" id="vh-btn-min" title="Minimize">
                <i class="fa-solid fa-window-minimize"></i>
              </button>
              <button class="vh-tool-btn" id="vh-btn-close" title="Close">
                <i class="fa-solid fa-xmark"></i>
              </button>
            </div>
          </div>

          <!-- Language Drawer -->
          <div class="vh-lang-drawer" id="vh-lang-drawer">
            <div class="vh-lang-drawer-title">🌐 Choose Your Language / अपनी भाषा चुनें</div>
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

          <!-- Message History & Choices Transcript -->
          <div class="vh-messages" id="vh-messages-stream"></div>

          <!-- Interim Speech Transcript -->
          <div class="vh-interim" id="vh-interim-box"></div>

          <!-- Footer Action Bar -->
          <div class="vh-footer">
            <button class="vh-mic-action" id="vh-mic-btn" title="Tap to Speak / बोलने के लिए टैप करें">
              <i class="fa-solid fa-microphone"></i>
            </button>
            <div class="vh-footer-info">
              <div class="vh-mic-hint" id="vh-mic-hint">Tap to Speak</div>
              <div class="vh-mic-subhint" id="vh-mic-subhint">Or speak / type below</div>
              <div class="vh-wave-wrap" id="vh-wave-indicator">
                <div class="vh-wave-bar"></div>
                <div class="vh-wave-bar"></div>
                <div class="vh-wave-bar"></div>
                <div class="vh-wave-bar"></div>
                <div class="vh-wave-bar"></div>
                <div class="vh-wave-bar"></div>
              </div>
            </div>
            <button class="vh-repeat-btn" id="vh-repeat-btn" title="Repeat Spoken Prompt">
              <i class="fa-solid fa-rotate-right"></i> Repeat
            </button>
          </div>

          <!-- Typed Input Fallback -->
          <div class="vh-typed-row" id="vh-typed-row">
            <input type="text" class="vh-typed-input" id="vh-typed-input" placeholder="यहाँ बोलें या टाइप करें... / Speak or type..." aria-label="Type message fallback">
            <button class="vh-typed-send" id="vh-typed-send" title="Send / भेजें" aria-label="Send message">
              <i class="fa-solid fa-paper-plane"></i>
            </button>
          </div>

        </div>
      `;

      document.body.appendChild(root);

      // Cache DOM references
      this.dom = {
        root: document.getElementById('vh-assistant-root'),
        fab: document.getElementById('vh-fab-trigger'),
        panel: document.getElementById('vh-main-panel'),
        statusRing: document.getElementById('vh-status-ring'),
        statusDot: document.getElementById('vh-status-dot'),
        statusText: document.getElementById('vh-status-text'),
        btnLang: document.getElementById('vh-btn-lang'),
        btnSound: document.getElementById('vh-btn-sound'),
        btnManual: document.getElementById('vh-btn-manual'),
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
      this.dom.btnMin.addEventListener('click', () => this.minimize());
      this.dom.btnClose.addEventListener('click', () => this.dismiss());
      this.dom.btnLang.addEventListener('click', () => this.toggleLangDrawer());
      this.dom.btnSound.addEventListener('click', () => this.toggleSound());
      this.dom.btnManual.addEventListener('click', () => this.toggleManualMode());

      // Language selection buttons in drawer
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
        if (this.currentUtterance) {
          this.speechSynth.cancel();
        }
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

      // Microphone button with rapid click debouncing
      this.dom.micBtn.addEventListener('click', () => {
        const now = Date.now();
        if (now - this.lastClickTime < 350) return;
        this.lastClickTime = now;
        if (this.stt && this.stt.state === (window.VoiceHireVoice ? window.VoiceHireVoice.VoiceStates.LISTENING : 'LISTENING')) {
          this.stopListening();
        } else {
          this.startListening();
        }
      });

      // Repeat button
      this.dom.repeatBtn.addEventListener('click', () => {
        this.speakCurrentInstruction();
      });
    }

    /* ── State Transition Engine ───────────────────────────────────────── */
    setState(newState) {
      this.state = newState;
      console.log(`[VoiceHire Assistant] Transition -> ${newState}`);
    }

    startOnboarding() {
      this.clearMessages();
      this.setState(States.GREETING);

      // Play initial Hindi greeting explaining finding work or booking a worker
      const greetingHi = DIALOGUES.greeting.hi;
      this.addMessage(greetingHi, 'bot');
      this.lastInstruction = greetingHi;

      this.speak(greetingHi, 'hi')
        .then(() => {
          // Immediately advance to Language Selection
          this.showLanguageSelection();
        })
        .catch(err => {
          if (err === 'autoplay_blocked') {
            this.showAutoplayBlockedBanner();
            this.showLanguageSelection();
          }
        });
    }

    showAutoplayBlockedBanner() {
      const bannerText = (DIALOGUES.autoplayBlockedMsg[this.currentLang] || DIALOGUES.autoplayBlockedMsg.hi);
      const btnText = (DIALOGUES.startVoiceBtn[this.currentLang] || DIALOGUES.startVoiceBtn.hi);
      this.dom.autoplayText.textContent = bannerText;
      this.dom.startVoiceBtn.innerHTML = btnText;
      this.dom.autoplayBanner.classList.add('is-visible');
    }

    showLanguageSelection() {
      this.setState(States.LANGUAGE_SELECT);
      const askText = DIALOGUES.askLanguage.hi;
      this.addMessage(askText, 'bot');
      this.lastInstruction = askText;

      // Render large, visible language buttons
      const choicesContainer = document.createElement('div');
      choicesContainer.className = 'vh-choices';

      // Required: Begin with Hindi, Punjabi, and English first, followed by verified Indian languages
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
          // Confirm language in chosen tongue and move to role selection
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

      // Choice 1: Worker
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

      // Choice 2: Customer / Employer
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

      // Option A: Login
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

      // Option B: Create Account
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

      this.speak(navText, lang).finally(() => {
        setTimeout(() => {
          window.location.href = targetUrl;
        }, 500);
      });
    }

    /* ── Speech Synthesis Engine ───────────────────────────────────────── */
    speak(text, langCode) {
      if (this.tts && this.tts.speak) {
        return this.tts.speak(text, langCode || this.currentLang);
      }
      return Promise.resolve();
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

    /* ── Speech Recognition & Voice Services Engine ────────────────────── */
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
          this.dom.statusText.textContent = DIALOGUES.micListening[this.currentLang] || 'Listening...';
          this.dom.micHint.textContent = DIALOGUES.micListening[this.currentLang] || 'Listening...';
          this.dom.interim.classList.add('is-active');
          this.dom.interim.textContent = '';
        } else {
          this.isListening = false;
          this.dom.micBtn.classList.remove('is-listening');
          this.dom.statusRing.className = 'vh-header-ring';
          this.dom.statusDot.className = 'vh-status-dot';
          this.dom.statusText.textContent = 'Ready';
          this.dom.micHint.textContent = 'Tap to Speak';
          this.dom.interim.classList.remove('is-active');
        }
      };

      this.stt.onInterim = (text) => {
        if (this.dom.interim) {
          this.dom.interim.textContent = text;
        }
      };

      this.stt.onFinal = (text, confidence) => {
        if (this.dom.interim) {
          this.dom.interim.textContent = text;
        }
        this.showTranscriptConfirmation(text, confidence);
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

    startListening() {
      this.stopSpeaking();
      if (!this.stt || !this.stt.isSupported || !this.stt.isSupported()) {
        this.showTypedFallbackNotice();
        return;
      }
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
      this.dom.micHint.textContent = 'Tap to Speak';
      this.dom.interim.classList.remove('is-active');
    }

    cancelVoice() {
      if (this.stt && this.stt.cancel) this.stt.cancel();
      if (this.tts && this.tts.cancel) this.tts.cancel();
      this.stopListening();
      this.stopSpeaking();
    }

    showTypedFallbackNotice() {
      if (this.dom.typedInput) {
        this.dom.typedInput.focus();
        this.dom.micSubhint.textContent = 'Please type below';
      }
    }

    handleTypedInput() {
      if (!this.dom.typedInput) return;
      const text = this.dom.typedInput.value.trim();
      if (!text) return;
      this.dom.typedInput.value = '';
      this.addMessage(text, 'user');
      this.executeVoiceIntent(text, 1.0);
    }

    showTranscriptConfirmation(text, confidence) {
      const card = document.createElement('div');
      card.className = 'vh-confirm-card';
      card.innerHTML = `
        <div class="vh-confirm-header">
          <i class="fa-solid fa-microphone"></i>
          <span>Recognized speech (Review / Edit)</span>
        </div>
        <div class="vh-confirm-text">"${text}"</div>
        <div class="vh-confirm-actions">
          <button class="vh-confirm-btn primary vh-confirm-ok">
            <i class="fa-solid fa-check"></i> Continue
          </button>
          <button class="vh-confirm-btn secondary vh-confirm-edit">
            <i class="fa-solid fa-pen"></i> Edit
          </button>
          <button class="vh-confirm-btn secondary vh-confirm-retry">
            <i class="fa-solid fa-rotate-right"></i> Retry
          </button>
        </div>
      `;

      const textEl = card.querySelector('.vh-confirm-text');
      const editBtn = card.querySelector('.vh-confirm-edit');
      const okBtn = card.querySelector('.vh-confirm-ok');
      const retryBtn = card.querySelector('.vh-confirm-retry');

      editBtn.addEventListener('click', () => {
        const curText = textEl.textContent.replace(/^"|"$/g, '');
        textEl.innerHTML = `<input type="text" class="vh-confirm-edit-input" value="${curText}" />`;
        const input = textEl.querySelector('input');
        input.focus();
        editBtn.style.display = 'none';
      });

      retryBtn.addEventListener('click', () => {
        card.remove();
        this.startListening();
      });

      okBtn.addEventListener('click', () => {
        const input = textEl.querySelector('input');
        const finalText = input ? input.value.trim() : text;
        card.remove();
        this.executeVoiceIntent(finalText, confidence);
      });

      this.dom.messages.appendChild(card);
      this.scrollToBottom();
    }

    async executeVoiceIntent(text, confidence = 1.0) {
      if (!text) return;

      // Call Orchestration Engine API
      let turn = null;
      if (window.VoiceHireVoice && window.VoiceHireVoice.VoiceIntentService && window.VoiceHireVoice.VoiceIntentService.orchestrateTurn) {
        turn = await window.VoiceHireVoice.VoiceIntentService.orchestrateTurn(
          text,
          this.state || 'greeting',
          this.currentLang
        );
      }

      if (!turn) {
        // Fallback to basic intent analyzer
        if (window.VoiceHireVoice && window.VoiceHireVoice.VoiceIntentService) {
          turn = await window.VoiceHireVoice.VoiceIntentService.processTranscript(
            text,
            this.currentLang,
            confidence,
            this.state
          );
        }
      }

      if (!turn) return;

      // Handle speech and display
      const displayMsg = turn.display_text || turn.speech_response || turn.clarification_prompt;
      if (displayMsg) {
        this.addMessage(displayMsg, 'bot');
        this.lastInstruction = displayMsg;
      }

      const speechMsg = turn.speech_response || displayMsg;
      if (speechMsg) {
        this.speak(speechMsg, this.currentLang);
      }

      // Handle State Transition
      if (turn.current_state) {
        this.state = turn.current_state;
      }

      const action = turn.action;
      const args = turn.action_arguments || {};

      // 1. Language Selection
      if (action === 'select_language' && args.language) {
        this.setLanguage(args.language, false);
      }

      // 2. Role Selection
      if (action === 'select_role' && args.role) {
        this.selectedRole = args.role;
      }

      // 3. Form Field Auto-Filling (Non-sensitive)
      if (action === 'set_form_field' && args.field_name && args.value) {
        const fieldEl = document.querySelector(`input[name="${args.field_name}"], input[id="${args.field_name}"], select[name="${args.field_name}"]`);
        if (fieldEl) {
          fieldEl.value = args.value;
          fieldEl.dispatchEvent(new Event('input', { bubbles: true }));
          fieldEl.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }

      // 4. Consequential Confirmation Request (Yes/No buttons)
      if (turn.requires_confirmation) {
        const confirmBox = document.createElement('div');
        confirmBox.className = 'vh-choices';
        confirmBox.style.marginTop = '8px';
        confirmBox.innerHTML = `
          <button class="vh-choice-btn" style="background:#10B981;color:#fff;" id="vh-btn-yes">
            <i class="fa-solid fa-check"></i> हाँ, पक्का करें (Yes)
          </button>
          <button class="vh-choice-btn" style="background:#EF4444;color:#fff;" id="vh-btn-no">
            <i class="fa-solid fa-xmark"></i> नहीं, रद्द करें (No)
          </button>
        `;
        this.dom.messages.appendChild(confirmBox);
        this.scrollToBottom();

        const yesBtn = confirmBox.querySelector('#vh-btn-yes');
        const noBtn = confirmBox.querySelector('#vh-btn-no');

        yesBtn.addEventListener('click', () => {
          confirmBox.remove();
          this.executeVoiceIntent('हाँ ठीक है confirm', 1.0);
        });

        noBtn.addEventListener('click', () => {
          confirmBox.remove();
          this.executeVoiceIntent('नहीं cancel karo', 1.0);
        });
      }

      // 5. Quick Replies Chips
      if (turn.quick_replies && turn.quick_replies.length > 0 && !turn.requires_confirmation) {
        const chipRow = document.createElement('div');
        chipRow.style.display = 'flex';
        chipRow.style.gap = '6px';
        chipRow.style.flexWrap = 'wrap';
        chipRow.style.marginTop = '6px';

        turn.quick_replies.forEach(reply => {
          const chip = document.createElement('button');
          chip.className = 'vh-lang-card';
          chip.style.padding = '5px 10px';
          chip.style.fontSize = '0.78rem';
          chip.style.borderRadius = '16px';
          chip.style.cursor = 'pointer';
          chip.textContent = reply;
          chip.addEventListener('click', () => {
            chipRow.remove();
            this.addMessage(reply, 'user');
            this.executeVoiceIntent(reply, 1.0);
          });
          chipRow.appendChild(chip);
        });

        this.dom.messages.appendChild(chipRow);
        this.scrollToBottom();
      }

      // 6. Navigation
      if (action === 'navigate' && args.route) {
        setTimeout(() => {
          window.location.href = args.route;
        }, 800);
      }
    }

    /* ── Visual Updates & Controls ─────────────────────────────────────── */
    addMessage(text, sender = 'bot') {
      const bubble = document.createElement('div');
      bubble.className = `vh-bubble ${sender}`;
      bubble.textContent = text;
      this.dom.messages.appendChild(bubble);
      this.scrollToBottom();
    }

    clearMessages() {
      this.dom.messages.innerHTML = '';
    }

    scrollToBottom() {
      this.dom.messages.scrollTop = this.dom.messages.scrollHeight;
    }

    updateSpeakingIndicators(active) {
      if (active) {
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

    updateStatus(label, type = 'ready') {
      this.dom.statusText.textContent = label;
      this.dom.statusDot.className = `vh-status-dot ${type}`;
    }

    setLanguage(code, speakNotice = true) {
      if (!LANGUAGES[code]) code = 'hi';
      this.currentLang = code;
      localStorage.setItem('vh_lang', code);

      // Highlight in drawer
      this.dom.langDrawer.querySelectorAll('.vh-lang-card').forEach(c => {
        c.classList.toggle('selected', c.dataset.code === code);
      });

      // Synchronize backend session language
      fetch(`/set_lang/${code}`).catch(() => {});
      if (window.VH) window.VH.lang = code;

      if (speakNotice) {
        const confText = DIALOGUES.langConfirmed[code] || DIALOGUES.langConfirmed.hi;
        this.addMessage(confText, 'bot');
        this.speak(confText, code).then(() => {
          if (this.state === States.LANGUAGE_SELECT || this.state === States.GREETING) {
            this.showRoleSelection();
          }
        });
      }
    }

    toggleLangDrawer() {
      this.dom.langDrawer.classList.toggle('is-open');
    }

    toggleSound() {
      this.isMuted = !this.isMuted;
      localStorage.setItem('vh_muted', this.isMuted ? 'true' : 'false');
      if (this.isMuted) {
        this.stopSpeaking();
        this.dom.btnSound.classList.add('active');
        this.dom.btnSound.innerHTML = '<i class="fa-solid fa-volume-xmark"></i>';
        this.dom.btnSound.title = 'Unmute Voice';
      } else {
        this.dom.btnSound.classList.remove('active');
        this.dom.btnSound.innerHTML = '<i class="fa-solid fa-volume-high"></i>';
        this.dom.btnSound.title = 'Mute Voice';
        this.speakCurrentInstruction();
      }
    }

    toggleManualMode() {
      this.isManualMode = !this.isManualMode;
      localStorage.setItem('vh_manual_mode', this.isManualMode ? 'true' : 'false');
      this.dom.btnManual.classList.toggle('active', this.isManualMode);

      if (this.isManualMode) {
        this.stopSpeaking();
        this.stopListening();
        this.updateStatus('Manual Mode', 'ready');
        this.addMessage('Manual Mode enabled. Voice prompts paused.', 'bot');
      } else {
        this.updateStatus('Ready', 'ready');
        this.addMessage('Voice Assistant active.', 'bot');
        this.speakCurrentInstruction();
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

})();
