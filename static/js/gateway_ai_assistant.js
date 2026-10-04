/**
 * VoiceHire Gateway AI Assistant
 * ─────────────────────────────────────────────────────────────────
 * Auto-starts on the landing page (gateway.html).
 * Speaks first in Hindi (default), asks for language preference,
 * then guides the user through Login → Profile Creation → Job Hunt
 * entirely by voice. Works 100% via Web Speech API — no backend AI needed.
 *
 * Flow:
 *   BOOT → LANGUAGE_SELECT → ROLE_ASK → (LOGIN | REGISTER) → GUIDE
 *
 * All voices are mapped to browser-native speech synthesis language codes.
 */
(function () {
  'use strict';

  /* ═══════════════════════════════════════════════════════════
     SECTION 1: CONFIGURATION
  ═══════════════════════════════════════════════════════════ */

  const LANG_MAP = {
    hi: { code: 'hi-IN', label: 'Hindi', flag: '🇮🇳' },
    en: { code: 'en-IN', label: 'English', flag: '🇬🇧' },
    bn: { code: 'bn-IN', label: 'Bangla', flag: '🇧🇩' },
    ta: { code: 'ta-IN', label: 'Tamil', flag: '🌟' },
    te: { code: 'te-IN', label: 'Telugu', flag: '🌟' },
    mr: { code: 'mr-IN', label: 'Marathi', flag: '🇮🇳' },
    gu: { code: 'gu-IN', label: 'Gujarati', flag: '🇮🇳' },
    kn: { code: 'kn-IN', label: 'Kannada', flag: '🌟' },
  };

  /* ═══════════════════════════════════════════════════════════
     SECTION 2: MULTI-LANGUAGE SCRIPT LIBRARY
     All text the AI speaks at each stage
  ═══════════════════════════════════════════════════════════ */

  const DIALOGUE = {
    // ── Boot greeting (always Hindi first) ──
    boot: {
      hi: "Namaste! Main VoiceHire ka AI Assistant hoon. Kya aap Hindi mein baat karna chahenge? Ya kisi aur bhasha mein?",
      en: "Hello! I am VoiceHire's AI assistant. Would you like to continue in English?",
      default: "Namaste! Main VoiceHire ka AI Assistant hoon. Kya aap Hindi mein baat karna chahenge?"
    },

    // ── Language confirmation ──
    langConfirm: {
      hi: "Bahut achha! Ab hum Hindi mein baat karenge.",
      en: "Great! We will continue in English.",
      bn: "Khub bhalo! Ekhon amra Banglay kotha bolbo.",
      ta: "Nanru! Naan unkalukku Tamil-il udavuven.",
      te: "Chala bagundi! Telugulo konasagista.",
      mr: "Chhan! Aata marathi madhe boluyat.",
      gu: "Khub saras! Hve aapane gujarati ma vaat karishu.",
      kn: "Tumba Chennaagi! Kannada-alli maatanaadona.",
    },

    // ── Role question: new user or existing? ──
    roleAsk: {
      hi: "Kya aap pehle bhi VoiceHire use kar chuke hain? Agar haan to 'Login' bolein. Agar nahin to 'Nayi Profile' bolein.",
      en: "Have you used VoiceHire before? Say 'Login' if you have an account, or 'New Profile' to register.",
      bn: "Apni ki age VoiceHire use korechhen? 'Login' bolun jodi account ache, noyto 'Notun' bolun.",
      ta: "Neenga munbe VoiceHire upayogissirreerga? 'Login' sollunga illaiyal 'Puthu' sollunga.",
      te: "Meeru mundhu VoiceHire vadilaaraa? 'Login' cheppandi ledu 'Kotta' cheppandi.",
      mr: "Tumhi aadhi VoiceHire vaparla aahe ka? 'Login' mhana kiva 'Navi Profile' mhana.",
      gu: "Shu tame pehla VoiceHire vapro chho? 'Login' kaho ya 'Navi Profile' kaho.",
      kn: "Neenu modalu VoiceHire upayogisiddiya? 'Login' helo illava 'Navu' helo.",
    },

    // ── Login path ──
    loginStart: {
      hi: "Theek hai! Chaliye login karte hain. Pehle bataaein — kya aap kaam dhundhne waale hain ya kaam dene waale? 'Mazdoor' ya 'Maalik' bolein.",
      en: "Let's log you in! Are you a Worker looking for jobs, or an Employer? Say 'Worker' or 'Employer'.",
      bn: "Thik ache! Apni ki Worker naki Employer? 'Worker' ba 'Employer' bolun.",
      ta: "Sari! Neengal Worker-a illaiyal Employer-a? 'Worker' ya 'Employer' sollunga.",
      te: "Sare! Meeru Worker aa Employer aa? 'Worker' cheppandi ya 'Employer' cheppandi.",
      mr: "Chalaa! Tumhi Worker aahat ka Employer? 'Worker' ya 'Employer' mhana.",
      gu: "Saru! Tame Worker cho ke Employer? 'Worker' ya 'Employer' kaho.",
      kn: "Sari! Neenu Worker-aa Employer-aa? 'Worker' helo ya 'Employer' helo.",
    },

    loginPhone: {
      hi: "Apna 10 ankon ka mobile number dheere dheere bolein.",
      en: "Please say your 10-digit mobile number slowly.",
      bn: "Apnar 10-digit mobile number aaste bolun.",
      ta: "Unkal 10 ellakkam phone number mella sollunga.",
      te: "Meeru 10 number mobile number meesta meesta cheppandi.",
      mr: "Tumcha 10 anki mobile number savakar saanga.",
      gu: "Tamaro 10 ankno mobile number dhire dhire kaho.",
      kn: "Nimma 10 anka mobile number nidhanavagi heli.",
    },

    loginPassword: {
      hi: "Ab apna password bolein.",
      en: "Now say your password.",
      bn: "Akhon apnar password bolun.",
      ta: "Ippo unkal password sollunga.",
      te: "Ippudu meeru password cheppandi.",
      mr: "Aata tumcha password saanga.",
      gu: "Hve tamaro password kaho.",
      kn: "Ipa nimma password heli.",
    },

    loginDone: {
      hi: "Bahut badhiya! Login ho raha hai. Ek second...",
      en: "Perfect! Logging you in now...",
      bn: "Ashadharon! Akhon login hochhe...",
      ta: "Arumai! Ippoluthu login aaguthu...",
      te: "Chala bagundi! Ippudu login avutundi...",
      mr: "Mast! Aata login hoto aahe...",
      gu: "Saras! Hve login thai rahu chhe...",
      kn: "Tumba Chenna! Ipa login aagutide...",
    },

    // ── Register path ──
    registerWho: {
      hi: "Shuruaat karte hain! Kya aap kaam dhundhne waale hain ya kaam dene waale? 'Mazdoor' ya 'Maalik' bolein.",
      en: "Let's get started! Are you a Worker looking for jobs, or an Employer hiring? Say 'Worker' or 'Employer'.",
      bn: "Shuru kori! Apni Worker naki Employer? Bolun.",
      ta: "Thudangyalam! Neengal Worker-a Employer-a? Sollunga.",
      te: "Modapatam! Meeru Worker aa Employer aa? Cheppandi.",
      mr: "Suru karuya! Tumhi Worker aahat ka Employer?",
      gu: "Sharu karaiye! Tame Worker cho ke Employer?",
      kn: "Praarabhavisona! Neenu Worker-aa Employer-aa?",
    },

    registerName: {
      hi: "Aapka poora naam kya hai? Kripaya bolein.",
      en: "What is your full name? Please say it now.",
      bn: "Apnar puro naam ki? Bolun.",
      ta: "Unkal peyar enna? Sollunga.",
      te: "Meeru peru emiti? Cheppandi.",
      mr: "Tumche poorne naav kaay aahe?",
      gu: "Tamaru puru naam shu chhe?",
      kn: "Nimma hesa heli.",
    },

    registerWork: {
      hi: "Aap kya kaam karte hain? Jaise plumber, electrician, carpenter, cleaner, driver...",
      en: "What kind of work do you do? For example: plumber, electrician, driver, cleaner...",
      bn: "Apni ki kaj koren? Jemon plumber, electrician, driver...",
      ta: "Neengal enna velai seikireerga? Udaharanam: plumber, electrician...",
      te: "Meeru em pani chestaaru? Udaharanaku: plumber, electrician...",
      mr: "Tumhi konte kaam karta? Udaaharan: plumber, electrician...",
      gu: "Tame shu kaam karo chho? Udaharan: plumber, electrician...",
      kn: "Neenu yenu kelasa maaduttiya? Udaaharana: plumber, electrician...",
    },

    registerLocation: {
      hi: "Aap kis sheher ya ilaake mein rehte hain?",
      en: "Which city or area do you live in?",
      bn: "Apni kon shahore thaken?",
      ta: "Neenga entha nagaram irukkireenga?",
      te: "Meeru em nagaram lo untaaru?",
      mr: "Tumhi konathya shaharat raahtaa?",
      gu: "Tame kya shaher ma rahoch?",
      kn: "Neenu yelli iruttiya?",
    },

    registerPhone: {
      hi: "Apna 10 ankon ka mobile number dheere dheere bolein.",
      en: "Please say your 10-digit mobile number slowly.",
      bn: "Apnar 10-digit mobile number aaste bolun.",
      ta: "Unkal 10 ellakkam phone number sollunga.",
      te: "Meeru 10 number mobile number cheppandi.",
      mr: "Tumcha 10 anki mobile number saanga.",
      gu: "Tamaro 10 ankno mobile number kaho.",
      kn: "Nimma 10 anka mobile number heli.",
    },

    registerPassword: {
      hi: "Ab apni pasand ka password bolein. Koi bhi shabd ya ankon ka mel jo aapko yaad rahe.",
      en: "Now say a password — any word or number combination you can remember easily.",
      bn: "Akhon ekti password bolun. Jekono word ba number.",
      ta: "Ippo password sollunga. Virupta word ya number.",
      te: "Ippudu oka password cheppandi. Mee ishtamaina word ya number.",
      mr: "Aata password saanga. Konataahi shabda ya anka.",
      gu: "Hve password kaho. Koi pan shabd ya ank.",
      kn: "Ipa password heli. Yaavude shabda ya sankhye.",
    },

    registerDone: {
      hi: "Shaandaar! Aapka account ban raha hai. Abhi redirect ho raha hai...",
      en: "Amazing! Your account is being created. Redirecting now...",
      bn: "Oshadharon! Apnar account toiri hocche...",
      ta: "Miga Aruma! Unkal account tayaar aaguthu...",
      te: "Adhbhutam! Meeru account create avutundi...",
      mr: "Wah! Tumche account tayyar hote aahe...",
      gu: "Darun! Tamaru account bani rahu chhe...",
      kn: "Adbhuta! Nimma account create aagutide...",
    },

    // ── Job guide (post-login for workers) ──
    jobGuide: {
      hi: "Swagat hai! Ab aapka dashboard khul jayega. Wahan aap naye kaam dekh sakte hain, apni availability on ya off kar sakte hain, aur apna voice profile share kar sakte hain. Kya main aapko koi kaam dhundhne mein madad karoon?",
      en: "Welcome back! Your dashboard is ready. You can see new jobs, toggle availability, and share your voice profile. Would you like me to help find a job for you?",
      bn: "Swagata! Apnar dashboard khulbe. Notun kaj dekha, availability toggle kora, voice profile share kora sombot. Ki ami apnar jonnyo kaj khundhte paari?",
      ta: "Varaverkirom! Unkal dashboard ready. Puthu velai paarkkalam, availability toggle seiyalam. Oru velai thodukkattuma?",
      te: "Swaagatam! Meeru dashboard ready. Kotta jobs choosukoni, availability toggle cheyagalaru. Job ventukaraa?",
      mr: "Swagat! Tumcha dashboard tayaar aahe. Nawe kaam paha, availability on off kara. Job shodhu ka?",
      gu: "Swagat! Tama dashboard taiyaar chhe. Nava kaam juo, availability toggle karo. Job shodhu?",
      kn: "Swagata! Nimma dashboard ready. Hosa jobs nodi, availability toggle maadi. Job hoodali?",
    },

    // ── Error/retry messages ──
    retry: {
      hi: "Maafi kijiye, main samajh nahi paaya. Kripaya phir bolein.",
      en: "Sorry, I did not understand. Please say it again.",
      bn: "Kshoma korun, bujhte parchhi na. Abar bolun.",
      ta: "Mannikkanam, puriyavillai. Meedaan sollunga.",
      te: "Kshaminchaandi, artham kaaledhu. Meeru meeru cheppandi.",
      mr: "Maaf kara, samajala nahi. Parat saanga.",
      gu: "Maaf karo, samajyu nahi. Fari kaho.",
      kn: "Kshamisee, arthaagalilla. Matte heli.",
    },

    notSupported: {
      hi: "Khed hai, aapka browser voice support nahi karta. Kripaya Chrome use karein.",
      en: "Sorry, your browser does not support voice. Please use Chrome.",
    },

    jobNotify: {
      hi: "Aapke liye ek nayi job request aayi hai! Apna dashboard check karein.",
      en: "You have a new job request! Check your dashboard.",
      bn: "Apnar jonnyo notun kaj eshechhe! Dashboard dekun.",
      ta: "Unkalukku oru puthu velai vanthu! Dashboard parungu.",
      te: "Meeru kotta job vachindi! Dashboard chuskoandi.",
      mr: "Tumhala nawe kaam aale! Dashboard paha.",
      gu: "Tama mate navu kaam aavyu! Dashboard juo.",
      kn: "Nimge hosa job bande! Dashboard nodi.",
    }
  };

  /* ═══════════════════════════════════════════════════════════
     SECTION 3: CORE ENGINE
  ═══════════════════════════════════════════════════════════ */

  let currentLang = 'hi';
  let recognition = null;
  let isSpeaking = false;
  let currentFlow = null;     // 'login' | 'register_worker' | 'register_user'
  let flowStep = 0;
  let collectedData = {};
  let isListening = false;
  let botEnabled = false;

  // TTS — speak a string in the chosen language
  function speak(text, onEnd) {
    if (!window.speechSynthesis) return onEnd && onEnd();
    window.speechSynthesis.cancel();
    isSpeaking = true;
    const utter = new SpeechSynthesisUtterance(text);
    const langCode = (LANG_MAP[currentLang] || LANG_MAP.hi).code;
    utter.lang = langCode;
    utter.rate = 0.92;
    utter.pitch = 1.05;
    utter.volume = 1;

    // Try to find a matching voice
    const voices = window.speechSynthesis.getVoices();
    const match = voices.find(v => v.lang.startsWith(langCode.split('-')[0]));
    if (match) utter.voice = match;

    utter.onend = () => { isSpeaking = false; onEnd && onEnd(); };
    utter.onerror = () => { isSpeaking = false; onEnd && onEnd(); };
    window.speechSynthesis.speak(utter);
    updateBubble(text);
  }

  // STT — listen for a single phrase
  function listen(callback, lang) {
    if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      speak(get('notSupported'));
      return;
    }
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new Rec();
    recognition.lang = (LANG_MAP[lang || currentLang] || LANG_MAP.hi).code;
    recognition.interimResults = false;
    recognition.maxAlternatives = 3;
    recognition.continuous = false;

    setMicState(true);
    isListening = true;

    recognition.onresult = (e) => {
      isListening = false;
      setMicState(false);
      const results = Array.from(e.results[0]).map(r => r.transcript.trim().toLowerCase());
      callback(results[0], results);
    };
    recognition.onerror = () => {
      isListening = false;
      setMicState(false);
      callback('', []);
    };
    recognition.onend = () => {
      isListening = false;
      setMicState(false);
    };
    recognition.start();
  }

  // Helper: get dialogue for current language with fallback to English/Hindi
  function get(key) {
    const d = DIALOGUE[key];
    if (!d) return '';
    return d[currentLang] || d.en || d.hi || '';
  }

  /* ═══════════════════════════════════════════════════════════
     SECTION 4: UI COMPONENTS
  ═══════════════════════════════════════════════════════════ */

  function buildUI() {
    // Remove existing if any
    const existing = document.getElementById('vh-gateway-bot');
    if (existing) existing.remove();

    const el = document.createElement('div');
    el.id = 'vh-gateway-bot';
    el.innerHTML = `
      <div id="vhb-panel" class="vhb-panel vhb-panel--closed">
        <div class="vhb-header">
          <div class="vhb-avatar-wrap">
            <div class="vhb-avatar">
              <i class="fa-solid fa-robot"></i>
              <div class="vhb-pulse"></div>
            </div>
          </div>
          <div class="vhb-header-info">
            <div class="vhb-title">VoiceHire Assistant</div>
            <div class="vhb-status" id="vhb-status">
              <span class="vhb-dot"></span> <span id="vhb-status-text">Listening...</span>
            </div>
          </div>
          <button class="vhb-close" id="vhb-close" title="Close"><i class="fa-solid fa-xmark"></i></button>
        </div>

        <div class="vhb-body">
          <div class="vhb-bubble-wrap">
            <div class="vhb-bubble" id="vhb-bubble">
              Namaste! VoiceHire AI Assistant yahan hai...
            </div>
            <div class="vhb-wave" id="vhb-wave">
              <span></span><span></span><span></span><span></span><span></span>
            </div>
          </div>

          <!-- Language picker (shown at start) -->
          <div class="vhb-lang-grid" id="vhb-lang-grid">
            <div class="vhb-lang-title">🌐 Apni bhasha chunein / Choose Language</div>
            <div class="vhb-lang-btns">
              <button class="vhb-lang-btn active" data-lang="hi">🇮🇳 हिंदी</button>
              <button class="vhb-lang-btn" data-lang="en">🇬🇧 English</button>
              <button class="vhb-lang-btn" data-lang="bn">🇧🇩 বাংলা</button>
              <button class="vhb-lang-btn" data-lang="ta">🌟 தமிழ்</button>
              <button class="vhb-lang-btn" data-lang="te">🌟 తెలుగు</button>
              <button class="vhb-lang-btn" data-lang="mr">🇮🇳 मराठी</button>
              <button class="vhb-lang-btn" data-lang="gu">🇮🇳 ગુજરાતી</button>
              <button class="vhb-lang-btn" data-lang="kn">🌟 ಕನ್ನಡ</button>
            </div>
          </div>

          <!-- Role choice buttons (shown after language select) -->
          <div class="vhb-choice-grid" id="vhb-choice-grid" style="display:none">
          </div>

          <!-- Mic indicator row -->
          <div class="vhb-mic-row" id="vhb-mic-row" style="display:none">
            <button class="vhb-mic-btn" id="vhb-mic-btn" title="Tap to speak">
              <i class="fa-solid fa-microphone"></i>
            </button>
            <span class="vhb-mic-hint" id="vhb-mic-hint">Tap to speak</span>
          </div>
        </div>
      </div>

      <!-- Floating button -->
      <button class="vhb-fab" id="vhb-fab" title="AI Voice Assistant">
        <i class="fa-solid fa-robot"></i>
        <span class="vhb-fab-ping"></span>
      </button>
    `;

    // Styles
    const style = document.createElement('style');
    style.textContent = `
      #vh-gateway-bot {
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 9999;
        font-family: 'Inter', sans-serif;
      }

      /* FAB */
      .vhb-fab {
        width: 62px; height: 62px;
        border-radius: 50%;
        background: linear-gradient(135deg, #4F46E5, #7C3AED);
        border: none; cursor: pointer;
        box-shadow: 0 8px 32px rgba(79,70,229,.45);
        display: flex; align-items: center; justify-content: center;
        font-size: 1.4rem; color: white;
        transition: transform .2s ease, box-shadow .2s ease;
        position: relative;
      }
      .vhb-fab:hover { transform: scale(1.08); box-shadow: 0 12px 40px rgba(79,70,229,.55); }
      .vhb-fab-ping {
        position: absolute; top: 0; right: 0;
        width: 14px; height: 14px;
        background: #10B981; border-radius: 50%;
        border: 2px solid white;
        animation: vhb-ping 1.6s ease infinite;
      }
      @keyframes vhb-ping {
        0%,100% { transform: scale(1); opacity:1; }
        50% { transform: scale(1.4); opacity:.6; }
      }

      /* Panel */
      .vhb-panel {
        position: absolute; bottom: 76px; right: 0;
        width: 340px;
        background: white;
        border-radius: 20px;
        box-shadow: 0 24px 64px rgba(0,0,0,.18);
        overflow: hidden;
        transform-origin: bottom right;
        transition: transform .25s cubic-bezier(.34,1.56,.64,1), opacity .2s ease;
      }
      .vhb-panel--closed { transform: scale(.85); opacity: 0; pointer-events: none; }
      .vhb-panel--open   { transform: scale(1);   opacity: 1; pointer-events: all; }

      /* Header */
      .vhb-header {
        background: linear-gradient(135deg, #4F46E5, #7C3AED);
        padding: 16px;
        display: flex; align-items: center; gap: 12px;
      }
      .vhb-avatar-wrap { position: relative; }
      .vhb-avatar {
        width: 44px; height: 44px;
        background: rgba(255,255,255,.2);
        border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.2rem; color: white;
        position: relative;
      }
      .vhb-pulse {
        position: absolute; inset: -3px;
        border-radius: 50%;
        border: 2px solid rgba(255,255,255,.4);
        animation: vhb-pulse 2s ease infinite;
      }
      @keyframes vhb-pulse {
        0%,100% { transform: scale(1); opacity:1; }
        50%      { transform: scale(1.15); opacity:.5; }
      }
      .vhb-header-info { flex: 1; }
      .vhb-title { color: white; font-weight: 700; font-size: .95rem; }
      .vhb-status { display: flex; align-items: center; gap: 5px; margin-top: 2px; }
      .vhb-dot { width: 7px; height: 7px; background: #10B981; border-radius: 50%; }
      #vhb-status-text { font-size: .72rem; color: rgba(255,255,255,.8); }
      .vhb-close {
        background: rgba(255,255,255,.15); border: none;
        color: white; width: 28px; height: 28px;
        border-radius: 50%; cursor: pointer; font-size: .8rem;
        display: flex; align-items: center; justify-content: center;
        transition: background .15s;
      }
      .vhb-close:hover { background: rgba(255,255,255,.3); }

      /* Body */
      .vhb-body { padding: 16px; display: flex; flex-direction: column; gap: 14px; }

      /* Bubble */
      .vhb-bubble-wrap { display: flex; flex-direction: column; gap: 8px; }
      .vhb-bubble {
        background: linear-gradient(135deg, #EEF2FF, #F5F3FF);
        border: 1px solid #C7D2FE;
        border-radius: 14px 14px 14px 4px;
        padding: 12px 14px;
        font-size: .875rem; color: #1E1B4B;
        line-height: 1.5;
        min-height: 52px;
        transition: all .3s ease;
      }

      /* Wave animation (speaking indicator) */
      .vhb-wave {
        display: flex; align-items: center; gap: 3px;
        padding-left: 4px; height: 20px;
        opacity: 0; transition: opacity .2s;
      }
      .vhb-wave.speaking { opacity: 1; }
      .vhb-wave span {
        display: block; width: 4px;
        border-radius: 2px;
        background: #4F46E5;
        animation: vhb-bar 1.1s ease-in-out infinite;
      }
      .vhb-wave span:nth-child(1) { animation-delay: 0s; }
      .vhb-wave span:nth-child(2) { animation-delay: .15s; }
      .vhb-wave span:nth-child(3) { animation-delay: .30s; }
      .vhb-wave span:nth-child(4) { animation-delay: .45s; }
      .vhb-wave span:nth-child(5) { animation-delay: .60s; }
      @keyframes vhb-bar {
        0%,100% { height: 4px; }
        50% { height: 20px; }
      }

      /* Language grid */
      .vhb-lang-title { font-size: .78rem; color: #6B7280; font-weight: 600; text-align:center; margin-bottom: 8px; }
      .vhb-lang-btns { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; }
      .vhb-lang-btn {
        padding: 6px 12px;
        border: 1.5px solid #E5E7EB;
        background: white; border-radius: 20px;
        font-size: .8rem; cursor: pointer;
        transition: all .15s ease;
        font-family: inherit;
      }
      .vhb-lang-btn:hover, .vhb-lang-btn.active {
        border-color: #4F46E5; background: #EEF2FF;
        color: #4F46E5; font-weight: 600;
      }

      /* Choice buttons */
      .vhb-choice-grid { display: flex; flex-direction: column; gap: 8px; }
      .vhb-choice-btn {
        display: flex; align-items: center; gap: 10px;
        padding: 12px 16px;
        border: 1.5px solid #E5E7EB;
        background: white; border-radius: 12px;
        font-size: .875rem; cursor: pointer;
        text-align: left; transition: all .15s ease;
        font-family: inherit;
      }
      .vhb-choice-btn:hover { border-color: #4F46E5; background: #EEF2FF; }
      .vhb-choice-btn .vhb-choice-icon { font-size: 1.4rem; }
      .vhb-choice-btn strong { color: #1E1B4B; }
      .vhb-choice-btn span { color: #6B7280; font-size: .78rem; }

      /* Mic row */
      .vhb-mic-row {
        display: flex; align-items: center; gap: 12px;
        background: #F9FAFB; border-radius: 12px;
        padding: 10px 14px;
      }
      .vhb-mic-btn {
        width: 42px; height: 42px;
        border-radius: 50%;
        background: linear-gradient(135deg, #4F46E5, #7C3AED);
        border: none; color: white; font-size: 1rem;
        cursor: pointer; display: flex; align-items: center; justify-content: center;
        transition: transform .15s ease, box-shadow .15s ease;
        flex-shrink: 0;
      }
      .vhb-mic-btn:hover { transform: scale(1.1); }
      .vhb-mic-btn.listening {
        animation: vhb-mic-pulse 1s ease infinite;
        background: linear-gradient(135deg, #DC2626, #B91C1C);
      }
      @keyframes vhb-mic-pulse {
        0%,100% { box-shadow: 0 0 0 0 rgba(220,38,38,.4); }
        50%      { box-shadow: 0 0 0 10px rgba(220,38,38,0); }
      }
      .vhb-mic-hint { font-size: .8rem; color: #6B7280; }

      @media (max-width: 400px) {
        .vhb-panel { width: calc(100vw - 32px); right: -8px; }
      }
    `;
    document.head.appendChild(style);
    document.body.appendChild(el);

    // Wire events
    document.getElementById('vhb-fab').addEventListener('click', openPanel);
    document.getElementById('vhb-close').addEventListener('click', closePanel);

    // Language buttons
    document.querySelectorAll('.vhb-lang-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.vhb-lang-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        onLangSelected(btn.dataset.lang);
      });
    });

    // Manual mic button
    document.getElementById('vhb-mic-btn').addEventListener('click', () => {
      if (!isListening && !isSpeaking) manualListen();
    });
  }

  function openPanel() {
    const panel = document.getElementById('vhb-panel');
    panel.classList.remove('vhb-panel--closed');
    panel.classList.add('vhb-panel--open');
    if (!botEnabled) {
      botEnabled = true;
      startFlow();
    }
  }

  function closePanel() {
    const panel = document.getElementById('vhb-panel');
    panel.classList.remove('vhb-panel--open');
    panel.classList.add('vhb-panel--closed');
    window.speechSynthesis && window.speechSynthesis.cancel();
  }

  function updateBubble(text) {
    const b = document.getElementById('vhb-bubble');
    if (b) b.textContent = text;
  }

  function setStatus(text) {
    const s = document.getElementById('vhb-status-text');
    if (s) s.textContent = text;
  }

  function setMicState(active) {
    const btn = document.getElementById('vhb-mic-btn');
    if (!btn) return;
    btn.classList.toggle('listening', active);
    const hint = document.getElementById('vhb-mic-hint');
    if (hint) hint.textContent = active ? 'Listening...' : 'Tap to speak';
    setStatus(active ? '🎙️ Listening...' : 'Online · Ready');
    const wave = document.getElementById('vhb-wave');
    if (wave) wave.classList.toggle('speaking', isSpeaking || active);
  }

  function showLangGrid(show) {
    const g = document.getElementById('vhb-lang-grid');
    if (g) g.style.display = show ? '' : 'none';
  }

  function showChoiceGrid(buttons) {
    const g = document.getElementById('vhb-choice-grid');
    if (!g) return;
    g.innerHTML = '';
    g.style.display = buttons && buttons.length ? 'flex' : 'none';
    (buttons || []).forEach(b => {
      const el = document.createElement('button');
      el.className = 'vhb-choice-btn';
      el.innerHTML = `<span class="vhb-choice-icon">${b.icon}</span><div><strong>${b.label}</strong><br><span>${b.sub}</span></div>`;
      el.addEventListener('click', b.action);
      g.appendChild(el);
    });
  }

  function showMicRow(show) {
    const r = document.getElementById('vhb-mic-row');
    if (r) r.style.display = show ? 'flex' : 'none';
  }

  /* ═══════════════════════════════════════════════════════════
     SECTION 5: FLOW ORCHESTRATOR
  ═══════════════════════════════════════════════════════════ */

  function startFlow() {
    // Auto-open panel after 1.5s
    setTimeout(() => {
      openPanel();
      // Wait for voices to load then boot
      if (window.speechSynthesis.getVoices().length === 0) {
        window.speechSynthesis.onvoiceschanged = bootGreet;
      } else {
        bootGreet();
      }
    }, 800);
  }

  function bootGreet() {
    setStatus('Speaking...');
    const wave = document.getElementById('vhb-wave');
    if (wave) wave.classList.add('speaking');
    speak(get('boot'), () => {
      if (wave) wave.classList.remove('speaking');
      // After speaking, listen for language preference via voice too
      listenForLanguage();
    });
  }

  function listenForLanguage() {
    setStatus('Say your language or tap a button below');
    showLangGrid(true);
    // Also listen for voice input
    listen((transcript) => {
      if (!transcript) return; // user will use button
      const t = transcript.toLowerCase();
      if (t.includes('english') || t.includes('angrezi') || t.includes('inglish')) {
        onLangSelected('en');
      } else if (t.includes('hindi') || t.includes('हिंदी') || t.includes('hind')) {
        onLangSelected('hi');
      } else if (t.includes('bangla') || t.includes('bengali') || t.includes('বাংলা')) {
        onLangSelected('bn');
      } else if (t.includes('tamil') || t.includes('தமிழ்')) {
        onLangSelected('ta');
      } else if (t.includes('telugu') || t.includes('తెలుగు')) {
        onLangSelected('te');
      } else if (t.includes('marathi') || t.includes('मराठी')) {
        onLangSelected('mr');
      } else if (t.includes('gujarati') || t.includes(' gujarati')) {
        onLangSelected('gu');
      } else if (t.includes('kannada') || t.includes('ಕನ್ನಡ')) {
        onLangSelected('kn');
      } else {
        // default to Hindi
        onLangSelected('hi');
      }
    }, 'hi'); // always listen in Hindi for language selection
  }

  function onLangSelected(lang) {
    currentLang = lang;
    // Highlight button
    document.querySelectorAll('.vhb-lang-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.lang === lang);
    });
    showLangGrid(false);
    const wave = document.getElementById('vhb-wave');
    if (wave) wave.classList.add('speaking');
    speak(get('langConfirm'), () => {
      if (wave) wave.classList.remove('speaking');
      setTimeout(askNewOrLogin, 400);
    });
  }

  function askNewOrLogin() {
    speak(get('roleAsk'), () => {
      showChoiceGrid([
        {
          icon: '🔑',
          label: currentLang === 'hi' ? 'Login' : 'Login',
          sub: currentLang === 'hi' ? 'Pehle se account hai' : 'I already have an account',
          action: () => { showChoiceGrid([]); startLoginFlow(); }
        },
        {
          icon: '✨',
          label: currentLang === 'hi' ? 'Nayi Profile' : 'New Profile',
          sub: currentLang === 'hi' ? 'Pehli baar hoon' : 'First time here',
          action: () => { showChoiceGrid([]); startRegisterFlow(); }
        }
      ]);
      // Also listen for voice
      listen((transcript) => {
        if (!transcript) return;
        const t = transcript.toLowerCase();
        const isLogin = t.includes('login') || t.includes('mazdoor') || t.includes('log') ||
                        t.includes('pehle') || t.includes('account') || t.includes('exist');
        if (isLogin) {
          showChoiceGrid([]);
          startLoginFlow();
        } else {
          showChoiceGrid([]);
          startRegisterFlow();
        }
      });
    });
  }

  /* ───── LOGIN FLOW ───── */
  function startLoginFlow() {
    currentFlow = 'login';
    collectedData = {};
    speak(get('loginStart'), () => {
      showChoiceGrid([
        {
          icon: '🔧',
          label: currentLang === 'hi' ? 'Mazdoor / Worker' : 'Worker',
          sub: currentLang === 'hi' ? 'Kaam dhundh raha hoon' : 'Looking for work',
          action: () => { showChoiceGrid([]); collectedData.role = 'worker'; askLoginPhone(); }
        },
        {
          icon: '🏢',
          label: currentLang === 'hi' ? 'Maalik / Employer' : 'Employer',
          sub: currentLang === 'hi' ? 'Kaam dena chahta hoon' : 'Hiring workers',
          action: () => { showChoiceGrid([]); collectedData.role = 'user'; askLoginPhone(); }
        }
      ]);
      listen((t) => {
        if (!t) return;
        if (t.includes('worker') || t.includes('mazdoor') || t.includes('kaam') || t.includes('dhundh')) {
          showChoiceGrid([]);
          collectedData.role = 'worker';
          askLoginPhone();
        } else {
          showChoiceGrid([]);
          collectedData.role = 'user';
          askLoginPhone();
        }
      });
    });
  }

  function askLoginPhone() {
    showMicRow(true);
    speak(get('loginPhone'), () => {
      listen((t) => {
        const phone = extractPhone(t);
        if (phone) {
          collectedData.phone = phone;
          updateBubble('📱 ' + phone);
          askLoginPassword();
        } else {
          speak(get('retry'), () => askLoginPhone());
        }
      });
    });
  }

  function askLoginPassword() {
    speak(get('loginPassword'), () => {
      listen((t) => {
        if (t && t.length >= 3) {
          collectedData.password = t.replace(/\s+/g, '');
          speak(get('loginDone'), () => {
            submitLogin();
          });
        } else {
          speak(get('retry'), () => askLoginPassword());
        }
      });
    });
  }

  function submitLogin() {
    showMicRow(false);
    setStatus('Logging in...');
    fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        phone: collectedData.phone,
        password: collectedData.password,
        role: collectedData.role
      })
    })
    .then(r => r.json())
    .then(data => {
      if (data.redirect) {
        window.location.href = data.redirect;
      } else {
        speak(get('retry') + '. ' + (data.error || ''), () => {
          setTimeout(() => startLoginFlow(), 600);
        });
      }
    })
    .catch(() => {
      speak(get('retry'), () => setTimeout(() => startLoginFlow(), 600));
    });
  }

  /* ───── REGISTER FLOW ───── */
  function startRegisterFlow() {
    currentFlow = 'register';
    collectedData = {};
    speak(get('registerWho'), () => {
      showChoiceGrid([
        {
          icon: '🔧',
          label: currentLang === 'hi' ? 'Mazdoor / Worker' : 'Worker',
          sub: currentLang === 'hi' ? 'Kaam dhundh raha hoon' : 'Looking for work',
          action: () => { showChoiceGrid([]); collectedData.role = 'worker'; askRegisterName(); }
        },
        {
          icon: '🏢',
          label: currentLang === 'hi' ? 'Maalik / Employer' : 'Employer',
          sub: currentLang === 'hi' ? 'Kaam dena chahta hoon' : 'Hiring workers',
          action: () => { showChoiceGrid([]); collectedData.role = 'user'; askUserName(); }
        }
      ]);
      listen((t) => {
        if (!t) return;
        if (t.includes('worker') || t.includes('mazdoor') || t.includes('kaam')) {
          showChoiceGrid([]); collectedData.role = 'worker'; askRegisterName();
        } else {
          showChoiceGrid([]); collectedData.role = 'user'; askUserName();
        }
      });
    });
  }

  // ── Worker registration steps ──
  function askRegisterName() {
    showMicRow(true);
    speak(get('registerName'), () => {
      listen((t) => {
        if (t && t.length > 2) {
          collectedData.name = toTitleCase(t);
          updateBubble('👤 ' + collectedData.name);
          askRegisterWork();
        } else {
          speak(get('retry'), () => askRegisterName());
        }
      });
    });
  }

  function askRegisterWork() {
    speak(get('registerWork'), () => {
      listen((t) => {
        if (t && t.length > 1) {
          collectedData.work = toTitleCase(t);
          updateBubble('🔧 ' + collectedData.work);
          askRegisterLocation();
        } else {
          speak(get('retry'), () => askRegisterWork());
        }
      });
    });
  }

  function askRegisterLocation() {
    speak(get('registerLocation'), () => {
      listen((t) => {
        if (t && t.length > 1) {
          collectedData.location = toTitleCase(t);
          updateBubble('📍 ' + collectedData.location);
          askRegisterPhone();
        } else {
          speak(get('retry'), () => askRegisterLocation());
        }
      });
    });
  }

  function askRegisterPhone() {
    speak(get('registerPhone'), () => {
      listen((t) => {
        const phone = extractPhone(t);
        if (phone) {
          collectedData.phone = phone;
          updateBubble('📱 ' + phone);
          askRegisterPassword();
        } else {
          speak(get('retry'), () => askRegisterPhone());
        }
      });
    });
  }

  function askRegisterPassword() {
    speak(get('registerPassword'), () => {
      listen((t) => {
        if (t && t.length >= 4) {
          collectedData.password = t.replace(/\s+/g, '');
          speak(get('registerDone'), () => submitWorkerRegister());
        } else {
          speak(get('retry'), () => askRegisterPassword());
        }
      });
    });
  }

  function submitWorkerRegister() {
    showMicRow(false);
    setStatus('Creating account...');
    const fd = new FormData();
    fd.append('name', collectedData.name || '');
    fd.append('work', collectedData.work || '');
    fd.append('location', collectedData.location || '');
    fd.append('phone', collectedData.phone || '');
    fd.append('password', collectedData.password || '');

    fetch('/api/auth/signup/worker', { method: 'POST', body: fd })
      .then(r => r.json())
      .then(data => {
        if (data.redirect) {
          window.location.href = data.redirect;
        } else {
          speak((data.error || get('retry')), () => setTimeout(() => startRegisterFlow(), 800));
        }
      })
      .catch(() => speak(get('retry'), () => setTimeout(() => startRegisterFlow(), 800)));
  }

  // ── Employer (user) registration steps ──
  function askUserName() {
    showMicRow(true);
    speak(get('registerName'), () => {
      listen((t) => {
        if (t && t.length > 2) {
          collectedData.name = toTitleCase(t);
          updateBubble('👤 ' + collectedData.name);
          askUserPhone();
        } else {
          speak(get('retry'), () => askUserName());
        }
      });
    });
  }

  function askUserPhone() {
    speak(get('registerPhone'), () => {
      listen((t) => {
        const phone = extractPhone(t);
        if (phone) {
          collectedData.phone = phone;
          updateBubble('📱 ' + phone);
          askUserPassword();
        } else {
          speak(get('retry'), () => askUserPhone());
        }
      });
    });
  }

  function askUserPassword() {
    speak(get('registerPassword'), () => {
      listen((t) => {
        if (t && t.length >= 4) {
          collectedData.password = t.replace(/\s+/g, '');
          speak(get('registerDone'), () => submitUserRegister());
        } else {
          speak(get('retry'), () => askUserPassword());
        }
      });
    });
  }

  function submitUserRegister() {
    showMicRow(false);
    setStatus('Creating account...');
    const fd = new FormData();
    fd.append('name', collectedData.name || '');
    fd.append('phone', collectedData.phone || '');
    fd.append('password', collectedData.password || '');

    fetch('/api/auth/signup/user', { method: 'POST', body: fd })
      .then(r => r.json())
      .then(data => {
        if (data.redirect) {
          window.location.href = data.redirect;
        } else {
          speak((data.error || get('retry')), () => setTimeout(() => startRegisterFlow(), 800));
        }
      })
      .catch(() => speak(get('retry'), () => setTimeout(() => startRegisterFlow(), 800)));
  }

  /* ═══════════════════════════════════════════════════════════
     SECTION 6: JOB NOTIFICATION SYSTEM
     Polls for new job requests every 60s and speaks an alert
  ═══════════════════════════════════════════════════════════ */

  let lastJobCount = null;

  function startJobNotifyLoop() {
    // Only for logged-in workers
    if (!window.VH || window.VH.role !== 'worker') return;
    setInterval(checkForNewJobs, 60000); // every 60 seconds
  }

  function checkForNewJobs() {
    fetch('/api/jobs?work=' + encodeURIComponent((window.VH && window.VH.work) || ''))
      .then(r => r.json())
      .then(jobs => {
        if (!Array.isArray(jobs)) return;
        const openJobs = jobs.filter(j => j.status === 'open').length;
        if (lastJobCount !== null && openJobs > lastJobCount) {
          speakJobAlert();
        }
        lastJobCount = openJobs;
      })
      .catch(() => {});
  }

  function speakJobAlert() {
    // Show a toast notification
    if (typeof showToast === 'function') {
      showToast(get('jobNotify'), 'success');
    }
    // Speak the alert
    speak(get('jobNotify'));
  }

  /* ─── Manual mic: let user re-ask a question by tapping mic ─── */
  let manualListenCallback = null;
  function manualListen() {
    setMicState(true);
    listen((t) => {
      if (manualListenCallback) manualListenCallback(t);
    });
  }

  /* ═══════════════════════════════════════════════════════════
     SECTION 7: UTILITY HELPERS
  ═══════════════════════════════════════════════════════════ */

  function extractPhone(text) {
    if (!text) return null;
    const digits = text.replace(/\D/g, '');
    if (digits.length >= 10) {
      const phone = digits.slice(-10); // take last 10 digits
      if (/^[6-9]\d{9}$/.test(phone)) return phone;
    }
    // spoken-number words to digits mapping
    const wordMap = { zero:0, one:1, two:2, three:3, four:4, five:5,
                      six:6, seven:7, eight:8, nine:9,
                      shoonya:0, ek:1, do:2, teen:3, chaar:4,
                      paanch:5, chhe:6, saat:7, aath:8, nau:9 };
    let num = '';
    text.split(/\s+/).forEach(w => {
      const d = wordMap[w.toLowerCase()];
      if (d !== undefined) num += d;
      else if (/^\d$/.test(w)) num += w;
    });
    if (num.length >= 10 && /^[6-9]\d{9}$/.test(num.slice(-10))) return num.slice(-10);
    return null;
  }

  function toTitleCase(str) {
    return str.replace(/\w\S*/g, t => t.charAt(0).toUpperCase() + t.slice(1).toLowerCase());
  }

  /* ═══════════════════════════════════════════════════════════
     SECTION 8: INIT
  ═══════════════════════════════════════════════════════════ */

  function init() {
    // Only run on landing/gateway page (not authenticated dashboards)
    const isGateway = !window.VH || !window.VH.userId;
    if (!isGateway) {
      // On authenticated pages: just run job notification loop
      startJobNotifyLoop();
      return;
    }

    buildUI();

    // Auto-open after 2 seconds of page load
    setTimeout(() => {
      openPanel();
      setTimeout(() => {
        botEnabled = true;
        if (window.speechSynthesis.getVoices().length === 0) {
          window.speechSynthesis.onvoiceschanged = bootGreet;
        } else {
          bootGreet();
        }
      }, 600);
    }, 2000);
  }

  // Wait for DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
