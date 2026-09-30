let selectedRole = localStorage.getItem('voicehire_role') || 'user';
let aiStep = 0;
let aiActive = false;

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const app = {
    init() {
        console.log("VoiceHire AI Core Initialized");
        this.injectTranslateWidget();
        this.bindEvents();
    },

    // Dynamically inject Google Translate widget if missing
    injectTranslateWidget() {
        if (document.getElementById('google_translate_element')) return;
        
        const div = document.createElement('div');
        div.id = 'google_translate_element';
        div.style.display = 'none';
        document.body.appendChild(div);

        const script = document.createElement('script');
        script.src = "//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit";
        document.head.appendChild(script);

        window.googleTranslateElementInit = () => {
            new google.translate.TranslateElement({
                pageLanguage: 'en',
                includedLanguages: 'hi,bn,te,mr,ta,gu,kn,ml,pa,ur,or,as',
                autoDisplay: false
            }, 'google_translate_element');
        };
    },

    bindEvents() {
        const loginForm = document.getElementById('login-form');
        if (loginForm) loginForm.addEventListener('submit', (e) => this.handleLogin(e));

        const userSignupForm = document.getElementById('user-signup-form');
        if (userSignupForm) userSignupForm.addEventListener('submit', (e) => this.handleUserSignup(e));

        const userEditForm = document.getElementById('user-edit-form');
        if (userEditForm) userEditForm.addEventListener('submit', (e) => this.handleUserEdit(e));

        const workerEditForm = document.getElementById('worker-edit-form');
        if (workerEditForm) workerEditForm.addEventListener('submit', (e) => this.handleWorkerEdit(e));

        const workerSignupForm = document.getElementById('worker-signup-form');
        if (workerSignupForm) workerSignupForm.addEventListener('submit', (e) => this.handleWorkerSignup(e));

        const jobPostForm = document.getElementById('job-post-form');
        if (jobPostForm) jobPostForm.addEventListener('submit', (e) => this.handleJobPost(e));

        // Bind all individual mic buttons
        document.querySelectorAll('button[aria-label="Voice input"]').forEach(btn => {
            const input = btn.parentElement.querySelector('input');
            if (input) {
                btn.onclick = () => this.listenForInput(input.id);
            }
        });
    },

    // Get the current language selected by the Google Translate widget
    getCurrentLang() {
        // 1. Check Google Translate cookie (highest priority for real-time changes)
        const match = document.cookie.match(/googtrans=\/en\/([a-z]{2,3})/);
        if (match) {
            console.log("Detected Lang via Cookie:", match[1]);
            return match[1];
        }

        // 2. Check global variable
        if (typeof PAGE_LANG !== 'undefined' && PAGE_LANG) {
            console.log("Detected Lang via PAGE_LANG:", PAGE_LANG);
            return PAGE_LANG;
        }

        // 3. Check HTML lang attribute
        const htmlLang = document.documentElement.lang;
        if (htmlLang && htmlLang.length >= 2) {
            const l = htmlLang.substring(0, 2);
            console.log("Detected Lang via HTML:", l);
            return l;
        }

        console.log("Fallback to default lang: en");
        return 'en';
    },

    // Map Google Translate code to BCP-47 for Web Speech API
    getSpeechLangCode(langCode) {
        const map = {
            'hi': 'hi-IN', 'bn': 'bn-IN', 'te': 'te-IN', 'mr': 'mr-IN',
            'ta': 'ta-IN', 'gu': 'gu-IN', 'kn': 'kn-IN', 'ml': 'ml-IN',
            'pa': 'pa-IN', 'ur': 'ur-IN', 'or': 'or-IN', 'as': 'as-IN', 'en': 'en-IN'
        };
        return map[langCode] || 'en-US';
    },

    setRole(role) {
        selectedRole = role;
        localStorage.setItem('voicehire_role', role);
    },

    // ---------------- AUTHENTICATION ---------------- //

    async handleLogin(e) {
        e.preventDefault();
        const phone = document.getElementById('l-phone').value;
        const password = document.getElementById('l-password').value;
        const role = document.getElementById('login-role').value;

        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone, password, role: role })
            });
            const data = await res.json();
            if (res.ok) {
                window.location.href = data.redirect;
            } else {
                alert('Login failed: ' + (data.error || 'Invalid credentials'));
            }
        } catch (err) {
            alert('Connection Error');
        }
    },

    async handleUserSignup(e) {
        e.preventDefault();
        const formElement = document.getElementById('user-signup-form');
        const formData = new FormData(formElement);

        try {
            const res = await fetch('/api/auth/signup/user', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (res.ok) {
                window.location.href = data.redirect;
            } else {
                alert('Signup failed: ' + (data.error || 'Unknown Error'));
            }
        } catch (err) {
            alert('Connection Error');
        }
    },

    async handleWorkerSignup(e) {
        e.preventDefault();
        const btn = document.getElementById('btn-submit-worker');
        const origHTML = btn.innerHTML;
        btn.innerHTML = "Processing...";
        btn.disabled = true;

        const formElement = document.getElementById('worker-signup-form');

        // Ensure we have lat/lng
        const lat = document.getElementById('w-lat').value;
        const lng = document.getElementById('w-lng').value;
        const location = document.getElementById('w-location').value;

        if (!lat || !lng) {
            const coords = await this.geocodeAddress(location);
            if (coords) {
                document.getElementById('w-lat').value = coords.lat;
                document.getElementById('w-lng').value = coords.lon;
            }
        }

        const formData = new FormData(formElement);

        try {
            const res = await fetch('/api/auth/signup/worker', {
                method: 'POST',
                body: formData
            });

            if (res.ok) {
                const data = await res.json();
                alert("Profile created successfully!");
                window.location.href = data.redirect;
            } else {
                const data = await res.json();
                alert('Signup failed: ' + (data.error || 'Unknown error'));
            }
        } catch (err) {
            alert('Connection Error. Make sure Flask server is running.');
        } finally {
            btn.innerHTML = origHTML;
            btn.disabled = false;
        }
    },

    async logout() {
        try {
            const res = await fetch('/api/auth/logout', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                window.location.href = data.redirect;
            }
        } catch (e) { }
    },

    async toggleAvailability(current) {
        const newState = !current;
        try {
            const res = await fetch('/api/worker/availability', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_available: newState })
            });
            if (res.ok) {
                location.reload();
            }
        } catch (e) {
            console.error(e);
        }
    },

    async t(text) {
        try {
            const res = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })
            });
            const data = await res.json();
            return data.translated;
        } catch (e) {
            return text;
        }
    },

    // ---------------- AI CONVERSATIONAL ASSISTANT ---------------- //

    startStepByStepAI(role = 'worker') {
        if (!SpeechRecognition) {
            alert('Your browser does not support full AI features. Please use Google Chrome or a modern browser.');
            return;
        }

        aiActive = true;
        aiStep = 0;
        this.aiRole = role;

        // Hide all parent containers of inputs
        const inputs = role === 'worker' 
            ? ['w-name', 'w-work', 'w-location', 'w-phone', 'w-password']
            : ['us-name', 'us-phone', 'us-password'];
            
        inputs.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                const parent = el.closest('.relative');
                if (parent) parent.style.display = 'none';
            }
        });

        document.getElementById('btn-start-ai').style.display = 'none';
        document.getElementById('ai-conversation-area').style.display = 'block';

        this.askNextQuestion();
    },

    askNextQuestion() {
        if (!aiActive) return;

        const qText = document.getElementById('ai-question');
        const anim = document.getElementById('ai-listening-anim');
        const tBox = document.getElementById('ai-transcript');

        anim.style.display = 'none';
        tBox.style.display = 'none';

        const maxSteps = this.aiRole === 'worker' ? 5 : 3;

        if (aiStep < maxSteps) {
            const promptStr = document.getElementById(`ai-p${aiStep}`).innerText;
            qText.innerText = promptStr;
            this.speak(promptStr, () => {
                anim.style.display = 'flex';
                this.listenForAnswer();
            });
        } else {
            const finalPrompt = document.getElementById(`ai-p${maxSteps}`).innerText;
            qText.innerText = finalPrompt;
            this.speak(finalPrompt, () => {
                const inputs = this.aiRole === 'worker'
                    ? ['w-name', 'w-work', 'w-location', 'w-phone', 'w-password']
                    : ['us-name', 'us-phone', 'us-password'];
                inputs.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) {
                        const parent = el.closest('.relative');
                        if (parent) parent.style.display = 'block';
                    }
                });
            });
        }
    },

    speak(text, onEndCallback) {
        const langCode = this.getCurrentLang();
        const fullLangCode = this.getSpeechLangCode(langCode);

        // For non-English/Hindi languages, native support is very poor, so we prefer Cloud TTS fallback
        if (!['en', 'hi'].includes(langCode)) {
            this.cloudSpeak(text, langCode, onEndCallback);
            return;
        }

        // 1. Try Native SpeechSynthesis first (Better integration, works offline)
        if (window.speechSynthesis) {
            window.speechSynthesis.cancel(); // Stop any current speech
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = fullLangCode;
            utterance.rate = 0.9;
            utterance.pitch = 1.0;

            utterance.onend = () => { if (onEndCallback) onEndCallback(); };
            utterance.onerror = (e) => {
                console.warn("Native SpeechSynthesis error, falling back to Cloud TTS:", e);
                this.cloudSpeak(text, langCode, onEndCallback);
            };

            window.speechSynthesis.speak(utterance);

            // Safety timeout for mobile browsers where onend might not fire
            setTimeout(() => {
                if (window.speechSynthesis.speaking === false && onEndCallback) {
                    // Already handled or failed
                }
            }, 5000);
        } else {
            this.cloudSpeak(text, langCode, onEndCallback);
        }
    },

    // Fallback Cloud TTS using Google Translate API
    cloudSpeak(text, lang, onEndCallback) {
        const url = `https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=${lang}&q=${encodeURIComponent(text)}`;
        const audio = new Audio(url);
        audio.onended = () => { if (onEndCallback) onEndCallback(); };
        audio.onerror = (e) => {
            console.error("Cloud TTS failed:", e);
            if (onEndCallback) onEndCallback();
        };
        audio.play().catch(err => {
            console.error("Audio playback blocked:", err);
            if (onEndCallback) onEndCallback();
        });
    },

    listenForAnswer() {
        if (!SpeechRecognition) return;
        const recognition = new SpeechRecognition();
        const lang = this.getCurrentLang();
        recognition.lang = this.getSpeechLangCode(lang);
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        const tBox = document.getElementById('ai-transcript');

        recognition.onstart = () => {
            tBox.style.display = 'block';
            tBox.innerText = 'Listening...';
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            tBox.innerText = `You said: "${transcript}"`;
            this.processAnswer(transcript);
        };

        recognition.onerror = (event) => {
            tBox.innerText = `Error: Please try speaking again.`;
            setTimeout(() => { if (aiActive) this.listenForAnswer(); }, 2000);
        };

        recognition.start();
    },

    listenForInput(targetId) {
        if (!SpeechRecognition) {
            alert('Speech recognition not supported in this browser.');
            return;
        }
        const recognition = new SpeechRecognition();
        const lang = this.getCurrentLang();
        recognition.lang = this.getSpeechLangCode(lang);

        const btn = document.querySelector(`#${targetId}`).parentElement.querySelector('button[aria-label="Voice input"]');
        const icon = btn ? btn.querySelector('.material-symbols-outlined') : null;
        const input = document.getElementById(targetId);

        recognition.onstart = () => {
            if (icon) {
                icon.innerText = 'graphic_eq';
                btn.classList.add('text-secondary');
            }
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            if (input) {
                if (targetId.includes('phone')) {
                    input.value = this.wordToDigits(transcript).slice(-10);
                } else if (targetId.includes('password')) {
                    input.value = this.wordsToMixedString(transcript);
                } else {
                    input.value = transcript;
                }
            }
        };

        recognition.onend = () => {
            if (icon) {
                icon.innerText = 'mic';
                btn.classList.remove('text-secondary');
            }
        };

        recognition.start();
    },

    getWordMap() {
        return {
            // English
            'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
            'oh': 0, 'to': 2, 'for': 4,
            // Hindi / Urdu / Marathi
            'शून्य': 0, 'एक': 1, 'दो': 2, 'तीन': 3, 'चार': 4, 'पांच': 5, 'छह': 6, 'सात': 7, 'आठ': 8, 'नौ': 9,
            // Bengali
            'শূন্য': 0, 'এক': 1, 'দুই': 2, 'তিন': 3, 'চার': 4, 'পাঁচ': 5, 'ছয়': 6, 'সাত': 7, 'আট': 8, 'নয়': 9,
            // Telugu
            'సున్నా': 0, 'ఒకటి': 1, 'రెండు': 2, 'మూడు': 3, 'నాలుగు': 4, 'అయిదు': 5, 'ఆరు': 6, 'ఏడు': 7, 'ఎనిమిది': 8, 'తొమ్మిది': 9,
            // Tamil
            'பூஜ்யம்': 0, 'ஒன்று': 1, 'இரண்டு': 2, 'மூன்று': 3, 'நான்கு': 4, 'ஐந்து': 5, 'ஆறு': 6, 'ஏழு': 7, 'எட்டு': 8, 'ஒன்பது': 9,
            // Gujarati
            'શૂન્ય': 0, 'એક': 1, 'બે': 2, 'ત્રણ': 3, 'ચાર': 4, 'પાંચ': 5, 'છ': 6, 'સાત': 7, 'આઠ': 8, 'નવ': 9,
            // Kannada
            'ಸೊನ್ನೆ': 0, 'ಒಂದು': 1, 'ಎರಡು': 2, 'ಮೂರು': 3, 'ನಾಲ್ಕು': 4, 'ಐದು': 5, 'ಆರು': 6, 'ಏಳು': 7, 'ಎಂಟು': 8, 'ಒಂಬತ್ತು': 9,
            // Malayalam
            'പൂജ്യം': 0, 'ഒന്ന്': 1, 'രണ്ട്': 2, 'മൂന്ന്': 3, 'നാല്': 4, 'അഞ്ച്': 5, 'ആറ്': 6, 'ഏഴ്': 7, 'എട്ട്': 8, 'ഒൻപത്': 9,
            // Punjabi
            'ਸਿਫ਼ਰ': 0, 'ਇੱਕ': 1, 'ਦੋ': 2, 'ਤਿੰਨ': 3, 'ਚਾਰ': 4, 'ਪੰਜ': 5, 'ਛੇ': 6, 'ਸੱਤ': 7, 'ਅੱਠ': 8, 'ਨੌਂ': 9,
        };
    },

    // Converts spoken number words → digits string
    wordToDigits(text) {
        const wordMap = this.getWordMap();

        // First try raw digit extraction
        const rawDigits = text.replace(/[^0-9]/g, '');
        if (rawDigits.length >= 10) return rawDigits;

        // Try word-by-word conversion
        const words = text.toLowerCase().trim().split(/\s+/);
        let digits = '';
        for (const w of words) {
            const clean = w.replace(/[.,!?।]/g, '');
            if (clean in wordMap) {
                digits += wordMap[clean];
            } else if (!isNaN(clean) && clean !== '') {
                digits += clean;
            }
        }
        return digits;
    },

    // Flexible word mapping for passwords
    wordsToMixedString(text) {
        const wordMap = this.getWordMap();
        const words = text.toLowerCase().trim().split(/\s+/);
        return words.map(w => {
            const clean = w.replace(/[.,!?।]/g, '');
            return clean in wordMap ? wordMap[clean] : clean;
        }).join('');
    },

    processAnswer(text) {
        const trimmed = text.trim();
        const retryPrompt = document.getElementById('ai-retry').innerText;

        if (this.aiRole === 'worker') {
            if (aiStep === 0) {
                if (trimmed) {
                    document.getElementById('w-name').value = this.capitalize(trimmed);
                    aiStep++;
                } else {
                    this.speak(retryPrompt, () => { this.askNextQuestion(); });
                    return;
                }
            }
            else if (aiStep === 1) {
                if (trimmed) {
                    document.getElementById('w-work').value = this.capitalize(trimmed);
                    aiStep++;
                } else {
                    this.speak(retryPrompt, () => { this.askNextQuestion(); });
                    return;
                }
            }
            else if (aiStep === 2) {
                if (trimmed) {
                    document.getElementById('w-location').value = this.capitalize(trimmed);
                    aiStep++;
                } else {
                    this.speak(retryPrompt, () => { this.askNextQuestion(); });
                    return;
                }
            }
            else if (aiStep === 3) {
                const allDigits = this.wordToDigits(text);
                if (allDigits.length >= 10) {
                    document.getElementById('w-phone').value = allDigits.slice(-10);
                    aiStep++;
                } else {
                    this.speak(retryPrompt, () => { this.listenForAnswer(); });
                    return;
                }
            }
            else if (aiStep === 4) {
                aiStep++;
            }
        } else {
            // User Signup Flow
            if (aiStep === 0) {
                if (trimmed) {
                    document.getElementById('us-name').value = this.capitalize(trimmed);
                    aiStep++;
                } else {
                    this.speak(retryPrompt, () => { this.askNextQuestion(); });
                    return;
                }
            }
            else if (aiStep === 1) {
                const allDigits = this.wordToDigits(text);
                if (allDigits.length >= 10) {
                    document.getElementById('us-phone').value = allDigits.slice(-10);
                    aiStep++;
                } else {
                    this.speak(retryPrompt, () => { this.listenForAnswer(); });
                    return;
                }
            }
            else if (aiStep === 2) {
                aiStep++; // Password step placeholder
            }
        }

        setTimeout(() => { this.askNextQuestion(); }, 1500);
    },

    capitalize(str) {
        if (!str) return '';
        return str.charAt(0).toUpperCase() + str.slice(1);
    },

    // ---------------- JOBS / QUERIES ---------------- //

    async handleJobPost(e) {
        e.preventDefault();
        const service_type = document.getElementById('j-service').value;
        const description = document.getElementById('j-desc').value;
        const locationElem = document.getElementById('j-loc');
        const location = locationElem ? locationElem.value : 'Unknown';
        const is_urgent = document.getElementById('j-urgent')?.checked || false;

        try {
            const res = await fetch('/api/jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ service_type, description, location, is_urgent })
            });
            if (res.ok) {
                alert("Job request posted successfully! Workers will see it.");
                document.getElementById('job-post-form').reset();
                this.fetchCustomerJobs();
            } else {
                alert("Failed to post job");
            }
        } catch (e) {
            alert("Connection error");
        }
    },

    async fetchJobsForWorker(workType) {
        const listDiv = document.getElementById('jobs-list');
        if (!listDiv) return;

        listDiv.innerHTML = `<div class="text-slate-400 italic">Loading jobs...</div>`;

        try {
            const url = workType ? `/api/jobs?work=${encodeURIComponent(workType)}` : `/api/jobs`;
            const response = await fetch(url);
            const jobs = await response.json();

            listDiv.innerHTML = '';

            if (jobs.length === 0) {
                listDiv.innerHTML = `<div class="text-slate-400 italic">No new jobs matching "${workType}" right now.</div>`;
                return;
            }

            jobs.forEach(j => {
                const card = document.createElement('div');
                card.className = 'card p-6 flex flex-col gap-4 animate-slide-up';

                const dateStr = new Date(j.created_at).toLocaleDateString();

                card.innerHTML = `
                    <div class="flex justify-between items-start">
                        <div>
                            <span class="text-[10px] font-black text-secondary uppercase tracking-widest mb-1 block">${j.service_type}</span>
                            <h4>${j.description}</h4>
                            <p class="text-muted text-xs mt-1"><i class="fa-solid fa-location-dot mr-1"></i> ${j.location || 'Unknown'}</p>
                        </div>
                        <span class="badge sm">${dateStr}</span>
                    </div>
                    
                    <div class="flex items-center justify-between pt-4 border-t border-slate-100">
                        <div class="flex items-center gap-2">
                            <div class="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 overflow-hidden border">
                                ${j.user_profile_pic ? `<img src="/static/${j.user_profile_pic}" class="w-full h-full object-cover">` : `<i class="fa-solid fa-user text-xs"></i>`}
                            </div>
                            <span class="text-xs font-bold">${j.user_name}</span>
                        </div>
                        <div class="flex gap-2">
                            <a href="tel:${j.user_phone}" class="btn btn-outline sm"><i class="fa-solid fa-phone"></i></a>
                            ${j.status === 'open' ? `<button onclick="app.acceptJob(${j.id}, '${workType}')" class="btn btn-primary sm">${app.translations ? (app.translations['Accept'] || 'Accept') : 'Accept'}</button>` : `<span class="badge sm success">Accepted</span>`}
                        </div>
                    </div>
                `;
                listDiv.appendChild(card);
            });
        } catch (error) {
            listDiv.innerHTML = `<div class="text-red-400 italic">Error loading jobs.</div>`;
        }
    },

    async fetchCustomerJobs() {
        const listDiv = document.getElementById('my-jobs-list');
        if (!listDiv) return;

        listDiv.innerHTML = `<div class="text-slate-400 italic">Loading your jobs...</div>`;

        try {
            const response = await fetch('/api/jobs/customer');
            const jobs = await response.json();
            listDiv.innerHTML = '';

            if (jobs.length === 0) {
                listDiv.innerHTML = `<div class="text-slate-400 italic">You haven't posted any jobs yet.</div>`;
                return;
            }

            jobs.forEach(j => {
                const card = document.createElement('div');
                card.className = 'card p-6 flex flex-col gap-4 animate-slide-up';

                card.innerHTML = `
                    <div class="flex justify-between items-start">
                        <div>
                            <span class="badge sm ${j.status === 'open' ? 'warning' : 'success'}">${j.status}</span>
                            <h4 class="mt-2">${j.service_type}</h4>
                        </div>
                        ${j.price ? `<span class="text-lg font-black text-primary">₹${j.price}</span>` : ''}
                    </div>

                    ${j.worker_name ? `
                        <div class="flex items-center gap-3 p-3 bg-slate-50 rounded-xl border border-slate-100">
                            <div class="w-8 h-8 rounded-full bg-white flex items-center justify-center border text-muted overflow-hidden">
                                <i class="fa-solid fa-user-gear text-xs"></i>
                            </div>
                            <div class="flex-1">
                                <p class="text-xs font-bold">${j.worker_name}</p>
                                <p class="text-[10px] text-muted">${j.worker_phone}</p>
                            </div>
                        </div>
                    ` : ''}

                    <div class="flex gap-2 mt-2">
                        ${j.status === 'accepted' ? `
                            <button onclick="app.showCompletionQR('${j.completion_token}')" class="btn btn-primary sm flex-1">
                                <i class="fa-solid fa-qrcode mr-2"></i> ${app.translations ? (app.translations['Complete'] || 'Complete') : 'Complete'}
                            </button>
                            <button onclick="app.trackWorker(${j.id})" class="btn btn-outline sm">
                                <i class="fa-solid fa-location-crosshairs"></i>
                            </button>
                        ` : j.status === 'completed' ? `
                            <button onclick="app.showReviewModal(${j.id}, ${j.worker_id})" class="btn btn-outline sm w-full">
                                ${app.translations ? (app.translations['Leave Review'] || 'Leave Review') : 'Leave Review'}
                            </button>
                        ` : ''}
                    </div>
                `;
                listDiv.appendChild(card);
            });
        } catch (e) {
            listDiv.innerHTML = `<div class="text-red-400 italic">Error loading jobs.</div>`;
        }
    },

    async acceptJob(jobId, workType) {
        const amount = prompt("Enter the amount for this job (in ₹):", "500");
        if (amount === null) return; // Cancelled
        
        try {
            const res = await fetch(`/api/jobs/${jobId}/accept`, { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ price: amount })
            });
            if (res.ok) {
                alert("Job accepted! The user will be notified of your price.");
                this.fetchJobsForWorker(workType);
            } else {
                const data = await res.json();
                alert(data.error || "Failed to accept job");
            }
        } catch (e) {
            alert("Connection error");
        }
    },

    async updateJobStatus(jobId, status, workerId) {
        try {
            const res = await fetch(`/api/jobs/${jobId}/status`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status })
            });
            if (res.ok) {
                alert("Job marked as " + status);
                this.fetchCustomerJobs();
                if (status === 'completed') {
                    this.showReviewModal(jobId, workerId);
                }
            } else {
                alert("Failed to update status");
            }
        } catch (e) {
            alert("Connection error");
        }
    },

    showReviewModal(jobId, workerId) {
        const modal = document.getElementById('review-modal');
        if (!modal) return;

        document.getElementById('rev-job-id').value = jobId;
        document.getElementById('rev-worker-id').value = workerId;
        document.getElementById('rev-text').value = '';
        this.setRating(0);

        modal.classList.remove('hidden');
    },

    closeReviewModal() {
        const modal = document.getElementById('review-modal');
        if (modal) modal.classList.add('hidden');
    },

    setRating(val) {
        document.getElementById('rev-rating').value = val;
        const stars = document.querySelectorAll('.star-btn');
        stars.forEach((s, idx) => {
            if (idx < val) {
                s.classList.remove('text-slate-300');
                s.classList.add('text-yellow-400');
            } else {
                s.classList.add('text-slate-300');
                s.classList.remove('text-yellow-400');
            }
        });
    },

    async submitReviewFromModal() {
        const jobId = document.getElementById('rev-job-id').value;
        const workerId = document.getElementById('rev-worker-id').value;
        const rating = document.getElementById('rev-rating').value;
        const review = document.getElementById('rev-text').value;

        if (!rating || rating == 0) {
            alert("Please select a star rating.");
            return;
        }

        await this.submitReview(workerId, jobId, rating, review);
        this.closeReviewModal();
        this.fetchCustomerJobs();
    },

    async fetchDashboardBookings() {
        const container = document.getElementById('dashboard-bookings-list');
        if (!container) return;

        try {
            const res = await fetch('/api/bookings');
            const bookings = await res.json();
            const upcoming = bookings.filter(b => ['Pending', 'Booked', 'Work Started'].includes(b.status));

            if (upcoming.length === 0) {
                container.innerHTML = `<div class="col-span-full py-8 text-center text-slate-400 italic text-sm">No upcoming bookings.</div>`;
                return;
            }

            const isWorker = window.location.pathname.includes('worker');
            container.innerHTML = upcoming.slice(0, 4).map(b => `
                <a href="/bookings/${b.id}" class="card p-4 flex items-center justify-between hover:border-primary transition-all animate-slide-up" style="text-decoration:none">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center text-muted overflow-hidden border">
                            ${(isWorker ? b.customer_profile_pic : b.worker_profile_pic) 
                                ? `<img src="/static/${isWorker ? b.customer_profile_pic : b.worker_profile_pic}" class="w-full h-full object-cover">` 
                                : `<i class="fa-solid fa-calendar-day"></i>`}
                        </div>
                        <div>
                            <p class="font-bold text-sm">${isWorker ? b.customer_name : b.worker_name}</p>
                            <p class="text-[10px] text-muted font-bold uppercase tracking-wider">${b.date} • ${b.time_slot}</p>
                        </div>
                    </div>
                    <span class="badge sm ${b.status === 'Work Started' ? 'success' : 'primary'}">
                        ${b.status}
                    </span>
                </a>
            `).join('');
        } catch (e) {
            console.error(e);
        }
    },

    async fetchWorkerPendingBookings() {
        const container = document.getElementById('pending-bookings-list');
        if (!container) return;

        try {
            const res = await fetch('/api/bookings');
            const bookings = await res.json();
            const pending = bookings.filter(b => b.status === 'Pending');

            if (pending.length === 0) {
                container.parentElement.style.display = 'none';
                return;
            }

            container.parentElement.style.display = 'block';
            container.innerHTML = pending.map(b => `
                <div class="card p-6 border-coral/30 bg-coral/5 animate-slide-up space-y-4">
                    <div class="flex items-center gap-4">
                        <div class="w-12 h-12 rounded-2xl bg-white flex items-center justify-center text-coral border border-coral/20 shadow-sm overflow-hidden">
                            ${b.customer_profile_pic 
                                ? `<img src="/static/${b.customer_profile_pic}" class="w-full h-full object-cover">` 
                                : `<i class="fa-solid fa-user"></i>`}
                        </div>
                        <div class="flex-1 min-w-0">
                            <p class="font-black truncate">${b.customer_name}</p>
                            <p class="text-[10px] text-muted font-bold uppercase tracking-widest">${b.date} • ${b.time_slot}</p>
                        </div>
                    </div>
                    
                    <div class="flex gap-2">
                        <button onclick="app.acceptBookingDirectly(${b.id})" 
                            class="btn btn-primary sm flex-1">
                            ${app.translations ? (app.translations['Accept Now'] || 'Accept Now') : 'Accept Now'}
                        </button>
                        <button onclick="location.href='/bookings/${b.id}'" 
                            class="btn btn-outline sm flex-1">
                            ${app.translations ? (app.translations['Details'] || 'Details') : 'Details'}
                        </button>
                    </div>
                </div>
            `).join('');
        } catch (e) {
            console.error(e);
        }
    },

    async acceptBookingDirectly(bookingId) {
        if (!confirm("Accept this booking request?")) return;
        try {
            const res = await fetch(`/api/bookings/${bookingId}/accept`, { method: 'POST' });
            if (res.ok) {
                alert("Booking accepted!");
                this.fetchWorkerPendingBookings();
            } else {
                const data = await res.json();
                alert(data.error || "Failed to accept");
            }
        } catch (e) {
            alert("Connection error");
        }
    },

    setServiceFilter(val) {
        const input = document.getElementById('u-service');
        if (input) {
            input.value = (val === 'All') ? '' : val;
            this.fetchWorkers();
        }
    },

    detectLocation(targetId) {
        if (!navigator.geolocation) {
            alert("Geolocation is not supported by your browser");
            return;
        }

        const input = document.getElementById(targetId);
        const icon = input.parentElement.querySelector('.material-symbols-outlined');
        if (icon) icon.classList.add('animate-pulse', 'text-secondary');

        navigator.geolocation.getCurrentPosition(async (position) => {
            try {
                const lat = position.coords.latitude;
                const lon = position.coords.longitude;

                // Save coordinates if hidden fields exist
                const latField = document.getElementById('w-lat');
                const lngField = document.getElementById('w-lng');
                if (latField) latField.value = lat;
                if (lngField) lngField.value = lon;

                const res = await fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json`);
                const data = await res.json();

                const loc = data.address.city || data.address.town || data.address.village || data.address.suburb || "Unknown";
                if (input) input.value = loc;
            } catch (e) {
                alert("Could not detect location automatically.");
            } finally {
                if (icon) icon.classList.remove('animate-pulse', 'text-secondary');
            }
        }, () => {
            alert("Location access denied.");
            if (icon) icon.classList.remove('animate-pulse', 'text-secondary');
        });
    },

    // ---------------- MAP VIEW ---------------- //
    map: null,
    markers: [],

    toggleView(view) {
        const listDiv = document.getElementById('workers-list');
        const mapContainer = document.getElementById('map-container');
        const btnList = document.getElementById('btn-list-view');
        const btnMap = document.getElementById('btn-map-view');

        if (view === 'map') {
            listDiv.style.display = 'none';
            mapContainer.style.display = 'block';
            btnMap.className = 'flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg text-sm font-bold transition-all shadow-sm';
            btnList.className = 'flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-bold transition-all';

            this.initMap();
        } else {
            listDiv.style.display = 'grid';
            mapContainer.style.display = 'none';
            btnList.className = 'flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-lg text-sm font-bold transition-all shadow-sm';
            btnMap.className = 'flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-sm font-bold transition-all';
        }
    },

    initMap() {
        if (this.map) {
            this.map.invalidateSize();
            return;
        }

        // Default to India center if no workers
        this.map = L.map('map-view').setView([20.5937, 78.9629], 5);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(this.map);

        this.updateMapMarkers();
    },

    updateMapMarkers() {
        if (!this.map) return;

        // Clear existing markers
        this.markers.forEach(m => this.map.removeLayer(m));
        this.markers = [];

        const workers = this.lastFetchedWorkers || [];
        const validWorkers = workers.filter(w => w.latitude && w.longitude);

        if (validWorkers.length > 0) {
            const group = new L.featureGroup();
            validWorkers.forEach(w => {
                const marker = L.marker([w.latitude, w.longitude]).addTo(this.map);
                marker.bindPopup(`
                    <div class="p-2 min-w-[150px]">
                        <h4 class="font-bold text-sm flex items-center gap-1">
                            ${w.name}
                            ${w.is_verified ? '<span class="material-symbols-outlined text-green-600 text-sm">verified</span>' : ''}
                        </h4>
                        <p class="text-xs text-slate-500">${w.work}</p>
                        <p class="text-xs text-slate-400 mb-2">${w.location}</p>
                        <div class="flex gap-2">
                            <a href="tel:${w.phone}" class="bg-primary text-white p-1 rounded-full flex items-center justify-center w-8 h-8">
                                <span class="material-symbols-outlined text-sm">call</span>
                            </a>
                            <a href="https://wa.me/91${w.phone}" target="_blank" class="bg-green-500 text-white p-1 rounded-full flex items-center justify-center w-8 h-8">
                                <img src="https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg" class="w-4 h-4 filter brightness-0 invert">
                            </a>
                            <a href="/book/${w.id}" class="bg-[#00668a] text-white p-1 rounded-full flex items-center justify-center w-8 h-8" title="Book Now">
                                <span class="material-symbols-outlined text-sm">calendar_month</span>
                            </a>
                        </div>
                    </div>
                `);
                this.markers.push(marker);
                group.addLayer(marker);
            });
            this.map.fitBounds(group.getBounds().pad(0.1));
        }
    },

    async geocodeAddress(address) {
        try {
            const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(address)}`);
            const data = await res.json();
            if (data && data.length > 0) {
                return { lat: data[0].lat, lon: data[0].lon };
            }
        } catch (e) {
            console.error("Geocoding error:", e);
        }
        return null;
    },

    async submitReview(workerId, jobId, rating, review) {
        try {
            const res = await fetch(`/api/workers/${workerId}/rate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ job_id: jobId, rating: parseInt(rating), review: review || '' })
            });
            if (res.ok) {
                alert("Review submitted!");
            } else {
                const data = await res.json();
                alert(data.error || "Failed to submit review");
            }
        } catch (e) {
            alert("Connection error");
        }
    },

    // ---------------- BROWSE WORKERS ---------------- //

    async fetchWorkers() {
        const listDiv = document.getElementById('workers-list');
        if (!listDiv) return;

        listDiv.innerHTML = `<div class="text-slate-400 italic">Loading workers...</div>`;

        const serviceElem = document.getElementById('u-service');
        const locElem = document.getElementById('u-location');
        const service = serviceElem ? serviceElem.value : '';
        const loc = locElem ? locElem.value : '';

        const params = new URLSearchParams();
        if (service) params.append('work', service);
        if (loc) params.append('location', loc);

        const url = `/get_workers?${params.toString()}`;

        try {
            const response = await fetch(url);
            const workers = await response.json();
            this.lastFetchedWorkers = workers; // Store for map view

            listDiv.innerHTML = '';

            if (workers.length === 0) {
                listDiv.innerHTML = `<div class="text-slate-400 italic">No workers found.</div>`;
                if (this.map) this.updateMapMarkers();
                return;
            }

            // Update map if initialized
            if (this.map) this.updateMapMarkers();

            workers.forEach(w => {
                const card = document.createElement('div');
                card.className = 'card p-6 flex flex-col gap-6 hover:border-primary transition-all animate-slide-up';

                const ratingHtml = w.review_count > 0 ? `
                    <div class="flex items-center gap-1">
                        <span class="text-coral font-bold">★ ${parseFloat(w.avg_rating).toFixed(1)}</span>
                        <span class="text-[10px] text-muted">(${w.review_count} ${app.translations ? (app.translations['reviews'] || 'reviews') : 'reviews'})</span>
                    </div>
                ` : `<span class="text-[10px] text-muted italic">${app.translations ? (app.translations['No reviews'] || 'No reviews') : 'No reviews'}</span>`;

                card.innerHTML = `
                    <div class="flex justify-between items-start">
                        <div class="flex items-center gap-4">
                            <div class="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center border-2 border-primary/10 overflow-hidden shadow-sm">
                                ${w.profile_pic ? `<img src="/static/${w.profile_pic}" class="w-full h-full object-cover">` : `<i class="fa-solid fa-user-tie text-2xl text-muted"></i>`}
                            </div>
                            <div>
                                <h4 class="flex items-center gap-2">
                                    ${w.name}
                                    ${w.is_verified ? '<i class="fa-solid fa-circle-check text-green-500 text-sm"></i>' : ''}
                                </h4>
                                ${ratingHtml}
                                <div class="flex gap-2 mt-1">
                                    <span class="text-[10px] font-bold text-secondary uppercase tracking-widest"><i class="fa-solid fa-briefcase mr-1"></i>${w.work}</span>
                                    <span class="text-[10px] font-bold text-muted uppercase tracking-widest"><i class="fa-solid fa-location-dot mr-1"></i>${w.location}</span>
                                </div>
                            </div>
                        </div>
                        <div class="flex flex-col gap-2">
                            <a href="tel:${w.phone}" class="btn btn-outline btn-icon sm"><i class="fa-solid fa-phone"></i></a>
                            <a href="https://wa.me/91${w.phone}" target="_blank" class="btn btn-outline btn-icon sm" style="border-color: #25D366; color: #25D366;"><i class="fa-brands fa-whatsapp"></i></a>
                        </div>
                    </div>

                    ${w.voice_resume ? `
                        <div class="p-4 bg-slate-50 rounded-2xl border border-slate-100 italic text-xs text-muted">
                            <i class="fa-solid fa-quote-left mr-2 opacity-20"></i>${w.voice_resume}
                        </div>
                    ` : ''}

                    <div class="flex items-center justify-between pt-6 border-t border-slate-100">
                        <div>
                            <span class="text-[10px] font-black text-muted uppercase tracking-widest block">${app.translations ? (app.translations['Hourly Rate'] || 'Hourly Rate') : 'Hourly Rate'}</span>
                            <span class="text-xl font-black text-primary">₹${w.price || 0}<span class="text-xs text-muted font-bold">/hr</span></span>
                        </div>
                        <a href="/book/${w.id}" class="btn btn-primary sm px-8">
                            <i class="fa-solid fa-calendar-check mr-2"></i>${app.translations ? (app.translations['Book Now'] || 'Book Now') : 'Book Now'}
                        </a>
                    </div>
                `;

                if (w.voice_note || w.video) {
                    const mediaDiv = document.createElement('div');
                    mediaDiv.className = 'flex flex-col gap-4 mt-2 pt-4 border-t border-slate-100';

                    if (w.voice_note) {
                        const auDiv = document.createElement('div');
                        auDiv.className = 'flex flex-col gap-2';
                        auDiv.innerHTML = `<span class="text-[10px] font-bold text-muted uppercase tracking-widest"><i class="fa-solid fa-microphone mr-1"></i> Voice Note</span>`;
                        const audio = document.createElement('audio');
                        audio.controls = true;
                        audio.className = 'w-full';
                        audio.src = `/static/${w.voice_note}`;
                        auDiv.appendChild(audio);
                        mediaDiv.appendChild(auDiv);
                    }
                    if (w.video) {
                        const vidDiv = document.createElement('div');
                        vidDiv.className = 'flex flex-col gap-2';
                        vidDiv.innerHTML = `<span class="text-[10px] font-bold text-muted uppercase tracking-widest"><i class="fa-solid fa-video mr-1"></i> Video Portfolio</span>`;
                        const video = document.createElement('video');
                        video.controls = true;
                        video.className = 'w-full rounded-2xl border shadow-sm max-h-64';
                        video.src = `/static/${w.video}`;
                        vidDiv.appendChild(video);
                        mediaDiv.appendChild(vidDiv);
                    }
                    card.appendChild(mediaDiv);
                }
                listDiv.appendChild(card);
            });
        } catch (error) {
            listDiv.innerHTML = `<div class="text-red-400 italic">Error loading workers.</div>`;
        }
    },

    async handleUserEdit(e) {
        e.preventDefault();
        const btn = document.getElementById('btn-update-user');
        if (btn) { btn.innerHTML = "Saving..."; btn.disabled = true; }

        const formElement = document.getElementById('user-edit-form');
        const formData = new FormData(formElement);

        try {
            const res = await fetch('/api/auth/profile/user', {
                method: 'POST',
                body: formData
            });
            if (res.ok) {
                alert("Profile updated successfully!");
                location.reload();
            } else {
                const data = await res.json();
                alert(data.error || "Update failed");
            }
        } catch (err) {
            alert("Connection error");
        } finally {
            if (btn) { btn.innerHTML = "Update Profile"; btn.disabled = false; }
        }
    },

    async handleWorkerEdit(e) {
        e.preventDefault();
        const btn = document.getElementById('btn-update-worker');
        if (btn) { btn.innerHTML = "Saving..."; btn.disabled = true; }

        const formElement = document.getElementById('worker-edit-form');

        // Ensure we have lat/lng
        const lat = document.getElementById('w-lat').value;
        const lng = document.getElementById('w-lng').value;
        const location = document.getElementById('edit-w-loc').value;

        if (!lat || !lng) {
            const coords = await this.geocodeAddress(location);
            if (coords) {
                document.getElementById('w-lat').value = coords.lat;
                document.getElementById('w-lng').value = coords.lon;
            }
        }

        const formData = new FormData(formElement);

        try {
            const res = await fetch('/api/worker/edit', {
                method: 'POST',
                body: formData
            });

            if (res.ok) {
                alert("Profile updated successfully!");
                window.location.reload();
            } else {
                const data = await res.json();
                alert('Update failed: ' + (data.error || 'Unknown error'));
            }
        } catch (err) {
            alert('Connection Error.');
        } finally {
            if (btn) { btn.innerHTML = "Save Changes"; btn.disabled = false; }
        }
    },

    // ---------------- VOICE RESUME ---------------- //
    startVoiceResume() {
        if (!SpeechRecognition) return alert("Speech recognition not supported");
        const rec = new SpeechRecognition();
        const lang = document.documentElement.lang || 'en';
        rec.lang = this.getSpeechLangCode(lang);

        const btn = document.getElementById('btn-record-resume');
        const display = document.getElementById('voice-resume-display');

        rec.onstart = () => {
            btn.innerHTML = `<span class="material-symbols-outlined animate-pulse text-red-500">mic</span> Listening...`;
            btn.disabled = true;
        };

        rec.onresult = async (e) => {
            const transcript = e.results[0][0].transcript;
            display.innerHTML = `<p class="text-xs font-medium text-slate-700 italic">"${transcript}"</p>`;

            // Save to server
            try {
                const res = await fetch('/api/worker/voice-resume', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ transcript })
                });
                if (res.ok) {
                    btn.innerHTML = `<span class="material-symbols-outlined text-green-500">check_circle</span> Saved!`;
                }
            } catch (err) {
                console.error(err);
            }
        };

        rec.onend = () => {
            setTimeout(() => {
                btn.innerHTML = `<span class="material-symbols-outlined text-sm">record_voice_over</span> Record New Resume`;
                btn.disabled = false;
            }, 3000);
        };

        rec.start();
    },

    // ---------------- LOCATION TRACKING ---------------- //
    locationInterval: null,

    async toggleLocationSharing(current) {
        const newState = !current;
        if (newState) {
            if (!navigator.geolocation) return alert("Geolocation not supported");

            const startSharing = async () => {
                navigator.geolocation.getCurrentPosition(async (pos) => {
                    const { latitude, longitude } = pos.coords;
                    await fetch('/api/worker/location', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ lat: latitude, lng: longitude })
                    });
                }, (err) => console.error(err), { enableHighAccuracy: true });
            };

            await startSharing();
            this.locationInterval = setInterval(startSharing, 30000); // Every 30s
            alert("Location sharing started. Customers can now track your progress.");
        } else {
            clearInterval(this.locationInterval);
            await fetch('/api/worker/location/stop', { method: 'POST' });
            alert("Location sharing stopped.");
        }
        window.location.reload();
    },

    trackingInterval: null,
    trackingMap: null,
    trackingMarker: null,

    async trackWorker(jobId) {
        const modal = document.getElementById('track-modal');
        if (!modal) return;
        modal.classList.remove('hidden');

        const updateMap = async () => {
            try {
                const res = await fetch(`/api/jobs/${jobId}/track`);
                if (!res.ok) throw new Error();
                const data = await res.json();

                if (!data.lat || !data.lng) {
                    document.getElementById('track-last-update').innerText = "Worker not sharing location";
                    return;
                }

                document.getElementById('track-worker-name').innerText = data.worker_name;
                document.getElementById('track-worker-avatar').innerText = data.worker_name[0];
                document.getElementById('track-call-btn').href = `tel:${data.worker_phone}`;
                document.getElementById('track-last-update').innerText = "Updated just now";

                const pos = [data.lat, data.lng];

                if (!this.trackingMap) {
                    // Slight delay to ensure modal is visible for Leaflet to calculate size
                    setTimeout(() => {
                        this.trackingMap = L.map('track-map').setView(pos, 15);
                        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(this.trackingMap);
                        this.trackingMarker = L.marker(pos).addTo(this.trackingMap);
                    }, 300);
                } else {
                    this.trackingMarker.setLatLng(pos);
                    this.trackingMap.panTo(pos);
                }
            } catch (e) {
                console.error("Tracking failed", e);
            }
        };

        await updateMap();
        this.trackingInterval = setInterval(updateMap, 30000);
    },

    stopTracking() {
        const modal = document.getElementById('track-modal');
        if (modal) modal.classList.add('hidden');
        clearInterval(this.trackingInterval);
        if (this.trackingMap) {
            this.trackingMap.remove();
            this.trackingMap = null;
        }
    },

    // ---------------- QR COMPLETION ---------------- //
    showCompletionQR(token) {
        const modal = document.getElementById('qr-modal');
        const container = document.getElementById('qrcode-container');
        if (!modal || !container) return;

        container.innerHTML = '';
        const url = window.location.origin + '/complete-job/' + token;

        new QRCode(container, {
            text: url,
            width: 200,
            height: 200,
            colorDark: "#000000",
            colorLight: "#ffffff",
            correctLevel: QRCode.CorrectLevel.H
        });

        modal.classList.remove('hidden');
    },

    closeQRModal() {
        const modal = document.getElementById('qr-modal');
        if (modal) modal.classList.add('hidden');
    },

    // ---------------- WORKER DASHBOARD ACTIONS ---------------- //
    async toggleAvailability(current) {
        try {
            const res = await fetch('/api/worker/availability', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_available: !current })
            });
            if (res.ok) {
                window.location.reload();
            } else {
                const data = await res.json();
                alert('Update failed: ' + (data.error || 'Unknown error'));
            }
        } catch (err) {
            console.error(err);
            alert('Connection Error');
        }
    },

    async toggleLocationSharing(current) {
        try {
            const res = await fetch('/api/worker/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_sharing: !current })
            });
            if (res.ok) {
                window.location.reload();
            } else {
                const data = await res.json();
                alert('Update failed: ' + (data.error || 'Unknown error'));
            }
        } catch (err) {
            console.error(err);
            alert('Connection Error');
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    app.init();

    // Bind new forms if they exist
    const editForm = document.getElementById('worker-edit-form');
    if (editForm) {
        editForm.addEventListener('submit', (e) => app.handleWorkerEdit(e));
    }
});