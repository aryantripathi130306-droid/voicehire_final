// ============================================================
// VOICEHIRE APP.JS PART 1 - FOUNDATION, AUTH, VOICE ONBOARDING
// Aligned with: part1_foundation_auth.py
// Owns: init/bindEvents, language helpers, login, signup,
// worker voice signup assistant, mic input helpers.
// Combine order: Part 1 -> Part 2 -> Part 3 -> Part 4.
// ============================================================
let selectedRole = localStorage.getItem('voicehire_role') || 'user';
let aiStep = 0;
let aiActive = false;

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const app = {
    init() {
        this.bindEvents();
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
        const match = document.cookie.match(/googtrans=\/en\/([a-z]{2})/);
        return match ? match[1] : 'en';
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

    startStepByStepAI() {
        if (!SpeechRecognition) {
            alert('Your browser does not support full AI features. Please use Google Chrome or a modern browser.');
            return;
        }

        aiActive = true;
        aiStep = 0;

        // Hide all parent containers of inputs
        const inputs = ['w-name', 'w-work', 'w-location', 'w-phone', 'w-password'];
        inputs.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.closest('.relative').style.display = 'none';
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

        if (aiStep < 5) {
            const promptStr = document.getElementById(`ai-p${aiStep}`).innerText;
            qText.innerText = promptStr;
            this.speak(promptStr, () => {
                anim.style.display = 'flex';
                this.listenForAnswer();
            });
        } else {
            const finalPrompt = document.getElementById('ai-p5').innerText;
            qText.innerText = finalPrompt;
            this.speak(finalPrompt, () => {
                const inputs = ['w-name', 'w-work', 'w-location', 'w-phone', 'w-password'];
                inputs.forEach(id => {
                    const el = document.getElementById(id);
                    if (el) el.closest('.relative').style.display = 'block';
                });
            });
        }
    },

    speak(text, onEndCallback) {
        const lang = this.getCurrentLang();
        const url = `https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=${lang}&q=${encodeURIComponent(text)}`;
        const audio = new Audio(url);
        audio.onended = () => {
            if (onEndCallback) onEndCallback();
        };
        audio.onerror = (e) => {
            console.error("Cloud TTS failed, falling back to instant answer mode.", e);
            if (onEndCallback) onEndCallback();
        };
        audio.play().catch(e => {
            console.error("Audio play blocked by browser:", e);
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
            'à¤¶à¥‚à¤¨à¥à¤¯': 0, 'à¤à¤•': 1, 'à¤¦à¥‹': 2, 'à¤¤à¥€à¤¨': 3, 'à¤šà¤¾à¤°': 4, 'à¤ªà¤¾à¤‚à¤š': 5, 'à¤›à¤¹': 6, 'à¤¸à¤¾à¤¤': 7, 'à¤†à¤ ': 8, 'à¤¨à¥Œ': 9,
            // Bengali
            'à¦¶à§‚à¦¨à§à¦¯': 0, 'à¦à¦•': 1, 'à¦¦à§à¦‡': 2, 'à¦¤à¦¿à¦¨': 3, 'à¦šà¦¾à¦°': 4, 'à¦ªà¦¾à¦à¦š': 5, 'à¦›à¦¯à¦¼': 6, 'à¦¸à¦¾à¦¤': 7, 'à¦†à¦Ÿ': 8, 'à¦¨à¦¯à¦¼': 9,
            // Telugu
            'à°¸à±à°¨à±à°¨à°¾': 0, 'à°’à°•à°Ÿà°¿': 1, 'à°°à±†à°‚à°¡à±': 2, 'à°®à±‚à°¡à±': 3, 'à°¨à°¾à°²à±à°—à±': 4, 'à°…à°¯à°¿à°¦à±': 5, 'à°†à°°à±': 6, 'à°à°¡à±': 7, 'à°Žà°¨à°¿à°®à°¿à°¦à°¿': 8, 'à°¤à±Šà°®à±à°®à°¿à°¦à°¿': 9,
            // Tamil
            'à®ªà¯‚à®œà¯à®¯à®®à¯': 0, 'à®’à®©à¯à®±à¯': 1, 'à®‡à®°à®£à¯à®Ÿà¯': 2, 'à®®à¯‚à®©à¯à®±à¯': 3, 'à®¨à®¾à®©à¯à®•à¯': 4, 'à®à®¨à¯à®¤à¯': 5, 'à®†à®±à¯': 6, 'à®à®´à¯': 7, 'à®Žà®Ÿà¯à®Ÿà¯': 8, 'à®’à®©à¯à®ªà®¤à¯': 9,
            // Gujarati
            'àª¶à«‚àª¨à«àª¯': 0, 'àªàª•': 1, 'àª¬à«‡': 2, 'àª¤à«àª°àª£': 3, 'àªšàª¾àª°': 4, 'àªªàª¾àª‚àªš': 5, 'àª›': 6, 'àª¸àª¾àª¤': 7, 'àª†àª ': 8, 'àª¨àªµ': 9,
            // Kannada
            'à²¸à³Šà²¨à³à²¨à³†': 0, 'à²’à²‚à²¦à³': 1, 'à²Žà²°à²¡à³': 2, 'à²®à³‚à²°à³': 3, 'à²¨à²¾à²²à³à²•à³': 4, 'à²à²¦à³': 5, 'à²†à²°à³': 6, 'à²à²³à³': 7, 'à²Žà²‚à²Ÿà³': 8, 'à²’à²‚à²¬à²¤à³à²¤à³': 9,
            // Malayalam
            'à´ªàµ‚à´œàµà´¯à´‚': 0, 'à´’à´¨àµà´¨àµ': 1, 'à´°à´£àµà´Ÿàµ': 2, 'à´®àµ‚à´¨àµà´¨àµ': 3, 'à´¨à´¾à´²àµ': 4, 'à´…à´žàµà´šàµ': 5, 'à´†à´±àµ': 6, 'à´à´´àµ': 7, 'à´Žà´Ÿàµà´Ÿàµ': 8, 'à´’àµ»à´ªà´¤àµ': 9,
            // Punjabi
            'à¨¸à¨¿à¨«à¨¼à¨°': 0, 'à¨‡à©±à¨•': 1, 'à¨¦à©‹': 2, 'à¨¤à¨¿à©°à¨¨': 3, 'à¨šà¨¾à¨°': 4, 'à¨ªà©°à¨œ': 5, 'à¨›à©‡': 6, 'à¨¸à©±à¨¤': 7, 'à¨…à©±à¨ ': 8, 'à¨¨à©Œà¨‚': 9,
        };
    },

    // Converts spoken number words â†’ digits string
    wordToDigits(text) {
        const wordMap = this.getWordMap();

        // First try raw digit extraction
        const rawDigits = text.replace(/[^0-9]/g, '');
        if (rawDigits.length >= 10) return rawDigits;

        // Try word-by-word conversion
        const words = text.toLowerCase().trim().split(/\s+/);
        let digits = '';
        for (const w of words) {
            const clean = w.replace(/[.,!?à¥¤]/g, '');
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
            const clean = w.replace(/[.,!?à¥¤]/g, '');
            return clean in wordMap ? wordMap[clean] : clean;
        }).join('');
    },

    processAnswer(text) {
        const trimmed = text.trim();
        const retryPrompt = document.getElementById('ai-retry').innerText;

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
            // Convert spoken number words to digits (handles "nine eight seven six..." etc.)
            const allDigits = this.wordToDigits(text);

            if (allDigits.length >= 10) {
                // Take the last 10 digits (handles "my number is 9876543210" etc.)
                const p = allDigits.slice(-10);
                document.getElementById('w-phone').value = p;
                aiStep++;
            } else {
                // Show what was heard so user can understand the issue
                const tBox = document.getElementById('ai-transcript');
                if (tBox) tBox.innerText = `Heard: "${text}" â€” Please say all 10 digits clearly.`;
                this.speak(retryPrompt, () => { this.listenForAnswer(); });
                return;
            }
        }
        else if (aiStep === 4) {
            // Password step removed for security and accessibility
            aiStep++;
        }

        setTimeout(() => { this.askNextQuestion(); }, 1500);
    },
    capitalize(str) {
        if (!str) return '';
        return str.charAt(0).toUpperCase() + str.slice(1);
    },

    // Needed by handleWorkerSignup() to convert text address → lat/lon
    async geocodeAddress(address) {
        try {
            const res = await fetch(
                `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(address)}`
            );
            const data = await res.json();
            if (data && data.length > 0) {
                return { lat: data[0].lat, lon: data[0].lon };
            }
        } catch (e) {
            console.error('Geocoding error:', e);
        }
        return null;
    },
};

// Auto-init on every page that loads this script
document.addEventListener('DOMContentLoaded', () => {
    app.init();
});
