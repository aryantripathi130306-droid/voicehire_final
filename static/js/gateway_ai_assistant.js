/**
 * VoiceHire — Unified AI Voice Assistant
 * ═══════════════════════════════════════════════════════════════════
 * Single source of truth. Replaces both voice_guide_bot.js (gateway)
 * and the old gateway_ai_assistant.js.
 *
 * BEHAVIOUR BY PAGE:
 *  / (gateway)   → Auto-open after 2s. Full guided onboarding flow.
 *  /signup/*     → Auto-open. Fill form by voice.
 *  /login        → Auto-open. Fill form by voice.
 *  /dashboard/*  → Show floating button. Speak job notifications.
 *
 * LANGUAGE SUPPORT (22 Indian languages + English):
 *  hi, en, bn, ta, te, mr, gu, kn, ml, pa, or, as, ur,
 *  mai, bh, ne, sd, kok, mni, sat, ks, doi
 *
 * FLOW:
 *  GATEWAY → greet (Hindi) → lang select → login/register → dashboard guide
 *  SIGNUP  → greet → fill name/work/location/phone/password → submit
 *  LOGIN   → greet → fill role/phone/password → submit
 * ═══════════════════════════════════════════════════════════════════
 */
(function () {
  'use strict';

  /* ───────────────────────────────────────────────────────────────
     GUARD: Prevent double-init if script is loaded multiple times
  ─────────────────────────────────────────────────────────────── */
  if (window.__VH_AI_INIT__) return;
  window.__VH_AI_INIT__ = true;

  /* ───────────────────────────────────────────────────────────────
     1. LANGUAGE REGISTRY
     Maps language code → { name, nativeName, speechCode, flag }
  ─────────────────────────────────────────────────────────────── */
  const LANGS = {
    hi: { name: 'Hindi',     native: 'हिंदी',      speech: 'hi-IN', flag: '🇮🇳' },
    en: { name: 'English',   native: 'English',    speech: 'en-IN', flag: '🇬🇧' },
    bn: { name: 'Bangla',    native: 'বাংলা',      speech: 'bn-IN', flag: '🇧🇩' },
    ta: { name: 'Tamil',     native: 'தமிழ்',      speech: 'ta-IN', flag: '🌟' },
    te: { name: 'Telugu',    native: 'తెలుగు',     speech: 'te-IN', flag: '🌟' },
    mr: { name: 'Marathi',   native: 'मराठी',      speech: 'mr-IN', flag: '🇮🇳' },
    gu: { name: 'Gujarati',  native: 'ગુજરાતી',   speech: 'gu-IN', flag: '🇮🇳' },
    kn: { name: 'Kannada',   native: 'ಕನ್ನಡ',     speech: 'kn-IN', flag: '🌟' },
    ml: { name: 'Malayalam', native: 'മലയാളം',     speech: 'ml-IN', flag: '🌟' },
    pa: { name: 'Punjabi',   native: 'ਪੰਜਾਬੀ',    speech: 'pa-IN', flag: '🇮🇳' },
    or: { name: 'Odia',      native: 'ଓଡ଼ିଆ',    speech: 'or-IN', flag: '🌟' },
    as: { name: 'Assamese',  native: 'অসমীয়া',   speech: 'as-IN', flag: '🌟' },
    ur: { name: 'Urdu',      native: 'اردو',       speech: 'ur-IN', flag: '🇮🇳' },
    ne: { name: 'Nepali',    native: 'नेपाली',     speech: 'ne-IN', flag: '🏔️' },
    kok:{ name: 'Konkani',   native: 'कोंकणी',    speech: 'kok-IN',flag: '🌟' },
  };

  /* ───────────────────────────────────────────────────────────────
     2. DIALOGUE LIBRARY
     Every string the AI speaks — keyed by lang code.
     Falls back: lang → en → hi
  ─────────────────────────────────────────────────────────────── */
  const D = {
    /* ── Gateway boot (always spoken in Hindi first) ── */
    boot: {
      _always_hi: "Namaste! Main VoiceHire ka AI Assistant hoon. Kya aap Hindi mein baat karna chahenge? Ya kisi aur bhasha mein baat karna chahte hain? Aap apni bhasha ka naam bol sakte hain ya neeche se select kar sakte hain.",
    },

    langDetectHint: {
      _always: "Apni bhasha bolein — Hindi, English, Tamil, Telugu, Bangla..."
    },

    langConfirm: {
      hi: "Bahut achha! Ab hum Hindi mein baat karenge.",
      en: "Great! We will continue in English.",
      bn: "Khub bhalo! Ekhon Banglay kotha bolbo.",
      ta: "Nanru! Naan unkalukku Tamil-il pEsuvEn.",
      te: "Chala bagundi! Ippudu Telugu lo maatunadam.",
      mr: "Chhan! Aata Marathi madhye boluyat.",
      gu: "Saras! Hve Gujarati ma vaat karishu.",
      kn: "Chennaagi! Kannada-alli maatunaadona.",
      ml: "Nannai! Malayalathil samsarikkaam.",
      pa: "Bahut vaddhia! Hun Punjabi vich gall karange.",
      or: "Bhala! Odia re kathaa hebu.",
      as: "Bhal! Asomiya bhashat kotha patio.",
      ur: "Bohat achhaa! Ab Urdu mein baat karte hain.",
      ne: "Ramro! Nepali ma kura garau.",
      kok:"Boro! Aata Konkani-t ulovuya.",
    },

    /* ── Gateway: new or existing user? ── */
    roleAsk: {
      hi: "Kya aap VoiceHire par pehle aaye hain? Agar aapka account hai to 'Login' bolein. Agar nayi profile banana chahte hain to 'Nayi Profile' bolein.",
      en: "Have you used VoiceHire before? Say 'Login' if you have an account, or 'New Profile' to register.",
      bn: "Apni ki age VoiceHire use korechhen? 'Login' bolun jodi account ache, noyto 'Notun Profile' bolun.",
      ta: "Neenga munbe VoiceHire upatiteenga? 'Login' sollunga illaiyal 'Puthu Profile' sollunga.",
      te: "Meeru mundhu VoiceHire vadilaaraa? Account unte 'Login' cheppandi, ledante 'Kotta Profile' cheppandi.",
      mr: "Tumhi aadhi VoiceHire vaparla aahe ka? 'Login' mhana kiva 'Navi Profile' mhana.",
      gu: "Shu tame pehla VoiceHire vapro chho? 'Login' kaho ya 'Navi Profile' kaho.",
      kn: "Neenu modalu VoiceHire upayogisiddiya? 'Login' helo illava 'Nava Profile' helo.",
      ml: "Neengu munpe VoiceHire upayogicchittundo? 'Login' paro allenkil 'Puthiya Profile' paro.",
      pa: "Kya tusi pehlan VoiceHire use kita? 'Login' kaho ya 'Naya Profile' kaho.",
      or: "Aapana purbaru VoiceHire bahibaru achi ki? 'Login' kahu nahi hole 'Nua Profile' kahu.",
      ur: "Kya aap pehle VoiceHire use kar chuke hain? 'Login' bolein ya 'Nayi Profile' bolein.",
      ne: "Tapaiले pahile VoiceHire prayog garnu bhayo? 'Login' bhannu ya 'Naya Profile' bhannu.",
    },

    /* ── Worker type question ── */
    workerOrUser: {
      hi: "Aap kaun hain? Kya aap kaam dhundhne waale hain? To 'Mazdoor' bolein. Ya aap kisi ko hire karna chahte hain? To 'Maalik' bolein.",
      en: "Are you a Worker looking for jobs, or an Employer looking to hire? Say 'Worker' or 'Employer'.",
      bn: "Apni Worker naki Employer? 'Worker' ba 'Employer' bolun.",
      ta: "Neenga Worker-a Employer-a? 'Worker' ya 'Employer' sollunga.",
      te: "Meeru Worker aa Employer aa? 'Worker' cheppandi ya 'Employer' cheppandi.",
      mr: "Tumhi Worker aahat ka Employer? 'Worker' ya 'Employer' mhana.",
      gu: "Tame Worker cho ke Employer? 'Worker' ya 'Employer' kaho.",
      kn: "Neenu Worker-aa Employer-aa? 'Worker' helo ya 'Employer' helo.",
      ml: "Neenu Worker-aano Employer-aano? 'Worker' paro ya 'Employer' paro.",
      pa: "Tusi Worker ho ya Employer? 'Worker' ya 'Employer' kaho.",
      or: "Aapana Worker naki Employer? 'Worker' ba 'Employer' kahu.",
      ur: "Aap Worker hain ya Employer? 'Worker' ya 'Employer' bolein.",
      ne: "Tapai Worker ho ki Employer? 'Worker' bhannu ya 'Employer' bhannu.",
    },

    /* ── Login flow ── */
    loginPhone: {
      hi: "Theek hai! Apna 10 ankon ka mobile number dheere dheere bolein.",
      en: "Please say your 10-digit mobile number slowly and clearly.",
      bn: "Apnar 10-digit mobile number aaste bolun.",
      ta: "Unkal 10 ellakkam phone number mella sollunga.",
      te: "Meeru 10 annelaphone number meesta meesta cheppandi.",
      mr: "Tumcha 10 anki mobile number savakar saanga.",
      gu: "Tamaro 10 ankno mobile number dhire dhire kaho.",
      kn: "Nimma 10 anka mobile number nidhanavagi heli.",
      ml: "Nimma 10 akkam phone number peethiyayi parayo.",
      pa: "Apna 10-anka wala mobile number dhire dhire kaho.",
      or: "Apananka 10-anka mobile number aaste aaste kahu.",
      ur: "Apna 10 ankon ka mobile number dheere bolein.",
      ne: "Tapaiको 10 anka mobile number bistaarai bhannu.",
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
      ml: "Ippol nimma password parayo.",
      pa: "Hune apna password kaho.",
      or: "Ebeye apananka password kahu.",
      ur: "Ab apna password bolein.",
      ne: "Aba tapaiको password bhannu.",
    },

    loginSubmitting: {
      hi: "Bahut achha! Login ho raha hai...",
      en: "Perfect! Logging you in now...",
      bn: "Khub bhalo! Akhon login hochhe...",
      ta: "Arumai! Ippoluthu login aaguthu...",
      te: "Chala bagundi! Ippudu login avutundi...",
      mr: "Mast! Aata login hoto aahe...",
      gu: "Saras! Hve login thai rahu chhe...",
      kn: "Tumba Chenna! Ipa login aagutide...",
      ml: "Kollaam! Ippol login aakkunnu...",
      pa: "Bahut vaddhia! Hune login ho raha hai...",
      ur: "Bahut achha! Login ho raha hai...",
      ne: "Raamro! Login hudai cha...",
    },

    /* ── Register flow ── */
    regName: {
      hi: "Aapka poora naam kya hai? Kripaya bolein.",
      en: "What is your full name? Please say it clearly.",
      bn: "Apnar puro naam ki? Sposto kore bolun.",
      ta: "Unkal peyar enna? Thirivaay sollunga.",
      te: "Meeru peru emiti? Cheppandi.",
      mr: "Tumche poorne naav saanga.",
      gu: "Tamaru puru naam kaho.",
      kn: "Nimma hesa heli.",
      ml: "Nimma pera parayo.",
      pa: "Apna poora naam kaho.",
      or: "Apananka poora naam kahu.",
      ur: "Aapka poora naam bolein.",
      ne: "Tapaiको puraa naam bhannu.",
    },

    regWork: {
      hi: "Aap kya kaam karte hain? Jaise plumber, electrician, carpenter, safaiwala, driver, cook...",
      en: "What is your profession? For example: plumber, electrician, driver, cook, cleaner, carpenter...",
      bn: "Apni ki kaj koren? Jemon plumber, electrician, driver, cook...",
      ta: "Neenga enna velai seikireerga? Udaharanam: plumber, electrician, driver...",
      te: "Meeru em pani chestaaru? Udaharanaku: plumber, electrician, driver...",
      mr: "Tumhi konte kaam karta? Udaaharan: plumber, electrician, driver...",
      gu: "Tame shu kaam karo chho? Udaharan: plumber, electrician, driver...",
      kn: "Neenu yenu kelasa maaduttiya? Udaaharana: plumber, electrician...",
      ml: "Nimmal yenna panikkaranu? Udaaharan: plumber, electrician...",
      pa: "Tusi ki kaam karde ho? Misal: plumber, electrician, driver...",
      ur: "Aap kya kaam karte hain? Jaise plumber, electrician, driver...",
      ne: "Tapai ke kaam garnuhunchha? Udaharan: plumber, electrician...",
    },

    regLocation: {
      hi: "Aap kis sheher ya ilaake mein rehte hain?",
      en: "Which city or area do you live in?",
      bn: "Apni kon shahore ba elaakay thaken?",
      ta: "Neenga entha nagaram illaiyal idam irukkireenga?",
      te: "Meeru em nagaram lonu em praadam lo untaaru?",
      mr: "Tumhi konathya shaharat kiva bhagaat raahtaa?",
      gu: "Tame kya shaher ya vishtar ma rahoch?",
      kn: "Neenu yelli iruttiya?",
      ml: "Nimmal enghe thamasikkunnath?",
      pa: "Tusi kis shahar ya ilaake vich rehunde ho?",
      ur: "Aap kis sheher ya ilaake mein rehte hain?",
      ne: "Tapai kun shahar ya thaauma basnu hunchha?",
    },

    regPhone: {
      hi: "Apna 10 ankon ka mobile number dheere dheere bolein.",
      en: "Please say your 10-digit mobile number slowly.",
      bn: "Apnar 10-digit mobile number aaste bolun.",
      ta: "Unkal 10 ellakkam phone number mella sollunga.",
      te: "Meeru 10 anela phone number meesta meesta cheppandi.",
      mr: "Tumcha 10 anki mobile number savakar saanga.",
      gu: "Tamaro 10 ankno mobile number dhire dhire kaho.",
      kn: "Nimma 10 anka mobile number nidhanavagi heli.",
      ml: "Nimma 10 akkam phone number mella parayo.",
      pa: "Apna 10-anka mobile number dhire dhire kaho.",
      ur: "Apna 10 ankon ka mobile number bolein.",
      ne: "Tapaiको 10 anka mobile number bistaarai bhannu.",
    },

    regPassword: {
      hi: "Ab apni pasand ka password bolein. Koi bhi shabd ya ankon ka mel jo aapko aasaani se yaad rahe.",
      en: "Now say a password — any word or number combination you can easily remember.",
      bn: "Akhon ekti password bolun — jekono word ba number jeta apni mone rakhte parben.",
      ta: "Ippo password sollunga — unga ninaivil nilaikkum oru word ba number.",
      te: "Ippudu password cheppandi — meeru tagaini gurtupettukuni unna word ya number.",
      mr: "Aata password saanga — aapala aathavata raheel ase konetihe shabd ya anka.",
      gu: "Hve password kaho — tamne yaad rahe tevu koi shabd ya ank.",
      kn: "Ipa password heli — nimmannu ninapitta iruvantha yaavude shabda ya sankhye.",
      ml: "Ippol password parayo — nimmal orkkaan kazhiyunna vaakkum ankhavum.",
      pa: "Hune password kaho — koi vi shabd ya ank jo tumhannu yaad rahe.",
      ur: "Ab password bolein — koi bhi lafz ya ank jo yaad rakhna aasaan ho.",
      ne: "Aba password bhannu — yaad rakhna sajilo shabad ya anka.",
    },

    regSubmitting: {
      hi: "Wah! Aapki profile ban rahi hai. Ek second ruk...",
      en: "Excellent! Creating your profile now...",
      bn: "Oshadharon! Apnar profile toiri hocche...",
      ta: "Miga Arumai! Unkal profile tayaar aaguthu...",
      te: "Adhbhutam! Meeru profile create avutundi...",
      mr: "Shandar! Tumchi profile tayyar hote aahe...",
      gu: "Darun! Tamari profile bani rahi chhe...",
      kn: "Adbhuta! Nimma profile create aagutide...",
      ml: "Poornam! Nimma profile create cheyyunnu...",
      pa: "Kamaal! Apna profile ban raha hai...",
      ur: "Wah! Aapki profile ban rahi hai...",
      ne: "Dherai raamro! Tapaiको profile banai rahe chha...",
    },

    /* ── Dashboard guide ── */
    dashGreet: {
      hi: "Swagat hai! Aapka dashboard taiyaar hai. Naye kaam dekhne ke liye Find Jobs dabayein. Apni availability ON rakhein taaki job requests aayein!",
      en: "Welcome back! Your dashboard is ready. Tap Find Jobs to see new work. Keep your availability ON to receive job requests!",
      bn: "Swagata! Apnar dashboard taiyaar. Notun kaj dekhte Find Jobs taan. Availability ON rakun!",
      ta: "Varaverkirom! Unkal dashboard tayaar. Puthu velai kaana Find Jobs thado. Availability ON vaiyungal!",
      te: "Swaagatam! Meeru dashboard ready. Kotta jobs choosukovadaniki Find Jobs nockkondi. Availability ON ga pettandi!",
      mr: "Swagat! Tumcha dashboard tayaar. Nawe kaam paahat Find Jobs click kara. Availability ON theva!",
      gu: "Swagat! Tama dashboard taiyaar chhe. Nava kaam jova Find Jobs tap karo. Availability ON rakho!",
      kn: "Swagata! Nimma dashboard ready. Hosa jobs noodalu Find Jobs click maadi. Availability ON ittukoli!",
      ml: "Swaagatam! Nimma dashboard ready. Puthu jobs kaanaanu Find Jobs tap cheyyuka. Availability ON aakki vaykkuka!",
      pa: "Ji ayan nu! Apna dashboard taiyaar hai. Nava kaam vekhne lyi Find Jobs dabaao. Availability ON rakho!",
      ur: "Khush aamdeed! Aapka dashboard taiyaar hai. Nayi jobs dekhne ke liye Find Jobs tap karein. Availability ON rakhein!",
      ne: "Swaagatam! Tapaiको dashboard taiyaar chha. Naya kaam herna Find Jobs click garnu. Availability ON rakhnos!",
    },

    /* ── Job notification ── */
    jobAlert: {
      hi: "Aapke liye ek nayi job request aayi hai! Dashboard check karein.",
      en: "You have a new job request! Please check your dashboard.",
      bn: "Apnar jonnyo ekta notun kaj eshechhe! Dashboard dekun.",
      ta: "Unkalukku oru puthu velai vanthu irukku! Dashboard parungu.",
      te: "Meeru kotta job request vachindi! Dashboard chuskoandi.",
      mr: "Tumhala ek nawe kaam aale! Dashboard paha.",
      gu: "Tama mate ek navu kaam aavyu! Dashboard juo.",
      kn: "Nimge hosa job request bande! Dashboard nodi.",
      ml: "Nimmalku oru puthiya job request vannu! Dashboard nokko.",
      pa: "Tuhade layi ik navi job request aayi hai! Dashboard vekhao.",
      ur: "Aapke liye ek nayi job request aayi hai! Dashboard check karein.",
      ne: "Tapaiलāi naya job request aayo chha! Dashboard check garnu.",
    },

    retry: {
      hi: "Maafi kijiye, samajh nahi aaya. Kripaya phir se bolein.",
      en: "Sorry, I did not catch that. Please say it again.",
      bn: "Kshoma korun, bujhte parchhi na. Abar bolun.",
      ta: "Mannikkanam, puriyavillai. Meendum sollunga.",
      te: "Kshaminchaandi, artham kaaledhu. Meeru meeru cheppandi.",
      mr: "Maaf kara, samajala nahi. Parat saanga.",
      gu: "Maaf karo, samajyu nahi. Phri kaho.",
      kn: "Kshamisi, arthaagalilla. Matte heli.",
      ml: "Kshaminnam, arjila. Valiyoru parayo.",
      pa: "Maafi karo, samajh nahi aaya. Phir kaho.",
      ur: "Maafi chahta hoon, samajh nahi aaya. Phir bolein.",
      ne: "Maafi maagnuhos, bujhena. Pheri bhannu.",
    },

    noSpeech: {
      hi: "Koi awaaz nahi mili. Ek baar phir koshish karein.",
      en: "No voice detected. Please try speaking again.",
      bn: "Kono awaz paaini. Abar bolun.",
      ta: "Kural kedaikkavillai. Meendum sollunga.",
      te: "Voice raaledu. Meeru meeru try cheyandi.",
      mr: "Awaz aali nahi. Parat bolun.",
      gu: "Koi awaaz sanbhaldi nahi. Phri bolao.",
      kn: "Dhwani sigalilla. Matte try madi.",
      ur: "Koi awaaz nahi mili. Dobara bolein.",
      ne: "Awaaz detekhina. Pheri prayaas garnu.",
    },

    noSupport: {
      hi: "Aapka browser voice support nahi karta. Kripaya Google Chrome use karein.",
      en: "Your browser does not support voice. Please use Google Chrome.",
    },
  };

  /* ───────────────────────────────────────────────────────────────
     3. STATE
  ─────────────────────────────────────────────────────────────── */
  let lang = 'hi';
  let recognition = null;
  let isSpeaking = false;
  let isListening = false;
  let panelOpen = false;
  let currentResolve = null;   // resolve fn for the current listen() promise
  let jobPollTimer = null;
  let lastJobCount = null;
  let hasInitialized = false;

  /* ───────────────────────────────────────────────────────────────
     4. SPEECH ENGINE
  ─────────────────────────────────────────────────────────────── */
  function say(textOrKey, overrideLang) {
    return new Promise(resolve => {
      if (!window.speechSynthesis) { resolve(); return; }
      window.speechSynthesis.cancel();

      let text = textOrKey;
      // If it's a key in D, resolve the language
      if (D[textOrKey]) {
        const src = D[textOrKey];
        const useLang = overrideLang || lang;
        text = src[useLang] || src.en || src.hi || src._always_hi || src._always || '';
      }

      if (!text) { resolve(); return; }

      uiSetBubble(text);
      uiSetWave(true);
      isSpeaking = true;

      const utt = new SpeechSynthesisUtterance(text);
      const useLang = overrideLang || lang;
      utt.lang = (LANGS[useLang] || LANGS.hi).speech;
      utt.rate  = 0.90;
      utt.pitch = 1.05;
      utt.volume = 1;

      // Try to find native voice
      const voices = window.speechSynthesis.getVoices();
      const langPrefix = utt.lang.split('-')[0];
      const match = voices.find(v => v.lang.startsWith(langPrefix) && !v.name.includes('(')) ||
                    voices.find(v => v.lang.startsWith(langPrefix));
      if (match) utt.voice = match;

      utt.onend  = () => { isSpeaking = false; uiSetWave(false); resolve(); };
      utt.onerror= () => { isSpeaking = false; uiSetWave(false); resolve(); };

      // Safari/iOS workaround — split very long sentences
      window.speechSynthesis.speak(utt);
    });
  }

  function hear(timeoutMs) {
    return new Promise(resolve => {
      if (!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
        say('noSupport').then(() => resolve({ text: '', raw: [] }));
        return;
      }

      const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
      recognition = new Rec();
      recognition.lang = (LANGS[lang] || LANGS.hi).speech;
      recognition.interimResults = true;
      recognition.maxAlternatives = 5;
      recognition.continuous = false;

      let interimEl = document.getElementById('vh-interim');
      let finalResult = '';
      let allAlts = [];
      const timeout = setTimeout(() => {
        recognition.stop();
        resolve({ text: '', raw: [] });
      }, timeoutMs || 12000);

      recognition.onstart = () => { isListening = true; uiSetMic(true); };
      recognition.onend   = () => {
        isListening = false;
        uiSetMic(false);
        clearTimeout(timeout);
        if (interimEl) interimEl.textContent = '';
        resolve({ text: finalResult.trim(), raw: allAlts });
      };
      recognition.onerror = (e) => {
        isListening = false;
        uiSetMic(false);
        clearTimeout(timeout);
        if (interimEl) interimEl.textContent = '';
        resolve({ text: '', raw: [], error: e.error });
      };
      recognition.onresult = (e) => {
        let interim = '';
        for (let i = e.resultIndex; i < e.results.length; i++) {
          if (e.results[i].isFinal) {
            finalResult = e.results[i][0].transcript;
            allAlts = Array.from(e.results[i]).map(r => r.transcript.toLowerCase().trim());
          } else {
            interim += e.results[i][0].transcript;
          }
        }
        if (interimEl) interimEl.textContent = interim || finalResult;
      };

      recognition.start();
    });
  }

  function stopListening() {
    if (recognition) { try { recognition.stop(); } catch(e){} recognition = null; }
    isListening = false;
    uiSetMic(false);
  }
  function stopSpeaking() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    isSpeaking = false;
    uiSetWave(false);
  }

  /* ───────────────────────────────────────────────────────────────
     5. PHONE EXTRACTION
  ─────────────────────────────────────────────────────────────── */
  const DIGIT_WORDS = {
    // English
    zero:0, one:1, two:2, three:3, four:4, five:5, six:6, seven:7, eight:8, nine:9, oh:0,
    // Hindi
    sifar:0, ek:1, do:2, teen:3, char:4, chaar:4, panch:5, paanch:5, chhe:6,
    chhah:6, saat:7, aath:8, nau:9,
    // Tamil
    sunnam:0, onnu:1, irantu:2, moonru:3, naanku:4, ainthu:5, aaru:6,
    ezhu:7, ettu:8, onpathu:9,
    // Telugu
    sunna:0, okati:1, rendu:2, muudu:3, naalugu:4, aidu:5, aaru:6,
    edu:7, enimidi:8, tommidi:9,
    // Kannada
    sonne:0, ondu:1, eradu:2, mooru:3, naalku:4, aidu:5, aaru:6,
    yelu:7, entu:8, ombattu:9,
    // Bengali
    shunno:0, ek_bn:1, dui:2, tin:3, char_bn:4, panch_bn:5, chhoy:6,
    saat_bn:7, aat:8, noy:9,
  };

  function extractPhone(transcript) {
    if (!transcript) return null;
    // 1) Raw digits in string
    const raw = transcript.replace(/\D/g, '');
    if (raw.length >= 10) {
      const last10 = raw.slice(-10);
      if (/^[6-9]\d{9}$/.test(last10)) return last10;
      if (/^\d{10}$/.test(last10)) return last10; // still return even if doesn't start 6-9
    }
    // 2) Word-to-digit conversion
    const words = transcript.toLowerCase().split(/[\s,.-]+/);
    let digits = '';
    for (const w of words) {
      const d = DIGIT_WORDS[w];
      if (d !== undefined) digits += d;
      else if (/^\d$/.test(w)) digits += w;
    }
    if (digits.length >= 10) {
      const last10 = digits.slice(-10);
      if (/^[6-9]\d{9}$/.test(last10)) return last10;
      if (/^\d{10}$/.test(last10)) return last10;
    }
    return null;
  }

  function normalizePassword(transcript) {
    if (!transcript) return '';
    // convert spoken digits to numeric form
    return transcript.toLowerCase().trim().split(/[\s,]+/).map(w => {
      const d = DIGIT_WORDS[w];
      return d !== undefined ? String(d) : w;
    }).join('');
  }

  /* ───────────────────────────────────────────────────────────────
     6. LANGUAGE DETECTION FROM SPEECH
  ─────────────────────────────────────────────────────────────── */
  const LANG_KEYWORDS = {
    hi: ['hindi', 'हिंदी', 'hind', 'hindhi'],
    en: ['english', 'angrezi', 'inglis', 'english'],
    bn: ['bangla', 'bengali', 'bongali', 'বাংলা'],
    ta: ['tamil', 'தமிழ்', 'tamizh'],
    te: ['telugu', 'తెలుగు', 'telgu'],
    mr: ['marathi', 'मराठी', 'maraati'],
    gu: ['gujarati', 'ગુજરાતી', 'gujrati'],
    kn: ['kannada', 'ಕನ್ನಡ', 'kannad'],
    ml: ['malayalam', 'മലയാളം', 'mallu'],
    pa: ['punjabi', 'ਪੰਜਾਬੀ', 'panjabi'],
    or: ['odia', 'oriya', 'ଓଡ଼ିଆ'],
    as: ['assamese', 'অসমীয়া', 'axomiya'],
    ur: ['urdu', 'اردو'],
    ne: ['nepali', 'नेपाली'],
    kok:['konkani', 'कोंकणी'],
  };

  function detectLangFromSpeech(transcript) {
    const t = (transcript || '').toLowerCase();
    for (const [code, keywords] of Object.entries(LANG_KEYWORDS)) {
      if (keywords.some(kw => t.includes(kw))) return code;
    }
    return null;
  }

  function getLang(textOrKey) {
    const src = D[textOrKey];
    if (!src) return textOrKey; // raw string
    return src[lang] || src.en || src.hi || src._always_hi || src._always || '';
  }

  /* ───────────────────────────────────────────────────────────────
     7. UI — BUILD PANEL
  ─────────────────────────────────────────────────────────────── */
  function buildUI() {
    // Kill any existing VoiceHire bots
    ['vgb-root', 'vh-gateway-bot'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.remove();
    });

    const langButtons = Object.entries(LANGS).map(([code, info]) =>
      `<button class="vhai-lb" data-lang="${code}" id="vhai-lb-${code}">${info.flag} ${info.native}</button>`
    ).join('');

    const wrap = document.createElement('div');
    wrap.id = 'vhai-root';
    wrap.innerHTML = `
      <!-- Floating Action Button -->
      <button class="vhai-fab" id="vhai-fab" title="VoiceHire AI Assistant" aria-label="Open AI Assistant">
        <i class="fa-solid fa-robot"></i>
        <span class="vhai-ping"></span>
      </button>

      <!-- Assistant Panel -->
      <div class="vhai-panel" id="vhai-panel" aria-hidden="true" role="dialog" aria-label="VoiceHire AI Assistant">
        <!-- Header -->
        <div class="vhai-header">
          <div class="vhai-hdr-left">
            <div class="vhai-avatar" id="vhai-avatar">
              <i class="fa-solid fa-robot"></i>
              <div class="vhai-avatar-ring" id="vhai-avatar-ring"></div>
            </div>
            <div>
              <div class="vhai-title">VoiceHire AI</div>
              <div class="vhai-status" id="vhai-status">
                <span class="vhai-dot" id="vhai-dot"></span>
                <span id="vhai-status-text">Ready</span>
              </div>
            </div>
          </div>
          <div class="vhai-hdr-right">
            <button class="vhai-hbtn" id="vhai-lang-toggle" title="Change Language" aria-label="Change Language">
              <i class="fa-solid fa-language"></i>
            </button>
            <button class="vhai-hbtn" id="vhai-close" title="Close" aria-label="Close assistant">
              <i class="fa-solid fa-xmark"></i>
            </button>
          </div>
        </div>

        <!-- Language Picker (hidden by default) -->
        <div class="vhai-langpick" id="vhai-langpick" style="display:none;">
          <div class="vhai-lp-title">🌐 Apni bhasha chunein / Choose Language</div>
          <div class="vhai-lp-grid">${langButtons}</div>
        </div>

        <!-- Bubble + Wave -->
        <div class="vhai-body">
          <div class="vhai-bubble" id="vhai-bubble">
            🎙️ <strong>Namaste!</strong> Main VoiceHire ka AI Assistant hoon. Seedha baat karte hain...
          </div>
          <div class="vhai-wave" id="vhai-wave">
            <span></span><span></span><span></span><span></span><span></span><span></span><span></span>
          </div>
          <!-- Live transcript preview -->
          <div class="vhai-interim" id="vh-interim"></div>

          <!-- Choice Buttons area -->
          <div class="vhai-choices" id="vhai-choices"></div>

          <!-- Mic row -->
          <div class="vhai-mic-row" id="vhai-mic-row">
            <button class="vhai-mic-btn" id="vhai-mic-btn" title="Tap to speak" aria-label="Tap to speak">
              <i class="fa-solid fa-microphone"></i>
            </button>
            <span class="vhai-mic-label" id="vhai-mic-label">Tap to speak</span>
          </div>
        </div>

        <!-- Progress bar -->
        <div class="vhai-progress" id="vhai-progress" style="display:none;">
          <div class="vhai-progress-bar" id="vhai-progress-bar"></div>
        </div>
      </div>
    `;

    injectCSS();
    document.body.appendChild(wrap);

    // Wire events
    document.getElementById('vhai-fab').addEventListener('click', openPanel);
    document.getElementById('vhai-close').addEventListener('click', closePanel);
    document.getElementById('vhai-lang-toggle').addEventListener('click', toggleLangPicker);
    document.getElementById('vhai-mic-btn').addEventListener('click', onManualMic);

    // Language button clicks
    document.querySelectorAll('.vhai-lb').forEach(btn => {
      btn.addEventListener('click', () => selectLanguage(btn.dataset.lang, true));
    });
  }

  function injectCSS() {
    if (document.getElementById('vhai-css')) return;
    const s = document.createElement('style');
    s.id = 'vhai-css';
    s.textContent = `
      #vhai-root {
        position: fixed; bottom: 24px; right: 24px; z-index: 99999;
        font-family: 'Inter', -apple-system, sans-serif;
      }

      /* ── FAB ── */
      .vhai-fab {
        width: 62px; height: 62px; border-radius: 50%;
        background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%);
        border: none; cursor: pointer; color: white; font-size: 1.4rem;
        display: flex; align-items: center; justify-content: center;
        box-shadow: 0 8px 32px rgba(79,70,229,.45);
        transition: transform .2s ease, box-shadow .2s ease;
        position: relative;
      }
      .vhai-fab:hover { transform: scale(1.08); box-shadow: 0 12px 40px rgba(79,70,229,.6); }
      .vhai-ping {
        position: absolute; top: 1px; right: 1px;
        width: 15px; height: 15px; border-radius: 50%;
        background: #10B981; border: 2.5px solid white;
        animation: vh-ping 2s ease infinite;
      }
      @keyframes vh-ping { 0%,100%{transform:scale(1);opacity:1;} 50%{transform:scale(1.5);opacity:.5;} }

      /* ── Panel ── */
      .vhai-panel {
        position: absolute; bottom: 76px; right: 0; width: 360px;
        background: white; border-radius: 22px;
        box-shadow: 0 28px 80px rgba(0,0,0,.22);
        overflow: hidden; transform-origin: bottom right;
        transition: transform .28s cubic-bezier(.34,1.56,.64,1), opacity .2s;
        transform: scale(.82); opacity: 0; pointer-events: none;
      }
      .vhai-panel.open { transform: scale(1); opacity: 1; pointer-events: all; }

      /* ── Header ── */
      .vhai-header {
        display: flex; align-items: center; justify-content: space-between;
        padding: 14px 16px;
        background: linear-gradient(135deg, #1E1B4B 0%, #4F46E5 60%, #7C3AED 100%);
      }
      .vhai-hdr-left { display: flex; align-items: center; gap: 12px; }
      .vhai-avatar {
        width: 44px; height: 44px; border-radius: 50%;
        background: rgba(255,255,255,.18); border: 2px solid rgba(255,255,255,.35);
        display: flex; align-items: center; justify-content: center;
        font-size: 1.2rem; color: white; position: relative;
      }
      .vhai-avatar-ring {
        position: absolute; inset: -6px; border-radius: 50%;
        border: 3px solid transparent; pointer-events: none;
        transition: border-color .3s;
      }
      .vhai-avatar-ring.speaking { border-color: #FDE68A; animation: vh-spin 1s linear infinite; }
      .vhai-avatar-ring.listening { border-color: #34D399; animation: vh-spin .7s linear infinite; }
      @keyframes vh-spin { to { transform: rotate(360deg); } }
      .vhai-title { color: white; font-size: .9rem; font-weight: 700; }
      .vhai-status { display: flex; align-items: center; gap: 5px; margin-top: 2px; }
      .vhai-dot { width: 7px; height: 7px; border-radius: 50%; background: #10B981; }
      #vhai-status-text { font-size: .7rem; color: rgba(255,255,255,.8); }
      .vhai-hdr-right { display: flex; gap: 5px; }
      .vhai-hbtn {
        width: 32px; height: 32px; border-radius: 8px;
        background: rgba(255,255,255,.15); border: none; color: white;
        cursor: pointer; font-size: .85rem;
        display: flex; align-items: center; justify-content: center;
        transition: background .15s;
      }
      .vhai-hbtn:hover { background: rgba(255,255,255,.3); }

      /* ── Language Picker ── */
      .vhai-langpick {
        padding: 12px 14px; background: #F8FAFC;
        border-bottom: 1px solid #E2E8F0; max-height: 200px; overflow-y: auto;
      }
      .vhai-lp-title { font-size: .72rem; font-weight: 700; color: #64748B; margin-bottom: 8px; text-transform: uppercase; letter-spacing: .05em; }
      .vhai-lp-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; }
      .vhai-lb {
        padding: 7px 6px; border-radius: 8px;
        border: 1.5px solid #E2E8F0; background: white;
        font-size: .75rem; cursor: pointer; text-align: center;
        transition: all .15s; font-family: inherit;
      }
      .vhai-lb:hover, .vhai-lb.selected {
        border-color: #4F46E5; background: #EEF2FF; color: #4F46E5; font-weight: 600;
      }

      /* ── Body ── */
      .vhai-body { padding: 14px 14px 10px; display: flex; flex-direction: column; gap: 10px; }

      /* ── Bubble ── */
      .vhai-bubble {
        background: linear-gradient(135deg, #EEF2FF, #F5F3FF);
        border: 1px solid #C7D2FE; border-radius: 14px 14px 14px 4px;
        padding: 12px 14px; font-size: .875rem; color: #1E1B4B;
        line-height: 1.6; min-height: 56px;
        animation: vh-fade .3s ease;
      }
      @keyframes vh-fade { from{opacity:0;transform:translateY(4px);} to{opacity:1;transform:translateY(0);} }

      /* ── Wave (speaking indicator) ── */
      .vhai-wave {
        display: flex; align-items: center; gap: 3px;
        padding-left: 2px; height: 22px;
        opacity: 0; transition: opacity .25s;
      }
      .vhai-wave.on { opacity: 1; }
      .vhai-wave span {
        display: inline-block; width: 4px; border-radius: 3px;
        background: linear-gradient(180deg, #4F46E5, #7C3AED);
        animation: vh-bar 1s ease-in-out infinite;
      }
      .vhai-wave span:nth-child(1){animation-delay:.00s;}
      .vhai-wave span:nth-child(2){animation-delay:.12s;}
      .vhai-wave span:nth-child(3){animation-delay:.24s;}
      .vhai-wave span:nth-child(4){animation-delay:.36s;}
      .vhai-wave span:nth-child(5){animation-delay:.24s;}
      .vhai-wave span:nth-child(6){animation-delay:.12s;}
      .vhai-wave span:nth-child(7){animation-delay:.00s;}
      @keyframes vh-bar {
        0%,100%{height:4px;} 50%{height:22px;}
      }

      /* ── Interim transcript ── */
      .vhai-interim {
        font-size: .78rem; color: #6B7280; font-style: italic;
        min-height: 18px; text-align: center;
        background: #F9FAFB; border-radius: 6px; padding: 4px 8px;
        display: none;
      }
      .vhai-interim:not(:empty) { display: block; }

      /* ── Choices ── */
      .vhai-choices { display: flex; flex-direction: column; gap: 6px; }
      .vhai-choice {
        display: flex; align-items: center; gap: 10px;
        padding: 11px 14px; border: 1.5px solid #E5E7EB;
        background: white; border-radius: 12px; cursor: pointer;
        transition: all .15s ease; font-family: inherit; text-align: left;
        width: 100%;
      }
      .vhai-choice:hover { border-color: #4F46E5; background: #EEF2FF; transform: translateX(2px); }
      .vhai-choice-icon { font-size: 1.5rem; flex-shrink: 0; }
      .vhai-choice strong { color: #1E1B4B; font-size: .875rem; display: block; }
      .vhai-choice span { color: #6B7280; font-size: .75rem; }

      /* ── Mic Row ── */
      .vhai-mic-row {
        display: flex; align-items: center; gap: 12px;
        background: #F9FAFB; border-radius: 12px; padding: 10px 14px;
      }
      .vhai-mic-btn {
        width: 44px; height: 44px; border-radius: 50%; flex-shrink: 0;
        background: linear-gradient(135deg, #4F46E5, #7C3AED);
        border: none; color: white; font-size: 1rem;
        cursor: pointer; display: flex; align-items: center; justify-content: center;
        transition: transform .15s, box-shadow .15s;
      }
      .vhai-mic-btn:hover { transform: scale(1.08); }
      .vhai-mic-btn.active {
        background: linear-gradient(135deg, #DC2626, #B91C1C);
        animation: vh-mic-pulse 1.2s ease infinite;
      }
      @keyframes vh-mic-pulse {
        0%,100%{box-shadow:0 0 0 0 rgba(220,38,38,.5);}
        50%{box-shadow:0 0 0 12px rgba(220,38,38,0);}
      }
      .vhai-mic-label { font-size: .82rem; color: #6B7280; }

      /* ── Progress ── */
      .vhai-progress { height: 3px; background: #E5E7EB; }
      .vhai-progress-bar { height: 100%; background: linear-gradient(90deg, #4F46E5, #7C3AED); transition: width .4s ease; }

      @media (max-width: 420px) {
        .vhai-panel { width: calc(100vw - 32px); right: -8px; }
        .vhai-lp-grid { grid-template-columns: repeat(2,1fr); }
      }
    `;
    document.head.appendChild(s);
  }

  /* ── UI helpers ── */
  function openPanel() {
    const p = document.getElementById('vhai-panel');
    if (!p) return;
    p.classList.add('open');
    p.setAttribute('aria-hidden', 'false');
    panelOpen = true;
  }
  function closePanel() {
    const p = document.getElementById('vhai-panel');
    if (!p) return;
    p.classList.remove('open');
    p.setAttribute('aria-hidden', 'true');
    panelOpen = false;
    stopSpeaking(); stopListening();
  }
  function toggleLangPicker() {
    const lp = document.getElementById('vhai-langpick');
    if (!lp) return;
    lp.style.display = lp.style.display === 'none' ? '' : 'none';
  }
  function uiSetBubble(html) {
    const b = document.getElementById('vhai-bubble');
    if (b) { b.innerHTML = html; b.style.animation = 'none'; requestAnimationFrame(() => { b.style.animation = ''; }); }
  }
  function uiSetStatus(text, type) {
    const t = document.getElementById('vhai-status-text');
    const d = document.getElementById('vhai-dot');
    const r = document.getElementById('vhai-avatar-ring');
    if (t) t.textContent = text;
    const colors = { ready:'#10B981', speaking:'#F59E0B', listening:'#3B82F6', error:'#EF4444' };
    if (d) d.style.background = colors[type] || colors.ready;
    if (r) { r.className = 'vhai-avatar-ring'; if (type !== 'ready') r.classList.add(type); }
  }
  function uiSetWave(on) {
    const w = document.getElementById('vhai-wave');
    if (w) w.classList.toggle('on', on);
    uiSetStatus(on ? 'Speaking...' : 'Ready', on ? 'speaking' : 'ready');
  }
  function uiSetMic(on) {
    const btn = document.getElementById('vhai-mic-btn');
    const lbl = document.getElementById('vhai-mic-label');
    if (btn) btn.classList.toggle('active', on);
    if (lbl) lbl.textContent = on ? 'Listening...' : 'Tap to speak';
    if (on) {
      uiSetStatus('Listening...', 'listening');
      const w = document.getElementById('vhai-wave'); if (w) w.classList.remove('on');
    }
    const it = document.getElementById('vh-interim');
    if (it && !on) it.textContent = '';
  }
  function uiShowChoices(items) {
    const c = document.getElementById('vhai-choices');
    if (!c) return;
    c.innerHTML = '';
    (items || []).forEach(item => {
      const btn = document.createElement('button');
      btn.className = 'vhai-choice';
      btn.innerHTML = `<span class="vhai-choice-icon">${item.icon}</span><div><strong>${item.label}</strong><span>${item.sub || ''}</span></div>`;
      btn.addEventListener('click', item.action);
      c.appendChild(btn);
    });
  }
  function uiClearChoices() { uiShowChoices([]); }
  function uiSetProgress(pct) {
    const bar = document.getElementById('vhai-progress');
    const fill = document.getElementById('vhai-progress-bar');
    if (!bar || !fill) return;
    if (pct < 0) { bar.style.display = 'none'; return; }
    bar.style.display = '';
    fill.style.width = pct + '%';
  }
  function selectLanguage(code, fromButton) {
    if (!LANGS[code]) code = 'hi';
    lang = code;
    // Highlight selected button
    document.querySelectorAll('.vhai-lb').forEach(b => b.classList.toggle('selected', b.dataset.lang === code));
    // Update session via server
    fetch('/set_lang/' + code).catch(() => {});
    // Update VH global
    if (window.VH) window.VH.lang = code;
    if (fromButton) {
      document.getElementById('vhai-langpick').style.display = 'none';
      // If flow hasn't started, re-trigger after language confirm
      stopSpeaking();
      say('langConfirm').then(() => askNewOrLogin());
    }
  }

  /* Manual mic — let user re-speak the current step */
  let manualMicCallback = null;
  function onManualMic() {
    if (isListening || isSpeaking) return;
    if (manualMicCallback) manualMicCallback();
    else uiSetMic(true);
  }

  /* ───────────────────────────────────────────────────────────────
     8. FLOWS
  ─────────────────────────────────────────────────────────────── */

  /* ── GATEWAY FLOW ── */
  async function runGatewayFlow() {
    // Always greet in Hindi
    await say(D.boot._always_hi, 'hi');
    // Show lang picker and listen
    document.getElementById('vhai-langpick').style.display = '';
    uiSetStatus('Choose language / Bhasha chunein', 'listening');

    // Listen for language in Hindi (so user can name their language)
    recognition && recognition.stop();
    const { text } = await hear(10000);
    document.getElementById('vhai-langpick').style.display = 'none';

    const detected = detectLangFromSpeech(text);
    if (detected && LANGS[detected]) {
      selectLanguage(detected);
      await say('langConfirm');
    } else {
      // Default to Hindi
      selectLanguage('hi');
      await say('langConfirm');
    }
    await askNewOrLogin();
  }

  async function askNewOrLogin() {
    uiClearChoices();
    await say('roleAsk');
    uiShowChoices([
      {
        icon: '🔑', label: getLang('loginLabel') || 'Login',
        sub: lang === 'hi' ? 'Pehle se account hai' : 'I already have an account',
        action: () => { uiClearChoices(); stopListening(); runLoginFlow(); }
      },
      {
        icon: '✨', label: lang === 'hi' ? 'Nayi Profile' : 'New Profile',
        sub: lang === 'hi' ? 'Pehli baar hoon' : 'First time here',
        action: () => { uiClearChoices(); stopListening(); runRegisterFlow(); }
      }
    ]);
    // Also listen for voice
    manualMicCallback = () => hear(8000).then(({text}) => {
      if (!text) return;
      const t = text.toLowerCase();
      const isLogin = /(login|log in|pehle|account|mera|already|maujood|existing)/i.test(t);
      uiClearChoices(); stopListening();
      if (isLogin) runLoginFlow(); else runRegisterFlow();
    });
    const { text } = await hear(8000);
    if (!text) return; // user will click button
    const t = text.toLowerCase();
    const isLogin = /(login|log in|pehle|account|mera|already|maujood|existing)/i.test(t);
    uiClearChoices();
    if (isLogin) await runLoginFlow(); else await runRegisterFlow();
  }

  /* ── LOGIN FLOW ── */
  async function runLoginFlow() {
    uiSetProgress(10);
    await say('workerOrUser');
    const role = await collectRole();
    if (!role) return;
    uiSetProgress(40);

    const phone = await collectPhone('loginPhone');
    if (!phone) return;
    uiSetProgress(70);

    const password = await collectPassword('loginPassword');
    if (!password) return;
    uiSetProgress(90);

    await say('loginSubmitting');
    uiSetProgress(100);

    const result = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone, password, role })
    }).then(r => r.json()).catch(() => ({ error: 'Network error' }));

    if (result.redirect) {
      window.location.href = result.redirect;
    } else {
      const errMsg = (result.error || '') + '. ' + getLang('retry');
      await say(errMsg.trim());
      uiSetProgress(-1);
      setTimeout(() => runLoginFlow(), 500);
    }
  }

  /* ── REGISTER FLOW ── */
  async function runRegisterFlow() {
    uiSetProgress(5);
    await say('workerOrUser');
    const role = await collectRole();
    if (!role) return;
    uiSetProgress(15);

    const name = await collectText('regName', 3, 5);
    if (!name) return;
    uiSetProgress(30);

    let work = '';
    if (role === 'worker') {
      work = await collectText('regWork', 2, 5);
      if (!work) return;
    }
    uiSetProgress(50);

    const location = await collectText('regLocation', 2, 5);
    if (!location) return;
    uiSetProgress(65);

    const phone = await collectPhone('regPhone');
    if (!phone) return;
    uiSetProgress(80);

    const password = await collectPassword('regPassword');
    if (!password) return;
    uiSetProgress(95);

    await say('regSubmitting');

    const fd = new FormData();
    fd.append('name', toTitleCase(name));
    if (role === 'worker') fd.append('work', toTitleCase(work));
    fd.append('location', toTitleCase(location));
    fd.append('phone', phone);
    fd.append('password', password);

    const endpoint = role === 'worker' ? '/api/auth/signup/worker' : '/api/auth/signup/user';
    const result = await fetch(endpoint, { method: 'POST', body: fd })
      .then(r => r.json()).catch(() => ({ error: 'Network error' }));

    if (result.redirect) {
      uiSetProgress(100);
      window.location.href = result.redirect;
    } else {
      const errMsg = (result.error || '') + '. ' + getLang('retry');
      await say(errMsg.trim());
      uiSetProgress(-1);
      setTimeout(() => runRegisterFlow(), 500);
    }
  }

  /* ── SIGNUP PAGE FLOW (pre-filled page) ── */
  async function runSignupPageFlow(isWorker) {
    const steps = isWorker
      ? ['regName','regWork','regLocation','regPhone','regPassword']
      : ['regName','regPhone','regPassword'];
    const fields = isWorker
      ? [['name','w-name'],['work','w-work'],['location','w-location'],['phone','w-phone','us-phone'],['password','w-password','us-password']]
      : [['name','us-name'],['phone','us-phone'],['password','us-password']];

    uiSetProgress(0);
    for (let i = 0; i < steps.length; i++) {
      uiSetProgress(Math.round((i / steps.length) * 90));
      const key = steps[i];
      let value = '';
      if (key === 'regPhone' || key.includes('Phone')) {
        value = await collectPhone(key);
        if (!value) continue;
      } else if (key === 'regPassword' || key.includes('Password')) {
        value = await collectPassword(key);
        if (!value) continue;
      } else {
        value = await collectText(key, 2, 5);
        if (!value) continue;
      }
      // Fill form field
      for (const fid of fields[i]) {
        const el = document.getElementById(fid);
        if (el) {
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.style.borderColor = '#4F46E5';
          setTimeout(() => { el.style.borderColor = ''; }, 2000);
          break;
        }
      }
    }
    uiSetProgress(100);
    await say(getLang('regSubmitting') || 'Done! Please click the button to submit.');
  }

  /* ── LOGIN PAGE FLOW ── */
  async function runLoginPageFlow() {
    uiSetProgress(0);
    await say('workerOrUser');
    const role = await collectRole();
    // Click the role card in the existing UI
    if (role) {
      const card = document.getElementById('card-' + role);
      if (card) card.click();
      const hiddenRole = document.getElementById('login-role');
      if (hiddenRole) hiddenRole.value = role;
    }
    uiSetProgress(40);

    const phone = await collectPhone('loginPhone');
    if (phone) {
      ['phone','us-phone','w-phone'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.value = phone; el.dispatchEvent(new Event('input',{bubbles:true})); }
      });
    }
    uiSetProgress(70);

    const password = await collectPassword('loginPassword');
    if (password) {
      ['password','us-password','w-password'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.value = password; el.dispatchEvent(new Event('input',{bubbles:true})); }
      });
    }
    uiSetProgress(90);
    await say('loginSubmitting');
    uiSetProgress(100);

    // Submit form if available
    const form = document.querySelector('form[id*="login"], form.login-form, form');
    if (form) setTimeout(() => form.requestSubmit(), 600);
  }

  /* ── DASHBOARD FLOW ── */
  async function runDashboardFlow() {
    if (localStorage.getItem('vhai_dash_shown')) return;
    localStorage.setItem('vhai_dash_shown', '1');
    await say('dashGreet');
    startJobPoll();
  }

  /* ───────────────────────────────────────────────────────────────
     9. COLLECTION HELPERS (say + hear with retry)
  ─────────────────────────────────────────────────────────────── */
  async function collectRole() {
    for (let attempt = 0; attempt < 3; attempt++) {
      uiShowChoices([
        { icon:'🔧', label: lang==='hi'?'Mazdoor / Worker':'Worker',
          sub: lang==='hi'?'Kaam dhundh raha hoon':'Looking for work',
          action: () => { uiClearChoices(); stopListening(); window.__vhai_role='worker'; }},
        { icon:'🏢', label: lang==='hi'?'Maalik / Employer':'Employer',
          sub: lang==='hi'?'Kaam dena chahta hoon':'Hiring workers',
          action: () => { uiClearChoices(); stopListening(); window.__vhai_role='user'; }},
      ]);
      window.__vhai_role = null;
      const { text } = await hear(10000);
      uiClearChoices();
      if (window.__vhai_role) return window.__vhai_role; // button was clicked
      if (!text) { if (attempt < 2) await say('noSpeech'); continue; }
      const t = text.toLowerCase();
      if (/(worker|mazdoor|kaam|kam|shramik|labour|laborer|majdoor|sramik|thozhilali|karmikudu|karmachiari)/i.test(t)) return 'worker';
      if (/(employer|maalik|malik|hire|owner|setha|saahab|udyogapathi|bawas|bos)/i.test(t)) return 'user';
      if (attempt < 2) await say('retry');
    }
    return 'worker'; // default
  }

  async function collectPhone(promptKey) {
    for (let attempt = 0; attempt < 4; attempt++) {
      if (attempt > 0) await say('retry');
      await say(promptKey);
      uiSetMic(true);
      const { text } = await hear(15000);
      uiSetMic(false);
      if (!text) { await say('noSpeech'); continue; }
      const phone = extractPhone(text);
      if (phone) {
        uiSetBubble(`📱 <strong>${phone}</strong>`);
        return phone;
      }
    }
    return null;
  }

  async function collectPassword(promptKey) {
    for (let attempt = 0; attempt < 3; attempt++) {
      if (attempt > 0) await say('retry');
      await say(promptKey);
      uiSetMic(true);
      const { text } = await hear(12000);
      uiSetMic(false);
      if (!text) { await say('noSpeech'); continue; }
      const pw = normalizePassword(text);
      if (pw && pw.length >= 4) {
        uiSetBubble('🔒 ' + '•'.repeat(Math.min(pw.length, 10)));
        return pw;
      }
    }
    return null;
  }

  async function collectText(promptKey, minLen, retries) {
    for (let attempt = 0; attempt < (retries || 3); attempt++) {
      if (attempt > 0) await say('retry');
      await say(promptKey);
      uiSetMic(true);
      const { text } = await hear(12000);
      uiSetMic(false);
      if (!text) { await say('noSpeech'); continue; }
      if (text.length >= (minLen || 2)) {
        uiSetBubble('✅ ' + toTitleCase(text));
        return text;
      }
    }
    return null;
  }

  /* ───────────────────────────────────────────────────────────────
     10. JOB NOTIFICATION POLLING
  ─────────────────────────────────────────────────────────────── */
  function startJobPoll() {
    if (jobPollTimer) return;
    checkJobs(); // immediate first check
    jobPollTimer = setInterval(checkJobs, 60000);
  }

  function checkJobs() {
    if (!window.VH || window.VH.role !== 'worker') return;
    fetch('/api/jobs').then(r => r.json()).then(jobs => {
      if (!Array.isArray(jobs)) return;
      const openCount = jobs.filter(j => j.status === 'open').length;
      if (lastJobCount !== null && openCount > lastJobCount) {
        alertNewJob();
      }
      lastJobCount = openCount;
    }).catch(() => {});
  }

  function alertNewJob() {
    const msg = getLang('jobAlert');
    if (typeof showToast === 'function') showToast(msg, 'success');
    // Speak alert if panel is closed (don't interrupt if user is interacting)
    if (!isSpeaking && !isListening) say('jobAlert');
  }

  /* ───────────────────────────────────────────────────────────────
     11. UTILITIES
  ─────────────────────────────────────────────────────────────── */
  function toTitleCase(str) {
    if (!str) return '';
    return str.replace(/\w\S*/g, t => t.charAt(0).toUpperCase() + t.slice(1).toLowerCase());
  }

  /* ───────────────────────────────────────────────────────────────
     12. INIT — decides which flow to run based on current page
  ─────────────────────────────────────────────────────────────── */
  function init() {
    if (hasInitialized) return;
    hasInitialized = true;

    // Read server-set language
    if (window.VH && window.VH.lang) lang = window.VH.lang;
    else {
      const htmlLang = document.documentElement.lang;
      if (htmlLang && LANGS[htmlLang.slice(0,2)]) lang = htmlLang.slice(0,2);
    }

    buildUI();

    const path = window.location.pathname;
    const isGateway  = path === '/' || path === '/gateway' || path === '/home' || path === '/welcome';
    const isSignup   = path.includes('/signup');
    const isLogin    = path.includes('/login');
    const isDashboard= path.includes('/dashboard');
    const isWorker   = path.includes('/signup/worker') || (window.VH && window.VH.role === 'worker');
    const isLoggedIn = window.VH && window.VH.userId;

    if (isGateway && !isLoggedIn) {
      // Auto-open + auto-start after 2s
      setTimeout(() => {
        openPanel();
        // Wait for TTS voices to be ready
        if (window.speechSynthesis.getVoices().length === 0) {
          window.speechSynthesis.addEventListener('voiceschanged', runGatewayFlow, { once: true });
        } else {
          runGatewayFlow();
        }
      }, 2000);
    } else if (isSignup && !isLoggedIn) {
      setTimeout(() => {
        openPanel();
        runSignupPageFlow(isWorker);
      }, 1500);
    } else if (isLogin && !isLoggedIn) {
      setTimeout(() => {
        openPanel();
        runLoginPageFlow();
      }, 1500);
    } else if (isDashboard && isLoggedIn) {
      setTimeout(() => {
        openPanel();
        runDashboardFlow();
        startJobPoll();
      }, 2000);
    } else if (isLoggedIn) {
      // Other authenticated pages — just run job poll, no auto-open
      startJobPoll();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
