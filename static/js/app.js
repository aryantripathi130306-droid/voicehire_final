const getMediaUrl = (path) => {
    if (!path) return null;
    if (path.startsWith('http://') || path.startsWith('https://')) return path;
    return `/static/${path}`;
};

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
                if (tBox) tBox.innerText = `Heard: "${text}" — Please say all 10 digits clearly.`;
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
                card.className = 'glass-panel rounded-xl p-6 shadow-sm border border-slate-200 flex flex-col gap-4';

                const dateStr = new Date(j.created_at).toLocaleDateString();

                const topDiv = document.createElement('div');
                topDiv.className = 'flex justify-between items-start';

                const infoDiv = document.createElement('div');
                const title = document.createElement('h4');
                title.className = 'font-bold text-lg text-primary';
                title.textContent = `Need: ${j.service_type}`;

                const desc = document.createElement('p');
                desc.className = 'text-slate-600 mt-1';
                desc.textContent = `"${j.description}"`;

                const loc = document.createElement('p');
                loc.className = 'text-xs text-slate-500 mt-1';
                loc.textContent = `📍 ${j.location || 'Unknown'}`;

                infoDiv.appendChild(title);
                infoDiv.appendChild(desc);
                infoDiv.appendChild(loc);

                const dateBadge = document.createElement('span');
                dateBadge.className = 'bg-blue-100 text-blue-700 text-[10px] font-bold px-2 py-1 rounded-full uppercase tracking-widest';
                dateBadge.textContent = dateStr;

                topDiv.appendChild(infoDiv);
                topDiv.appendChild(dateBadge);

                const bottomDiv = document.createElement('div');
                bottomDiv.className = 'flex items-center justify-between mt-2 pt-4 border-t border-slate-100';

                const userDiv = document.createElement('div');
                userDiv.className = 'flex items-center gap-2';
                userDiv.innerHTML = `
                    <div class="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-500 overflow-hidden">
                        ${j.user_profile_pic ? `<img src="${getMediaUrl(j.user_profile_pic)}" class="w-full h-full object-cover">` : `<span class="material-symbols-outlined text-sm">person</span>`}
                    </div>`;
                const userName = document.createElement('span');
                userName.className = 'text-sm font-medium text-slate-700';
                userName.textContent = j.user_name;
                userDiv.appendChild(userName);

                const actionsDiv = document.createElement('div');
                actionsDiv.className = 'flex gap-2';

                const callBtn = document.createElement('a');
                callBtn.href = `tel:${j.user_phone}`;
                callBtn.className = 'flex items-center gap-2 bg-slate-200 text-slate-800 px-4 py-2 rounded-lg text-sm font-bold hover:opacity-90 transition-all';
                callBtn.innerHTML = `<span class="material-symbols-outlined text-sm">call</span>Call`;

                actionsDiv.appendChild(callBtn);

                if (j.status === 'open') {
                    const acceptBtn = document.createElement('button');
                    acceptBtn.className = 'flex items-center gap-2 bg-primary text-white px-4 py-2 rounded-lg text-sm font-bold hover:opacity-90 transition-all';
                    acceptBtn.innerHTML = `<span class="material-symbols-outlined text-sm">check</span>Accept`;
                    acceptBtn.onclick = () => this.acceptJob(j.id, workType);
                    actionsDiv.appendChild(acceptBtn);
                } else {
                    const statusBadge = document.createElement('span');
                    statusBadge.className = 'flex items-center gap-2 bg-green-100 text-green-800 px-4 py-2 rounded-lg text-sm font-bold';
                    statusBadge.textContent = 'Accepted';
                    actionsDiv.appendChild(statusBadge);
                }

                bottomDiv.appendChild(userDiv);
                bottomDiv.appendChild(actionsDiv);

                card.appendChild(topDiv);
                card.appendChild(bottomDiv);
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
                card.className = 'glass-panel rounded-xl p-6 shadow-sm border border-slate-200 flex flex-col gap-3';

                const title = document.createElement('h4');
                title.className = 'font-bold text-lg text-primary';
                title.textContent = j.service_type;

                const statusBadge = document.createElement('span');
                statusBadge.className = `text-xs font-bold px-2 py-1 rounded-full uppercase tracking-widest self-start ${j.status === 'open' ? 'bg-yellow-100 text-yellow-800' : j.status === 'accepted' ? 'bg-blue-100 text-blue-800' : 'bg-green-100 text-green-800'}`;
                statusBadge.textContent = j.status;

                card.appendChild(statusBadge);
                card.appendChild(title);

                if (j.worker_name) {
                    const workerInfo = document.createElement('div');
                    workerInfo.className = 'text-sm text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-100';
                    workerInfo.textContent = `Worker: ${j.worker_name} (${j.worker_phone})`;
                    card.appendChild(workerInfo);
                }

                const actions = document.createElement('div');
                actions.className = 'flex gap-2 mt-2';

                if (j.status === 'accepted') {
                    const completeBtn = document.createElement('button');
                    completeBtn.className = 'bg-green-500 text-white px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2';
                    completeBtn.innerHTML = `<span class="material-symbols-outlined text-sm">qr_code_2</span> Complete`;
                    completeBtn.onclick = () => this.showCompletionQR(j.completion_token);
                    actions.appendChild(completeBtn);

                    const trackBtn = document.createElement('button');
                    trackBtn.className = 'bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2';
                    trackBtn.innerHTML = `<span class="material-symbols-outlined text-sm">location_on</span> Track`;
                    trackBtn.onclick = () => this.trackWorker(j.id);
                    actions.appendChild(trackBtn);
                } else if (j.status === 'completed') {
                    const reviewBtn = document.createElement('button');
                    reviewBtn.className = 'bg-primary text-white px-4 py-2 rounded-lg text-sm font-bold';
                    reviewBtn.textContent = 'Leave a Review';
                    reviewBtn.onclick = () => this.showReviewModal(j.id, j.worker_id);
                    actions.appendChild(reviewBtn);
                }

                if (actions.children.length > 0) {
                    card.appendChild(actions);
                }
                listDiv.appendChild(card);
            });
        } catch (e) {
            listDiv.innerHTML = `<div class="text-red-400 italic">Error loading jobs.</div>`;
        }
    },

    async acceptJob(jobId, workType) {
        try {
            const res = await fetch(`/api/jobs/${jobId}/accept`, { method: 'POST' });
            if (res.ok) {
                alert("Job accepted! The user will be notified.");
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
                <a href="/bookings/${b.id}" class="glass-panel p-4 rounded-2xl border border-slate-100 flex items-center justify-between hover:border-secondary/30 transition-all">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-full bg-secondary/10 flex items-center justify-center text-secondary overflow-hidden">
                            ${(isWorker ? b.customer_profile_pic : b.worker_profile_pic) 
                                ? `<img src="${getMediaUrl(isWorker ? b.customer_profile_pic : b.worker_profile_pic)}" class="w-full h-full object-cover">` 
                                : `<span class="material-symbols-outlined text-xl">calendar_month</span>`}
                        </div>
                        <div>
                            <p class="font-black text-slate-800 text-sm">${isWorker ? b.customer_name : b.worker_name}</p>
                            <p class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">${b.date} • ${b.time_slot}</p>
                        </div>
                    </div>
                    <span class="px-2 py-1 rounded-full text-[9px] font-black uppercase tracking-tighter ${b.status === 'Work Started' ? 'bg-green-100 text-green-700' : 'bg-blue-50 text-blue-600'}">
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
                <div class="glass-panel p-6 rounded-[24px] border border-amber-100/50 hover:shadow-xl hover:shadow-amber-500/5 transition-all space-y-4 bg-white">
                    <div class="flex items-center gap-4">
                        <div class="w-12 h-12 rounded-2xl bg-amber-50 flex items-center justify-center text-amber-600 border border-amber-100 shadow-sm overflow-hidden">
                            ${b.customer_profile_pic 
                                ? `<img src="${getMediaUrl(b.customer_profile_pic)}" class="w-full h-full object-cover">` 
                                : `<span class="material-symbols-outlined" style="font-variation-settings:'FILL' 1">person</span>`}
                        </div>
                        <div class="flex-1 min-w-0">
                            <p class="font-black text-slate-900 truncate">${b.customer_name}</p>
                            <p class="text-[10px] text-slate-500 font-bold uppercase tracking-widest">${b.date} • ${b.time_slot}</p>
                        </div>
                    </div>
                    
                    <div class="flex gap-2">
                        <button onclick="app.acceptBookingDirectly(${b.id})" 
                            class="flex-1 h-11 bg-amber-600 text-white rounded-xl text-[10px] font-black uppercase tracking-widest shadow-lg shadow-amber-600/20 hover:bg-amber-700 transition-all active:scale-95">
                            Accept Now
                        </button>
                        <button onclick="location.href='/bookings/${b.id}'" 
                            class="flex-1 h-11 bg-slate-50 text-slate-500 rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-slate-100 transition-all border border-slate-100">
                            Details
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
                card.className = 'glass-panel rounded-xl p-6 shadow-sm border border-slate-200 flex flex-col gap-4 hover:shadow-md transition-all';

                const headerDiv = document.createElement('div');
                headerDiv.className = 'flex justify-between items-start';

                const infoWrapper = document.createElement('div');
                infoWrapper.className = 'flex items-center gap-4';
                infoWrapper.innerHTML = `
                    <div class="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 overflow-hidden">
                        ${w.profile_pic ? `<img src="${getMediaUrl(w.profile_pic)}" class="w-full h-full object-cover">` : `<span class="material-symbols-outlined text-3xl">person</span>`}
                    </div>
                `;

                const textDiv = document.createElement('div');
                const nameLabel = document.createElement('h4');
                nameLabel.className = 'font-bold text-lg text-primary flex items-center gap-1';
                nameLabel.innerHTML = `
                    ${w.name}
                    ${w.is_verified ? '<span class="material-symbols-outlined text-green-600 text-[20px]" title="Verified">verified</span>' : ''}
                `;
                textDiv.appendChild(nameLabel);

                if (w.review_count > 0) {
                    const ratingSpan = document.createElement('div');
                    ratingSpan.className = 'text-sm mb-1 flex items-center gap-1';

                    const avg = parseFloat(w.avg_rating);
                    const stars = '★'.repeat(Math.round(avg)) + '☆'.repeat(5 - Math.round(avg));

                    ratingSpan.innerHTML = `
                        <span class="text-yellow-500 font-bold">${stars}</span>
                        <span class="text-slate-600 font-medium">${avg.toFixed(1)}</span>
                        <span class="text-slate-400 text-xs">(${w.review_count} reviews)</span>
                    `;
                    textDiv.appendChild(ratingSpan);
                } else {
                    const noRating = document.createElement('div');
                    noRating.className = 'text-xs text-slate-400 italic mb-1';
                    noRating.textContent = 'No reviews yet';
                    textDiv.appendChild(noRating);
                }

                const tagsDiv = document.createElement('div');
                tagsDiv.className = 'flex flex-wrap items-center gap-3 mt-1';

                const workTag = document.createElement('span');
                workTag.className = 'flex items-center gap-1 text-xs font-bold text-secondary uppercase tracking-wider';
                workTag.innerHTML = `<span class="material-symbols-outlined text-[14px]">work</span>`;
                workTag.appendChild(document.createTextNode(w.work));

                const locTag = document.createElement('span');
                locTag.className = 'flex items-center gap-1 text-xs font-medium text-slate-500';
                locTag.innerHTML = `<span class="material-symbols-outlined text-[14px]">location_on</span>`;
                locTag.appendChild(document.createTextNode(w.location));

                tagsDiv.appendChild(workTag);
                tagsDiv.appendChild(locTag);
                textDiv.appendChild(tagsDiv);

                infoWrapper.appendChild(textDiv);

                const actionsWrapper = document.createElement('div');
                actionsWrapper.className = 'flex items-center gap-2';

                const waBtn = document.createElement('a');
                waBtn.href = `https://wa.me/91${w.phone}`;
                waBtn.target = '_blank';
                waBtn.className = 'w-10 h-10 bg-green-500 text-white rounded-full flex items-center justify-center hover:opacity-90 active:scale-95 transition-all shadow-sm';
                waBtn.innerHTML = `<img src="https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg" class="w-5 h-5 filter brightness-0 invert" alt="WA">`;

                const callBtn = document.createElement('a');
                callBtn.href = `tel:${w.phone}`;
                callBtn.className = 'w-10 h-10 bg-primary text-white rounded-full flex items-center justify-center hover:opacity-90 active:scale-95 transition-all shadow-sm';
                callBtn.innerHTML = `<span class="material-symbols-outlined">call</span>`;

                actionsWrapper.appendChild(waBtn);
                actionsWrapper.appendChild(callBtn);

                headerDiv.appendChild(infoWrapper);
                headerDiv.appendChild(actionsWrapper);
                card.appendChild(headerDiv);

                const portfolioBtn = document.createElement('a');
                portfolioBtn.href = `/book/${w.id}#portfolio`;
                portfolioBtn.className = 'mt-2 h-12 bg-white text-secondary border border-secondary/20 rounded-xl flex items-center justify-center gap-2 font-black text-sm hover:bg-secondary/5 active:scale-95 transition-all';
                portfolioBtn.innerHTML = `<span class="material-symbols-outlined text-base">person_outline</span> View Portfolio`;
                card.appendChild(portfolioBtn);

                const bookBtn = document.createElement('a');
                bookBtn.href = `/book/${w.id}`;
                bookBtn.className = 'mt-2 h-12 bg-primary text-white rounded-xl flex items-center justify-center gap-2 font-black text-sm hover:opacity-90 active:scale-95 transition-all shadow-lg shadow-primary/10';
                bookBtn.innerHTML = `<span class="material-symbols-outlined text-base">calendar_month</span> Book Now`;
                card.appendChild(bookBtn);

                if (w.voice_resume) {
                    const vrDiv = document.createElement('div');
                    vrDiv.className = 'mt-3 p-3 bg-blue-50 rounded-xl border border-blue-100 italic text-sm text-slate-700';
                    vrDiv.innerHTML = `<span class="material-symbols-outlined text-xs align-middle mr-1">voice_chat</span> "${w.voice_resume}"`;
                    card.appendChild(vrDiv);
                }

                if (w.voice_note || w.video) {
                    const mediaDiv = document.createElement('div');
                    mediaDiv.className = 'flex flex-col gap-4 mt-2 pt-4 border-t border-slate-100';

                    if (w.voice_note) {
                        const auDiv = document.createElement('div');
                        auDiv.className = 'flex flex-col gap-2';
                        auDiv.innerHTML = `<span class="flex items-center gap-1 text-xs font-bold text-secondary uppercase tracking-wider"><span class="material-symbols-outlined text-sm">mic</span> Voice Note</span>`;
                        const audio = document.createElement('audio');
                        audio.controls = true;
                        audio.className = 'w-full';
                        audio.src = `${getMediaUrl(w.voice_note)}`;
                        auDiv.appendChild(audio);
                        mediaDiv.appendChild(auDiv);
                    }
                    if (w.video) {
                        const vidDiv = document.createElement('div');
                        vidDiv.className = 'flex flex-col gap-2';
                        vidDiv.innerHTML = `<span class="flex items-center gap-1 text-xs font-bold text-secondary uppercase tracking-wider"><span class="material-symbols-outlined text-sm">videocam</span> Video Portfolio</span>`;
                        const video = document.createElement('video');
                        video.controls = true;
                        video.className = 'w-full rounded-xl border border-slate-200 shadow-sm max-h-64';
                        video.src = `${getMediaUrl(w.video)}`;
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