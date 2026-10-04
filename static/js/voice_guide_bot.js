
/**
 * VoiceHire AI Guide Bot
 * Guides low-literacy workers through signup, login and dashboard usage by voice.
 * Speaks in 10 Indian languages. Auto-opens on signup/login pages.
 */
(function () {
  'use strict';

  /* ── SCRIPTS: per-page, per-language guided prompts ── */
  const SCRIPTS = {
    signup: {
      en: [
        { speak: "Welcome to VoiceHire! I am your helper. I will guide you to create your account. Let us start! What is your full name?", field: 'name', hint: 'Say your full name', icon: '👤' },
        { speak: "Great! Now, what kind of work do you do? For example, plumber, carpenter, cleaner, driver.", field: 'work', hint: 'Say your work type', icon: '🔧' },
        { speak: "Nice! In which city or area do you live?", field: 'location', hint: 'Say your city or area', icon: '📍' },
        { speak: "Please say your 10-digit mobile number slowly.", field: 'phone', hint: 'Say your phone number', icon: '📱', isPhone: true },
        { speak: "Now create a password. Say any word or numbers you can remember easily.", field: 'password', hint: 'Say a password', icon: '🔒', isPassword: true },
        { speak: "Wonderful! Your profile is ready. Now click the Create Account button to save it.", field: null, hint: null, icon: '🎉', isFinal: true }
      ],
      hi: [
        { speak: "VoiceHire mein aapka swagat hai! Main aapka sahayak hoon. Aapka poora naam kya hai?", field: 'name', hint: 'Apna naam bolein', icon: '👤' },
        { speak: "Bahut achha! Aap kya kaam karte hain? Jaise plumber, badhhai, safaiwala, driver.", field: 'work', hint: 'Apna kaam bolein', icon: '🔧' },
        { speak: "Shaandaar! Aap kis sheher ya ilaake mein rehte hain?", field: 'location', hint: 'Apna sheher bolein', icon: '📍' },
        { speak: "Kripaya apna 10 ankon ka mobile number dheere-dheere bolein.", field: 'phone', hint: 'Phone number bolein', icon: '📱', isPhone: true },
        { speak: "Ab ek password banaein. Koi bhi shabd ya number bolein jo aapko yaad rahe.", field: 'password', hint: 'Password bolein', icon: '🔒', isPassword: true },
        { speak: "Bahut badhiya! Aapki profile taiyar hai. Ab Create Account button dabayein.", field: null, hint: null, icon: '🎉', isFinal: true }
      ],
      bn: [
        { speak: "VoiceHire e aapnake swagata. Ami aapnar sahayakar. Aapnar puro naam ki?", field: 'name', hint: 'Apnar naam bolun', icon: '👤' },
        { speak: "Durdar! Apni ki kaj koren? Jemon plumber, carpenter, cleaner.", field: 'work', hint: 'Apnar kaj bolun', icon: '🔧' },
        { speak: "Apni kon shahore thaken?", field: 'location', hint: 'Apnar shahor bolun', icon: '📍' },
        { speak: "Apnar 10 sonkhyar mobile nombor bolun.", field: 'phone', hint: 'Phone nombor bolun', icon: '📱', isPhone: true },
        { speak: "Akhon ekti password toiri korun.", field: 'password', hint: 'Password bolun', icon: '🔒', isPassword: true },
        { speak: "Ashadharon! Apnar profile prostut. Akhon button chapon!", field: null, hint: null, icon: '🎉', isFinal: true }
      ],
      ta: [
        { speak: "VoiceHire l ungalai varaverkiren! Nan unkal udaviyalar. Unkal peyar enna?", field: 'name', hint: 'Unkal peyar sollunga', icon: '👤' },
        { speak: "Aruma! Neenga enna velai seikireengal?", field: 'work', hint: 'Unkal velai sollunga', icon: '🔧' },
        { speak: "Neenga entha nagaram?", field: 'location', hint: 'Unkal oor sollunga', icon: '📍' },
        { speak: "Unkal 10 ilakkam phone number sollunga.", field: 'phone', hint: 'Phone number sollunga', icon: '📱', isPhone: true },
        { speak: "Ippo oru password urvakkuunga.", field: 'password', hint: 'Password sollunga', icon: '🔒', isPassword: true },
        { speak: "Sirappana! Unkal profile tayar!", field: null, hint: null, icon: '🎉', isFinal: true }
      ],
      te: [
        { speak: "VoiceHire ki swaagatam! Nenu meeru sahayakudu. Meeru peru emiti?", field: 'name', hint: 'Meeru peru cheppandi', icon: '👤' },
        { speak: "Chala bagundi! Meeru em pani chesraaru?", field: 'work', hint: 'Meeru pani cheppandi', icon: '🔧' },
        { speak: "Meeru em nagaram lo untaaru?", field: 'location', hint: 'Meeru ooru cheppandi', icon: '📍' },
        { speak: "Meeru 10 ankela mobile number cheppandi.", field: 'phone', hint: 'Phone number cheppandi', icon: '📱', isPhone: true },
        { speak: "Password create cheyandi.", field: 'password', hint: 'Password cheppandi', icon: '🔒', isPassword: true },
        { speak: "Adbhutam! Meeru profile ready!", field: null, hint: null, icon: '🎉', isFinal: true }
      ],
      mr: [
        { speak: "VoiceHire madhe apale swagat! Mi tumcha madatnis ahe. Tumche poorne naav kay ahe?", field: 'name', hint: 'Tumche naav saanga', icon: '👤' },
        { speak: "Chhan! Tumhi konte kaam karta?", field: 'work', hint: 'Tumhe kaam saanga', icon: '🔧' },
        { speak: "Tumhi konathya shaharat raahtaa?", field: 'location', hint: 'Tumhe shahar saanga', icon: '📍' },
        { speak: "Tumcha 10 anki mobile number saanga.", field: 'phone', hint: 'Phone number saanga', icon: '📱', isPhone: true },
        { speak: "Aata ek password tayaar kara.", field: 'password', hint: 'Password saanga', icon: '🔒', isPassword: true },
        { speak: "Shaabas! Tumchi profile tayaar ahe!", field: null, hint: null, icon: '🎉', isFinal: true }
      ]
    },
    login: {
      en: [
        { speak: "Welcome back! Let me help you log in. Are you a Worker or an Employer? Say Worker or Employer.", field: 'role', hint: "Say Worker or Employer", icon: '🏷️', isRole: true },
        { speak: "Please say your 10-digit mobile number.", field: 'phone', hint: 'Say your phone number', icon: '📱', isPhone: true },
        { speak: "Now say your password.", field: 'password', hint: 'Say your password', icon: '🔒', isPassword: true },
        { speak: "All done! I will click Login for you now!", field: null, hint: null, icon: '✅', isFinal: true, autoSubmit: true }
      ],
      hi: [
        { speak: "Wapas aane par swagat hai! Mujhe bataaein, kya aap mazdoor hain ya maalik? Mazdoor ya Maalik bolein.", field: 'role', hint: "Mazdoor ya Maalik bolein", icon: '🏷️', isRole: true },
        { speak: "Apna 10 ankon ka mobile number bolein.", field: 'phone', hint: 'Phone number bolein', icon: '📱', isPhone: true },
        { speak: "Ab apna password bolein.", field: 'password', hint: 'Password bolein', icon: '🔒', isPassword: true },
        { speak: "Badhiya! Login button dabaa raha hoon!", field: null, hint: null, icon: '✅', isFinal: true, autoSubmit: true }
      ],
      bn: [
        { speak: "Phire ashar jonnyo swagata! Apni ki shromik naki niyogakarta? Worker ba Employer bolun.", field: 'role', hint: "Worker ba Employer bolun", icon: '🏷️', isRole: true },
        { speak: "Apnar 10 sonkhyar mobile nombor bolun.", field: 'phone', hint: 'Phone nombor bolun', icon: '📱', isPhone: true },
        { speak: "Akhon apnar password bolun.", field: 'password', hint: 'Password bolun', icon: '🔒', isPassword: true },
        { speak: "Durdar! Login button chepchi!", field: null, hint: null, icon: '✅', isFinal: true, autoSubmit: true }
      ],
      ta: [
        { speak: "Marupadiyum varaverkiren! Neenga worker a employer a? Worker ba Employer sollunga.", field: 'role', hint: "Worker ba Employer sollunga", icon: '🏷️', isRole: true },
        { speak: "Unkal 10 ilakkam phone number sollunga.", field: 'phone', hint: 'Phone number sollunga', icon: '📱', isPhone: true },
        { speak: "Ippo unkal password sollunga.", field: 'password', hint: 'Password sollunga', icon: '🔒', isPassword: true },
        { speak: "Aruma! Login pannukirein!", field: null, hint: null, icon: '✅', isFinal: true, autoSubmit: true }
      ]
    },
    dashboard: {
      en: [
        { speak: "Hello! I am your VoiceHire guide. Your profile shows your name, work type, and location at the top.", hint: 'Say OK or tap Next', icon: '🏠', isInfo: true },
        { speak: "To find jobs near you, click Find Jobs in the left menu.", hint: 'Say OK or tap Next', icon: '💼', isInfo: true },
        { speak: "To see your booked work, click My Work. You will see all jobs you have accepted.", hint: 'Say OK or tap Next', icon: '📋', isInfo: true },
        { speak: "To scan a QR code when you finish a job, click Scan QR and point your camera at the code.", hint: 'Say OK or tap Next', icon: '📷', isInfo: true },
        { speak: "Turn your availability ON to get job requests! You are all set. Ask me anything anytime!", hint: null, icon: '✅', isInfo: true, isFinal: true }
      ],
      hi: [
        { speak: "Namaste! Main aapka VoiceHire guide hoon. Aapki profile mein naam, kaam aur jagah dikhti hai.", hint: 'OK bolein ya aage tapein', icon: '🏠', isInfo: true },
        { speak: "Naukri dhundne ke liye bayin taraf menu mein Find Jobs par click karein.", hint: 'OK bolein ya aage tapein', icon: '💼', isInfo: true },
        { speak: "Apna book kiya hua kaam dekhne ke liye My Work par click karein.", hint: 'OK bolein ya aage tapein', icon: '📋', isInfo: true },
        { speak: "Kaam poora hone par QR code scan karne ke liye Scan QR par click karein.", hint: 'OK bolein ya aage tapein', icon: '📷', isInfo: true },
        { speak: "Availability toggle ON karein taaki naukri ke anurodh milein! Sab taiyar hai.", hint: null, icon: '✅', isInfo: true, isFinal: true }
      ],
      bn: [
        { speak: "Namaskara! Ami apnar VoiceHire guide. Apnar profile e naam, kaj o jagah dekhay.", hint: 'OK bolun ba next tapun', icon: '🏠', isInfo: true },
        { speak: "Kaj khunjte bam diker menute Find Jobs e click korun.", hint: 'OK bolun ba next tapun', icon: '💼', isInfo: true },
        { speak: "Buk kora kaj dekhte My Work e click korun.", hint: 'OK bolun ba next tapun', icon: '📋', isInfo: true },
        { speak: "Kaj shesh hole Scan QR e click kore QR code scan korun.", hint: 'OK bolun ba next tapun', icon: '📷', isInfo: true },
        { speak: "Availability ON korun jate kaj er request paan! Sob thik ache.", hint: null, icon: '✅', isInfo: true, isFinal: true }
      ]
    }
  };

  /* ── HELPERS ── */
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  function getLang() {
    const match = document.cookie.match(/googtrans=\/en\/([a-z]{2,3})/);
    if (match) return match[1];
    if (window.VH && window.VH.lang) return window.VH.lang;
    const html = document.documentElement.lang;
    if (html && html.length >= 2) return html.slice(0, 2);
    return 'en';
  }

  function getSpeechLang(lang) {
    const map = { hi:'hi-IN', bn:'bn-IN', te:'te-IN', mr:'mr-IN', ta:'ta-IN', gu:'gu-IN', kn:'kn-IN', ml:'ml-IN', pa:'pa-IN', en:'en-IN' };
    return map[lang] || 'en-US';
  }

  function getScript(type) {
    const lang = getLang();
    const all = SCRIPTS[type];
    if (!all) return null;
    return all[lang] || all['en'] || null;
  }

  function detectPage() {
    const p = window.location.pathname;
    if (p.includes('/signup')) return 'signup';
    if (p.includes('/login')) return 'login';
    if (p.includes('/dashboard')) return 'dashboard';
    return null;
  }

  function wordToDigits(text) {
    const wm = {zero:0,one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,oh:0,
      sifar:0,ek:1,do:2,teen:3,char:4,panch:5,chhe:6,saat:7,aath:8,nau:9};
    const raw = text.replace(/[^0-9]/g, '');
    if (raw.length >= 10) return raw;
    const words = text.toLowerCase().split(/\s+/);
    let digits = '';
    for (const w of words) {
      const c = w.replace(/[.,!?]/g, '');
      if (c in wm) digits += wm[c];
      else if (!isNaN(c) && c !== '') digits += c;
    }
    return digits;
  }

  function wordsToPassword(text) {
    const wm = {zero:0,one:1,two:2,three:3,four:4,five:5,six:6,seven:7,eight:8,nine:9,oh:0};
    return text.toLowerCase().trim().split(/\s+/).map(w => {
      const c = w.replace(/[.,!?]/g, '');
      return c in wm ? wm[c] : c;
    }).join('');
  }

  function fillField(name, value, step) {
    const maps = {
      name: ['name', 'w-name', 'us-name'],
      work: ['w-work', 'work_type'],
      location: ['w-location', 'location'],
      phone: ['phone', 'w-phone', 'us-phone'],
      password: ['password', 'w-password', 'us-password']
    };
    const ids = maps[name] || [name];
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) {
        let v = value;
        if (step.isPhone) v = wordToDigits(value).slice(-10);
        else if (step.isPassword) v = wordsToPassword(value);
        el.value = v;
        el.dispatchEvent(new Event('input', {bubbles:true}));
        el.style.transition = 'all .3s';
        el.style.borderColor = '#2563EB';
        el.style.boxShadow = '0 0 0 3px rgba(37,99,235,.18)';
        setTimeout(() => { el.style.borderColor = ''; el.style.boxShadow = ''; }, 2200);
        return v;
      }
    }
    return value;
  }

  function fillRole(text) {
    const lo = text.toLowerCase();
    let role = null;
    if (lo.includes('worker') || lo.includes('mazdoor') || lo.includes('labor') || lo.includes('kaam')) role = 'worker';
    else if (lo.includes('employer') || lo.includes('maalik') || lo.includes('hire') || lo.includes('owner')) role = 'user';
    if (role) {
      const card = document.getElementById('card-' + role);
      if (card) card.click();
      const hr = document.getElementById('login-role');
      if (hr) hr.value = role;
    }
    return role;
  }

  /* ── BOT CLASS ── */
  class VoiceGuideBot {
    constructor() {
      this.isOpen = false; this.isGuiding = false; this.currentStep = 0;
      this.script = null; this.pageType = null; this.recognition = null;
      this.isSpeaking = false; this.isListening = false; this.autoStarted = false;
      this._st = null;
      this.render();
      this.bindEvents();
    }

    render() {
      const el = document.createElement('div');
      el.id = 'vgb-root';
      const langs = [['en','English'],['hi','Hindi'],['bn','Bengali'],['te','Telugu'],['ta','Tamil'],['mr','Marathi'],['gu','Gujarati'],['kn','Kannada'],['ml','Malayalam'],['pa','Punjabi']];
      el.innerHTML = `
        <button id="vgb-fab" title="AI Voice Guide">
          <div class="vgb-fab-icon"><i class="fa-solid fa-robot"></i></div>
          <div class="vgb-fab-pulse"></div>
          <div class="vgb-fab-lbl">Help!</div>
        </button>
        <div id="vgb-panel" class="vgb-panel">
          <div class="vgb-hdr">
            <div class="vgb-hdr-l">
              <div class="vgb-av" id="vgb-av">
                <i class="fa-solid fa-robot"></i>
                <div class="vgb-av-ring" id="vgb-av-ring"></div>
              </div>
              <div>
                <div class="vgb-ttl">VoiceHire Guide</div>
                <div class="vgb-sts" id="vgb-sts"><span class="vgb-dot"></span>Ready to help</div>
              </div>
            </div>
            <div class="vgb-hdr-r">
              <button id="vgb-lang-btn" class="vgb-ibtn" title="Language"><i class="fa-solid fa-language"></i></button>
              <button id="vgb-close" class="vgb-ibtn" title="Close"><i class="fa-solid fa-xmark"></i></button>
            </div>
          </div>
          <div id="vgb-langpick" class="vgb-langpick" style="display:none;">
            <div class="vgb-lp-label">Choose Language / Bhasha Chunein</div>
            <div class="vgb-lp-grid">
              ${langs.map(([c,l]) => `<button class="vgb-lopt" data-lang="${c}">${l}</button>`).join('')}
            </div>
          </div>
          <div class="vgb-msgs" id="vgb-msgs"></div>
          <div class="vgb-prog" id="vgb-prog" style="display:none;"><div class="vgb-prog-bar" id="vgb-prog-bar"></div></div>
          <div class="vgb-speaking" id="vgb-speaking" style="display:none;">
            <div class="vgb-wavs">${'<div class="vgb-wv"></div>'.repeat(7)}</div>
            <span class="vgb-spk-txt" id="vgb-spk-txt">Speaking...</span>
          </div>
          <div class="vgb-lstn" id="vgb-lstn" style="display:none;">
            <div class="vgb-mic-anim"><div class="vgb-mic-ring"></div><i class="fa-solid fa-microphone"></i></div>
            <div class="vgb-lstn-hint" id="vgb-lstn-hint">Listening...</div>
            <div class="vgb-tx" id="vgb-tx"></div>
          </div>
          <div class="vgb-inp-area">
            <div class="vgb-qrow" id="vgb-qrow">
              <button class="vgb-qbtn" data-qa="guide"><i class="fa-solid fa-wand-magic-sparkles"></i> Guide Me</button>
              <button class="vgb-qbtn" data-qa="help"><i class="fa-solid fa-circle-question"></i> Help</button>
              <button class="vgb-qbtn" data-qa="repeat"><i class="fa-solid fa-rotate-left"></i> Repeat</button>
            </div>
            <div class="vgb-row2">
              <input class="vgb-txt" id="vgb-txt" type="text" placeholder="Type or speak...">
              <button class="vgb-mic-inp" id="vgb-mic-inp"><i class="fa-solid fa-microphone"></i></button>
              <button class="vgb-snd" id="vgb-snd"><i class="fa-solid fa-paper-plane"></i></button>
            </div>
          </div>
        </div>`;
      document.body.appendChild(el);
    }

    bindEvents() {
      document.getElementById('vgb-fab').addEventListener('click', () => this.toggle());
      document.getElementById('vgb-close').addEventListener('click', () => this.close());
      document.getElementById('vgb-lang-btn').addEventListener('click', () => {
        const p = document.getElementById('vgb-langpick');
        p.style.display = p.style.display === 'none' ? 'block' : 'none';
      });
      document.querySelectorAll('.vgb-lopt').forEach(b => {
        b.addEventListener('click', () => {
          this.setLang(b.dataset.lang);
          document.getElementById('vgb-langpick').style.display = 'none';
        });
      });
      document.getElementById('vgb-snd').addEventListener('click', () => {
        const v = document.getElementById('vgb-txt').value.trim();
        if (v) { this.handleInput(v); document.getElementById('vgb-txt').value = ''; }
      });
      document.getElementById('vgb-txt').addEventListener('keydown', e => {
        if (e.key === 'Enter') document.getElementById('vgb-snd').click();
      });
      document.getElementById('vgb-mic-inp').addEventListener('click', () => this.freeVoice());
      document.getElementById('vgb-qrow').addEventListener('click', e => {
        const b = e.target.closest('[data-qa]');
        if (!b) return;
        const a = b.dataset.qa;
        if (a === 'guide') this.startGuide();
        else if (a === 'help') this.showHelp();
        else if (a === 'repeat') this.repeatCurrent();
      });
      setTimeout(() => {
        if (this.autoStarted) return;
        const pg = detectPage();
        if (pg === 'signup' || pg === 'login') {
          this.open(); this.autoStarted = true;
          setTimeout(() => this.startGuide(), 900);
        } else if (pg === 'dashboard' && !localStorage.getItem('vgb_dash_shown')) {
          this.open(); this.autoStarted = true;
          localStorage.setItem('vgb_dash_shown', '1');
          setTimeout(() => this.startGuide(), 900);
        } else if (!pg) {
          this.open(); this.autoStarted = true;
          setTimeout(() => this.welcome(), 900);
        }
      }, 2300);
    }

    setLang(lang) {
      document.documentElement.lang = lang;
      if (window.VH) window.VH.lang = lang;
      this.addMsg('Language changed! Bhasha badal gayi!', '🌐');
      if (this.isGuiding) { this.script = getScript(this.pageType); this.speakStep(this.currentStep); }
    }

    toggle() { this.isOpen ? this.close() : this.open(); }
    open() {
      this.isOpen = true;
      document.getElementById('vgb-panel').classList.add('open');
      document.getElementById('vgb-fab').classList.add('active');
    }
    close() {
      this.isOpen = false;
      document.getElementById('vgb-panel').classList.remove('open');
      document.getElementById('vgb-fab').classList.remove('active');
      this.stopSpeech(); this.stopListening();
    }

    addMsg(text, icon, isUser) {
      const msgs = document.getElementById('vgb-msgs');
      const d = document.createElement('div');
      d.className = 'vgb-msg ' + (isUser ? 'vgb-user' : 'vgb-bot');
      d.innerHTML = isUser
        ? `<div class="vgb-bubble">${text}</div>`
        : `<div class="vgb-icon">${icon || '🤖'}</div><div class="vgb-bubble">${text}</div>`;
      msgs.appendChild(d);
      setTimeout(() => { msgs.scrollTop = msgs.scrollHeight; }, 50);
      return d;
    }

    setStatus(txt, type) {
      const clr = { ready:'#22c55e', speaking:'#f59e0b', listening:'#3b82f6', error:'#ef4444' };
      document.getElementById('vgb-sts').innerHTML =
        `<span class="vgb-dot" style="background:${clr[type]||clr.ready}"></span>${txt}`;
    }

    showSpeaking(label) {
      document.getElementById('vgb-speaking').style.display = 'flex';
      document.getElementById('vgb-spk-txt').textContent = label || 'Speaking...';
      document.getElementById('vgb-lstn').style.display = 'none';
      document.getElementById('vgb-av-ring').classList.add('ringing');
    }
    hideSpeaking() {
      document.getElementById('vgb-speaking').style.display = 'none';
      document.getElementById('vgb-av-ring').classList.remove('ringing');
    }
    showListening(hint) {
      document.getElementById('vgb-lstn').style.display = 'flex';
      document.getElementById('vgb-lstn-hint').textContent = hint || 'Listening...';
      document.getElementById('vgb-tx').textContent = '';
      document.getElementById('vgb-speaking').style.display = 'none';
    }
    hideListening() { document.getElementById('vgb-lstn').style.display = 'none'; }

    updateProgress() {
      if (!this.script) return;
      document.getElementById('vgb-prog').style.display = 'block';
      const pct = Math.round((this.currentStep / Math.max(1, this.script.length - 1)) * 100);
      document.getElementById('vgb-prog-bar').style.width = pct + '%';
    }

    speak(text, onEnd) {
      this.stopSpeech();
      this.isSpeaking = true;
      const lang = getLang(), sl = getSpeechLang(lang);
      this.showSpeaking('Speaking...');
      this.setStatus('Speaking...', 'speaking');

      const done = () => {
        this.isSpeaking = false; this.hideSpeaking();
        this.setStatus('Ready', 'ready'); clearTimeout(this._st);
        if (onEnd) onEnd();
      };

      const cloud = () => {
        const url = `https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=${lang}&q=${encodeURIComponent(text.slice(0,200))}`;
        const a = new Audio(url);
        a.onended = done; a.onerror = done;
        a.play().catch(done);
      };

      if (window.speechSynthesis) {
        const utt = new SpeechSynthesisUtterance(text);
        utt.lang = sl; utt.rate = 0.87; utt.pitch = 1.05;
        utt.onend = done;
        utt.onerror = () => { this.hideSpeaking(); cloud(); };
        window.speechSynthesis.speak(utt);
        this._st = setTimeout(() => { if (this.isSpeaking) { window.speechSynthesis.cancel(); done(); } }, Math.max(9000, text.length * 90));
      } else {
        cloud();
      }
    }

    stopSpeech() {
      if (window.speechSynthesis) window.speechSynthesis.cancel();
      clearTimeout(this._st); this.isSpeaking = false; this.hideSpeaking();
    }

    startListening(hint, onResult, onFail) {
      if (!SpeechRecognition) {
        this.addMsg('Voice needs Chrome browser. Please type below.', '⚠️'); return;
      }
      this.stopListening();
      const rec = new SpeechRecognition();
      rec.lang = getSpeechLang(getLang());
      rec.interimResults = true; rec.maxAlternatives = 1; rec.continuous = false;
      this.recognition = rec; this.isListening = true;
      this.showListening(hint || 'Listening...');
      this.setStatus('Listening...', 'listening');
      const txEl = document.getElementById('vgb-tx');

      rec.oninterimresult = e => { txEl.textContent = Array.from(e.results).map(r => r[0].transcript).join(''); };
      rec.onresult = e => {
        const tx = e.results[e.results.length - 1][0].transcript;
        txEl.textContent = tx;
        this.isListening = false; this.hideListening(); this.setStatus('Ready', 'ready');
        this.addMsg(tx, '🎤', true);
        if (onResult) onResult(tx);
      };
      rec.onerror = e => {
        this.isListening = false; this.hideListening(); this.setStatus('Ready', 'ready');
        if (e.error !== 'aborted' && onFail) onFail();
      };
      rec.onend = () => { this.isListening = false; this.hideListening(); this.setStatus('Ready', 'ready'); };
      rec.start();
    }

    stopListening() {
      if (this.recognition) { try { this.recognition.abort(); } catch(e){} this.recognition = null; }
      this.isListening = false; this.hideListening();
    }

    freeVoice() {
      if (this.isListening) { this.stopListening(); return; }
      const lang = getLang();
      const hints = { en:'Ask me anything...', hi:'Kuch bhi poochein...', bn:'Jekono proshno korun...' };
      this.startListening(hints[lang] || 'Ask me anything...', t => this.handleInput(t),
        () => this.addMsg("Didn't hear that. Try again or type below.", '⚠️'));
    }

    startGuide() {
      this.pageType = detectPage();
      if (!this.pageType) { this.welcome(); return; }
      this.script = getScript(this.pageType);
      if (!this.script) { this.addMsg("I am here to help! Ask me anything.", '🤖'); return; }
      this.isGuiding = true; this.currentStep = 0;
      this.updateProgress();
      this.speakStep(0);
    }

    speakStep(idx) {
      if (!this.script || idx >= this.script.length) { this.isGuiding = false; return; }
      const step = this.script[idx];
      this.currentStep = idx; this.updateProgress();
      this.addMsg(step.speak, step.icon || '🤖');
      this.speak(step.speak, () => {
        if (step.isFinal) {
          this.isGuiding = false;
          if (step.autoSubmit) {
            setTimeout(() => {
              const btn = document.getElementById('login-btn');
              if (btn) { this.addMsg('Clicking Login for you!', '✅'); btn.click(); }
            }, 1500);
          }
          return;
        }
        if (step.isInfo) { this.showNextBtn(() => this.speakStep(idx + 1)); return; }
        const lang = getLang(), hint = step.hint || 'Say your answer...';
        const retry = {en:"Sorry, I did not hear you. Please say it again.",hi:"Sunai nahi diya. Phir se bolein.",bn:"Sunini. Aabar bolun.",ta:"Ketkavillai. Meedam sollunga."};
        this.startListening(hint, tx => this.processAnswer(idx, tx, step),
          () => { this.speak(retry[lang]||retry.en, () => this.startListening(hint, t => this.processAnswer(idx, t, step))); });
      });
    }

    processAnswer(idx, tx, step) {
      const lang = getLang(); let ok = false;
      if (step.isRole) {
        const role = fillRole(tx);
        if (role) { const lbl = {en:`Got it! You are a ${role}.`,hi:`Samajh gaya! Aap ${role==='worker'?'mazdoor':'maalik'} hain.`,bn:`Bujhechhi!`}; this.addMsg(lbl[lang]||lbl.en,'✅'); ok=true; }
      } else if (step.field) {
        const filled = fillField(step.field, tx, step);
        if (filled) { const c={en:`Got it: "${filled}"`,hi:`Samajh gaya: "${filled}"`,bn:`Bujhechhi: "${filled}"`}; this.addMsg(c[lang]||c.en,'✅'); ok=true; }
      }
      if (ok) { setTimeout(() => this.speakStep(idx + 1), 1200); }
      else {
        const r={en:"Could not understand. Please try again.",hi:"Samajh nahi aaya. Phir se bolein.",bn:"Bujhte parini. Aabar bolun."};
        this.speak(r[lang]||r.en, () => this.speakStep(idx));
      }
    }

    showNextBtn(onNext) {
      const msgs = document.getElementById('vgb-msgs');
      const d = document.createElement('div');
      d.className = 'vgb-msg vgb-bot';
      d.innerHTML = `<div class="vgb-nxt-row"><button class="vgb-nxt" id="vgb-nxt"><i class="fa-solid fa-arrow-right"></i> Next</button><span class="vgb-ok-hint">or say OK</span></div>`;
      msgs.appendChild(d); msgs.scrollTop = msgs.scrollHeight;
      document.getElementById('vgb-nxt').addEventListener('click', () => { d.remove(); onNext(); });
      this.startListening('Say OK or tap Next',
        () => { try{d.remove();}catch(e){} onNext(); },
        () => { setTimeout(() => { try{d.remove();}catch(e){} onNext(); }, 5000); });
    }

    repeatCurrent() {
      if (this.isGuiding && this.script && this.currentStep < this.script.length) this.speakStep(this.currentStep);
      else this.welcome();
    }

    showHelp() {
      const lang = getLang();
      const h = {en:"I can guide you to create a profile, log in, or use your dashboard. Click Guide Me to start!",hi:"Profile banana, login ya dashboard samajhne mein madad karta hoon. Guide Me dabayein!",bn:"Profile toiri, login, ba dashboard bujhate sahayata korte pari. Guide Me click korun!"};
      const msg = h[lang]||h.en; this.addMsg(msg,'ℹ️'); this.speak(msg);
    }

    welcome() {
      const lang = getLang();
      const m = {
        en:"Welcome to VoiceHire! I am your AI voice guide. I will help you find work. Click Guide Me to get started!",
        hi:"VoiceHire mein aapka swagat hai! Main aapka AI voice guide hoon. Guide Me dabayein!",
        bn:"VoiceHire e swagata! Ami apnar AI voice guide. Guide Me click korun!",
        ta:"VoiceHire l swagata! Nan unkal AI voice guide. Guide Me click seyyunga!",
        te:"VoiceHire ki swaagatam! Nenu meeru AI voice guide.",
        mr:"VoiceHire madhe swagat! Mi tumcha AI voice guide ahe.",
        gu:"VoiceHire ma swagat! Hu tamaro AI voice guide chhu.",
        kn:"VoiceHire ge swagatha! Nanu nimma AI voice guide.",
        ml:"VoiceHire il swagatha! Njan ningalude AI voice guide.",
        pa:"VoiceHire vich suagat! Main tumhada AI voice guide haan."
      };
      const msg = m[lang]||m.en; this.addMsg(msg,'🌟'); this.speak(msg);
    }

    handleInput(text) {
      if (!text) return;
      this.addMsg(text,'🎤',true);
      const lo = text.toLowerCase(), lang = getLang();
      if (lo.includes('guide')||lo.includes('start')||lo.includes('help me')||lo.includes('madad')) { this.startGuide(); return; }
      if (lo.includes('repeat')||lo.includes('again')||lo.includes('phir')||lo.includes('dobara')) { this.repeatCurrent(); return; }
      if (lo.includes('job')||lo.includes('kaam')||lo.includes('naukri')||lo.includes('work')) {
        const r={en:"Find Jobs in the left menu of your dashboard!",hi:"Dashboard ke baye menu mein Find Jobs dekhen!",bn:"Dashboard er bam dike Find Jobs e click korun!"};
        const msg=r[lang]||r.en; this.addMsg(msg,'💼'); this.speak(msg); return;
      }
      if (lo.includes('wallet')||lo.includes('paisa')||lo.includes('money')||lo.includes('payment')) {
        const r={en:"Your earnings are in the Wallet section of your dashboard.",hi:"Aapki kamaai Dashboard ke Wallet section mein hai.",bn:"Apnar uparjan Dashboard er Wallet section e ache."};
        const msg=r[lang]||r.en; this.addMsg(msg,'💰'); this.speak(msg); return;
      }
      if (lo.includes('login')||lo.includes('sign in')) {
        const r={en:"Go to the login page, I will guide you!",hi:"Login page par jaein, main guide karoonga!",bn:"Login page e jan, ami help korbo!"};
        const msg=r[lang]||r.en; this.addMsg(msg,'🔑'); this.speak(msg); return;
      }
      if (lo.includes('signup')||lo.includes('register')||lo.includes('naya account')) {
        const r={en:"Go to Sign Up page, I will walk you through!",hi:"Sign Up page par jaein, sab kuch guide karoonga!",bn:"Sign Up page e jan, sab kichhu guide korbo!"};
        const msg=r[lang]||r.en; this.addMsg(msg,'📋'); this.speak(msg); return;
      }
      const d={en:"I am here to help! Click Guide Me and I will walk you through step by step.",hi:"Main yahan hoon! Guide Me dabayein, main har kadam par saath rahoonga.",bn:"Ami ekhane achhi! Guide Me click korun."};
      const msg=d[lang]||d.en; this.addMsg(msg,'🤖'); this.speak(msg);
    }
  }

  /* ── CSS ── */
  function injectCSS() {
    const s = document.createElement('style');
    s.textContent = `
#vgb-root{position:fixed;bottom:24px;right:24px;z-index:99999;font-family:'Inter',sans-serif;}
#vgb-fab{position:relative;width:66px;height:66px;border-radius:50%;background:linear-gradient(135deg,#2563EB,#7C3AED);color:#fff;border:none;cursor:pointer;box-shadow:0 8px 30px rgba(37,99,235,.45);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;transition:transform .2s,box-shadow .2s;overflow:visible;}
#vgb-fab:hover{transform:scale(1.08);box-shadow:0 12px 40px rgba(37,99,235,.6);}
#vgb-fab.active{background:linear-gradient(135deg,#7C3AED,#2563EB);}
.vgb-fab-icon{font-size:1.5rem;line-height:1;}
.vgb-fab-lbl{font-size:8.5px;font-weight:700;letter-spacing:.05em;color:rgba(255,255,255,.9);text-transform:uppercase;}
.vgb-fab-pulse{position:absolute;top:-3px;right:-3px;width:18px;height:18px;border-radius:50%;background:#22c55e;border:2.5px solid #fff;animation:vgb-pulse 2s infinite;}
@keyframes vgb-pulse{0%,100%{transform:scale(1);opacity:1;}50%{transform:scale(1.35);opacity:.65;}}
.vgb-panel{position:absolute;bottom:78px;right:0;width:358px;max-height:580px;background:#fff;border-radius:20px;box-shadow:0 24px 64px rgba(15,23,42,.2),0 8px 24px rgba(37,99,235,.12);display:flex;flex-direction:column;opacity:0;pointer-events:none;transform:translateY(16px) scale(.96);transform-origin:bottom right;transition:opacity .22s ease,transform .22s ease;overflow:hidden;border:1.5px solid rgba(37,99,235,.1);}
.vgb-panel.open{opacity:1;pointer-events:all;transform:translateY(0) scale(1);}
@media(max-width:480px){.vgb-panel{width:calc(100vw - 20px);right:0;bottom:82px;max-height:78vh;}#vgb-root{right:10px;bottom:14px;}}
.vgb-hdr{display:flex;align-items:center;justify-content:space-between;padding:13px 15px;background:linear-gradient(135deg,#1e3a8a,#4c1d95);color:#fff;flex-shrink:0;}
.vgb-hdr-l{display:flex;align-items:center;gap:10px;}
.vgb-av{position:relative;width:40px;height:40px;background:rgba(255,255,255,.15);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.15rem;flex-shrink:0;border:2px solid rgba(255,255,255,.28);}
.vgb-av-ring{position:absolute;inset:-5px;border-radius:50%;border:3px solid transparent;transition:.3s;}
.vgb-av-ring.ringing{border-color:#fbbf24;border-right-color:transparent;animation:vgb-spin 1.1s linear infinite;}
@keyframes vgb-spin{to{transform:rotate(360deg);}}
.vgb-ttl{font-size:.88rem;font-weight:700;color:#fff;}
.vgb-sts{font-size:.7rem;display:flex;align-items:center;gap:4px;color:rgba(255,255,255,.8);margin-top:1px;}
.vgb-dot{width:7px;height:7px;border-radius:50%;background:#22c55e;flex-shrink:0;}
.vgb-hdr-r{display:flex;gap:4px;}
.vgb-ibtn{width:30px;height:30px;border-radius:7px;background:rgba(255,255,255,.12);color:rgba(255,255,255,.9);border:none;cursor:pointer;font-size:.85rem;display:flex;align-items:center;justify-content:center;transition:background .15s;}
.vgb-ibtn:hover{background:rgba(255,255,255,.24);}
.vgb-langpick{padding:11px 14px;background:#f8fafc;border-bottom:1px solid #e2e8f0;flex-shrink:0;}
.vgb-lp-label{font-size:.7rem;font-weight:600;color:#64748b;margin-bottom:7px;text-transform:uppercase;letter-spacing:.04em;}
.vgb-lp-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;}
.vgb-lopt{padding:5px 2px;font-size:.69rem;font-weight:500;border-radius:6px;border:1.5px solid #e2e8f0;background:#fff;color:#1e293b;cursor:pointer;transition:all .15s;text-align:center;}
.vgb-lopt:hover{border-color:#2563EB;background:#eff6ff;color:#2563EB;}
.vgb-msgs{flex:1;overflow-y:auto;padding:12px 11px;display:flex;flex-direction:column;gap:9px;min-height:100px;scroll-behavior:smooth;}
.vgb-msgs::-webkit-scrollbar{width:4px;}
.vgb-msgs::-webkit-scrollbar-thumb{background:#cbd5e1;border-radius:4px;}
.vgb-msg{display:flex;gap:7px;align-items:flex-start;animation:vgb-in .28s ease;}
@keyframes vgb-in{from{opacity:0;transform:translateY(7px);}to{opacity:1;transform:translateY(0);}}
.vgb-bot{flex-direction:row;}
.vgb-user{flex-direction:row-reverse;}
.vgb-icon{font-size:1.15rem;flex-shrink:0;margin-top:2px;}
.vgb-bubble{padding:8px 12px;border-radius:13px;font-size:.8rem;line-height:1.55;max-width:80%;}
.vgb-bot .vgb-bubble{background:#f1f5f9;color:#1e293b;border-bottom-left-radius:3px;}
.vgb-user .vgb-bubble{background:linear-gradient(135deg,#2563EB,#7C3AED);color:#fff;border-bottom-right-radius:3px;}
.vgb-nxt-row{display:flex;align-items:center;gap:8px;}
.vgb-nxt{padding:6px 14px;border-radius:8px;background:linear-gradient(135deg,#2563EB,#7C3AED);color:#fff;font-size:.79rem;font-weight:600;border:none;cursor:pointer;display:flex;align-items:center;gap:5px;}
.vgb-nxt:hover{opacity:.88;}
.vgb-ok-hint{font-size:.72rem;color:#94a3b8;}
.vgb-prog{height:3px;background:#e2e8f0;flex-shrink:0;}
.vgb-prog-bar{height:100%;background:linear-gradient(90deg,#2563EB,#7C3AED);transition:width .4s ease;border-radius:3px;}
.vgb-speaking{display:flex;align-items:center;gap:9px;padding:9px 13px;background:#fef9c3;border-top:1px solid #fde68a;flex-shrink:0;}
.vgb-wavs{display:flex;align-items:center;gap:3px;}
.vgb-wv{width:4px;height:18px;background:#f59e0b;border-radius:4px;animation:vgb-wav .8s ease-in-out infinite;}
.vgb-wv:nth-child(1){animation-delay:0s;height:8px;}
.vgb-wv:nth-child(2){animation-delay:.1s;height:13px;}
.vgb-wv:nth-child(3){animation-delay:.2s;height:19px;}
.vgb-wv:nth-child(4){animation-delay:.3s;height:23px;}
.vgb-wv:nth-child(5){animation-delay:.2s;height:17px;}
.vgb-wv:nth-child(6){animation-delay:.1s;height:11px;}
.vgb-wv:nth-child(7){animation-delay:0s;height:7px;}
@keyframes vgb-wav{0%,100%{transform:scaleY(.35);}50%{transform:scaleY(1.15);}}
.vgb-spk-txt{font-size:.75rem;font-weight:600;color:#92400e;}
.vgb-lstn{display:flex;flex-direction:column;align-items:center;gap:5px;padding:11px 13px;background:linear-gradient(135deg,#eff6ff,#f0fdf4);border-top:1px solid #bfdbfe;flex-shrink:0;}
.vgb-mic-anim{position:relative;width:46px;height:46px;display:flex;align-items:center;justify-content:center;color:#2563EB;font-size:1.2rem;}
.vgb-mic-ring{position:absolute;inset:-6px;border-radius:50%;border:3px solid #2563EB;opacity:.4;animation:vgb-mring 1.2s ease-out infinite;}
@keyframes vgb-mring{0%{transform:scale(.9);opacity:.6;}100%{transform:scale(1.55);opacity:0;}}
.vgb-lstn-hint{font-size:.75rem;font-weight:600;color:#2563EB;}
.vgb-tx{font-size:.78rem;color:#1e293b;font-style:italic;text-align:center;min-height:18px;max-width:90%;word-break:break-word;}
.vgb-inp-area{padding:9px 11px;border-top:1px solid #f1f5f9;flex-shrink:0;}
.vgb-qrow{display:flex;gap:5px;margin-bottom:7px;flex-wrap:wrap;}
.vgb-qbtn{padding:5px 10px;border-radius:18px;font-size:.71rem;font-weight:600;border:1.5px solid #2563EB;color:#2563EB;background:transparent;cursor:pointer;display:flex;align-items:center;gap:4px;transition:all .15s;white-space:nowrap;}
.vgb-qbtn:hover{background:#eff6ff;}
.vgb-row2{display:flex;gap:5px;align-items:center;}
.vgb-txt{flex:1;padding:7px 11px;border-radius:9px;border:1.5px solid #e2e8f0;font-size:.79rem;background:#f8fafc;color:#1e293b;outline:none;transition:border-color .15s;}
.vgb-txt:focus{border-color:#2563EB;background:#fff;}
.vgb-mic-inp{width:34px;height:34px;border-radius:9px;background:#eff6ff;color:#2563EB;border:1.5px solid #bfdbfe;cursor:pointer;font-size:.85rem;display:flex;align-items:center;justify-content:center;transition:all .15s;}
.vgb-mic-inp:hover{background:#dbeafe;}
.vgb-snd{width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg,#2563EB,#7C3AED);color:#fff;border:none;cursor:pointer;font-size:.82rem;display:flex;align-items:center;justify-content:center;transition:opacity .15s;}
.vgb-snd:hover{opacity:.88;}
    `;
    document.head.appendChild(s);
  }

  function init() {
    injectCSS();
    window.VGBot = new VoiceGuideBot();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
