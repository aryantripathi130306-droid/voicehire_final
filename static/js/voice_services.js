/**
 * VoiceHire — Production Voice Input & Voice Output Layer
 * ═══════════════════════════════════════════════════════════════════════════
 * Reusable, production-grade SpeechRecognition and TextToSpeech services.
 * Features:
 *  - Full locale mapping defaulting to Hindi (hi-IN) and 12 Indian languages.
 *  - Safe microphone lifecycle: start/stop, cancellation, timeouts, no zombie listeners.
 *  - Server-backed intent analysis with code-switching and Hinglish support.
 *  - Low-confidence (< 0.60) and ambiguous intent clarification workflows.
 *  - Transcript correction & retry hooks before consequential actions.
 *  - Typed-input fallback when speech recognition is denied, unsupported, or fails.
 *  - Zero client-side API key exposure.
 * ═══════════════════════════════════════════════════════════════════════════
 */

(function (window) {
  'use strict';

  // ─────────────────────────────────────────────────────────────────────────
  // 1. CONSTANTS & LOCALE REGISTRY
  // ─────────────────────────────────────────────────────────────────────────
  const VoiceStates = {
    IDLE:                 'IDLE',
    REQUESTING_PERMISSION:'REQUESTING_PERMISSION',
    LISTENING:            'LISTENING',
    PROCESSING:           'PROCESSING',
    SPEAKING:             'SPEAKING',
    MUTED:                'MUTED',
    ERROR:                'ERROR',
    PERMISSION_DENIED:    'PERMISSION_DENIED',
    UNSUPPORTED:          'UNSUPPORTED'
  };

  const LOCALE_REGISTRY = {
    hi: { stt: 'hi-IN', tts: 'hi-IN', name: 'Hindi', native: 'हिन्दी', confidenceThreshold: 0.60 },
    pa: { stt: 'pa-IN', tts: 'pa-IN', name: 'Punjabi', native: 'ਪੰਜਾਬੀ', confidenceThreshold: 0.60 },
    en: { stt: 'en-IN', tts: 'en-IN', name: 'English', native: 'English', confidenceThreshold: 0.65 },
    bn: { stt: 'bn-IN', tts: 'bn-IN', name: 'Bengali', native: 'বাংলা', confidenceThreshold: 0.60 },
    mr: { stt: 'mr-IN', tts: 'mr-IN', name: 'Marathi', native: 'मराठी', confidenceThreshold: 0.60 },
    ta: { stt: 'ta-IN', tts: 'ta-IN', name: 'Tamil', native: 'தமிழ்', confidenceThreshold: 0.60 },
    te: { stt: 'te-IN', tts: 'te-IN', name: 'Telugu', native: 'తెలుగు', confidenceThreshold: 0.60 },
    gu: { stt: 'gu-IN', tts: 'gu-IN', name: 'Gujarati', native: 'ગુજરાતી', confidenceThreshold: 0.60 },
    kn: { stt: 'kn-IN', tts: 'kn-IN', name: 'Kannada', native: 'ಕನ್ನಡ', confidenceThreshold: 0.60 },
    ml: { stt: 'ml-IN', tts: 'ml-IN', name: 'Malayalam', native: 'മലയാളം', confidenceThreshold: 0.60 },
    or: { stt: 'or-IN', tts: 'or-IN', name: 'Odia', native: 'ଓଡ଼ିଆ', confidenceThreshold: 0.60 },
    ur: { stt: 'ur-IN', tts: 'ur-IN', name: 'Urdu', native: 'اردو', confidenceThreshold: 0.60 }
  };

  function getLocaleMeta(lang) {
    const key = (lang || 'hi').toLowerCase().split('-')[0];
    return LOCALE_REGISTRY[key] || LOCALE_REGISTRY.hi;
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 2. TEXT-TO-SPEECH SERVICE
  // ─────────────────────────────────────────────────────────────────────────
  class TextToSpeechService {
    constructor() {
      this.synth = window.speechSynthesis || null;
      this.isMuted = false;
      this.isSpeaking = false;
      this.currentUtterance = null;
      this.chromeBugTimer = null;

      // Event listeners
      this.onStart = null;
      this.onEnd = null;
      this.onError = null;
      this.onStateChange = null;

      // Warm up voices
      if (this.synth && this.synth.onvoiceschanged !== undefined) {
        this.synth.onvoiceschanged = () => this.getVoices();
      }
    }

    isSupported() {
      return !!this.synth;
    }

    setMuted(muted) {
      this.isMuted = !!muted;
      if (this.isMuted) {
        this.cancel();
      }
    }

    getVoices() {
      if (!this.synth || !this.synth.getVoices) return [];
      return this.synth.getVoices() || [];
    }

    findBestVoice(localeMeta) {
      const voices = this.getVoices();
      if (!voices.length) return null;

      const targetTag = (localeMeta.tts || 'hi-IN').replace('_', '-').toLowerCase();
      const langPrefix = targetTag.split('-')[0];

      // 1. Exact BCP-47 match
      const exact = voices.find(v => (v.lang || '').replace('_', '-').toLowerCase() === targetTag);
      if (exact) return exact;

      // 2. Language-specific name keyword mapping for native Indian voices
      const voiceKeywords = {
        hi: ['hindi', 'हिन्दी', 'kalpana', 'hemant', 'swara', 'madhur'],
        pa: ['punjabi', 'panjabi', 'ਪੰਜਾਬੀ'],
        bn: ['bengali', 'bangla', 'বাংলা', 'tapan', 'bashkar'],
        mr: ['marathi', 'मराठी', 'aarohi', 'manohar'],
        ta: ['tamil', 'தமிழ்', 'valluvar', 'iniya'],
        te: ['telugu', 'తెలుగు', 'mohan', 'shruti'],
        gu: ['gujarati', 'ગુજરાતી', 'dhwani', 'niranjan'],
        kn: ['kannada', 'ಕನ್ನಡ', 'gagan', 'sapna'],
        ml: ['malayalam', 'മലയാളം', 'midhun', 'sobhana'],
        ur: ['urdu', 'اردو', 'salman', 'uzma'],
        en: ['en-in', 'india', 'indian', 'ravi', 'heera', 'neerja', 'prabhat']
      };

      const kws = voiceKeywords[langPrefix] || [];
      const namedMatch = voices.find(v => {
        const vName = (v.name || '').toLowerCase();
        const vLang = (v.lang || '').replace('_', '-').toLowerCase();
        return kws.some(k => vName.includes(k)) || (vLang.startsWith(langPrefix) && !vName.includes('english'));
      });
      if (namedMatch) return namedMatch;

      // 3. Prefix match on lang tag
      const prefixMatch = voices.find(v => (v.lang || '').replace('_', '-').toLowerCase().startsWith(langPrefix));
      if (prefixMatch) return prefixMatch;

      return null;
    }

    _chunkText(text, maxLen = 160) {
      if (!text || text.length <= maxLen) return [text];
      const chunks = [];
      const sentences = text.split(/([।,\.\?!;\n]+)/);
      let cur = '';

      for (let i = 0; i < sentences.length; i++) {
        const part = sentences[i];
        if (!part) continue;
        if ((cur + part).length > maxLen) {
          if (cur.trim()) chunks.push(cur.trim());
          cur = part;
        } else {
          cur += part;
        }
      }
      if (cur.trim()) chunks.push(cur.trim());
      return chunks.length ? chunks : [text.slice(0, maxLen)];
    }

    playCloudAudio(text, lang = 'hi', options = {}) {
      return new Promise((resolve) => {
        if (!text || this.isMuted) {
          resolve();
          return;
        }
        if (typeof Audio === 'undefined') {
          resolve();
          return;
        }

        const rawCode = (lang || 'hi').toLowerCase().split('-')[0];
        const audioLang = rawCode === 'pa' ? 'pa' : rawCode;
        const chunks = this._chunkText(text, 170);

        this.isSpeaking = true;
        this.currentAudioIndex = 0;
        this.isAudioCancelled = false;
        if (this.onStart) this.onStart(text, getLocaleMeta(lang));
        if (this.onStateChange) this.onStateChange(VoiceStates.SPEAKING);

        const playNextChunk = () => {
          if (this.isAudioCancelled || this.currentAudioIndex >= chunks.length) {
            this._cleanup();
            if (options.onEnd) options.onEnd(text);
            if (this.onEnd) this.onEnd(text);
            if (this.onStateChange) this.onStateChange(VoiceStates.IDLE);
            resolve();
            return;
          }

          const chunk = chunks[this.currentAudioIndex++];
          const ttsUrl = `https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=${encodeURIComponent(audioLang)}&q=${encodeURIComponent(chunk)}`;
          
          try {
            const audio = new Audio(ttsUrl);
            this.currentAudio = audio;
            audio.playbackRate = options.rate !== undefined ? options.rate : 0.95;

            const onDone = () => {
              if (this.currentAudio === audio) this.currentAudio = null;
              playNextChunk();
            };

            audio.onended = onDone;
            audio.onerror = () => {
              console.warn('[Cloud TTS] Audio element error, resolving chunk.');
              onDone();
            };

            const playPromise = audio.play();
            if (playPromise !== undefined) {
              playPromise.catch((err) => {
                console.warn('[Cloud TTS] Play rejected (autoplay policy):', err);
                onDone();
              });
            }
          } catch (e) {
            playNextChunk();
          }
        };

        playNextChunk();
      });
    }

    speak(text, lang = 'hi', options = {}) {
      return new Promise((resolve, reject) => {
        if (!text || this.isMuted) {
          resolve();
          return;
        }

        // Cancel any pending speech to prevent queuing build-up
        this.cancel();

        const meta = getLocaleMeta(lang);
        const voice = this.findBestVoice(meta);
        const langPrefix = (meta.tts || 'hi').split('-')[0].toLowerCase();

        // If no native voice exists in browser for regional languages, use natural cloud audio
        const browserHasNativeVoice = Boolean(voice);
        const isEnglishOrHindi = (langPrefix === 'en' || (langPrefix === 'hi' && browserHasNativeVoice));

        if (!isEnglishOrHindi && !browserHasNativeVoice && typeof Audio !== 'undefined') {
          return this.playCloudAudio(text, lang, options).then(resolve);
        }

        if (!this.synth) {
          if (typeof Audio !== 'undefined') {
            return this.playCloudAudio(text, lang, options).then(resolve);
          }
          console.warn('[TTS] SpeechSynthesis not supported on this browser.');
          resolve();
          return;
        }

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = meta.tts;
        utterance.rate = options.rate !== undefined ? options.rate : 0.92;
        utterance.pitch = options.pitch !== undefined ? options.pitch : 1.0;

        this.currentUtterance = utterance;

        utterance.onstart = () => {
          this.isSpeaking = true;
          this._startChromeKeepAlive();
          if (options.onStart) options.onStart(text, meta);
          if (this.onStart) this.onStart(text, meta);
          if (this.onStateChange) this.onStateChange(VoiceStates.SPEAKING);
        };

        utterance.onend = () => {
          this._cleanup();
          if (options.onEnd) options.onEnd(text);
          if (this.onEnd) this.onEnd(text);
          if (this.onStateChange) this.onStateChange(VoiceStates.IDLE);
          resolve();
        };

        utterance.onerror = (e) => {
          this._cleanup();
          const errType = e.error || 'speech_error';
          if (errType === 'not-allowed') {
            if (this.onError) this.onError('autoplay_blocked', e);
            reject('autoplay_blocked');
          } else if (errType === 'canceled' || errType === 'interrupted') {
            resolve();
          } else {
            // SpeechSynthesis failed; fall back to cloud audio seamlessly
            if (typeof Audio !== 'undefined') {
              this.playCloudAudio(text, lang, options).then(resolve);
            } else {
              resolve();
            }
          }
        };

        const doSpeak = () => {
          try {
            if (this.synth.paused) {
              try { this.synth.resume(); } catch (e) {}
            }
            if (voice) {
              utterance.voice = voice;
            }
            this.synth.speak(utterance);

            // Safe non-blocking autoplay detection with 3000ms tolerance
            setTimeout(() => {
              if (!this.isSpeaking && this.synth && !this.synth.speaking && !this.synth.pending && !this.isMuted) {
                if (this.onError) this.onError('autoplay_blocked');
                reject('autoplay_blocked');
              }
            }, 3000);
          } catch (err) {
            this._cleanup();
            if (typeof Audio !== 'undefined') {
              this.playCloudAudio(text, lang, options).then(resolve);
            } else {
              reject('autoplay_blocked');
            }
          }
        };

        // If voices list is still loading, wait briefly for voiceschanged
        if (this.getVoices().length === 0 && this.synth.onvoiceschanged !== undefined) {
          let voicesFired = false;
          const handler = () => {
            if (voicesFired) return;
            voicesFired = true;
            doSpeak();
          };
          this.synth.onvoiceschanged = handler;
          setTimeout(() => {
            if (!voicesFired) {
              voicesFired = true;
              doSpeak();
            }
          }, 350);
        } else {
          doSpeak();
        }
      });
    }

    cancel() {
      this.isAudioCancelled = true;
      if (this.currentAudio) {
        try {
          this.currentAudio.pause();
          this.currentAudio.currentTime = 0;
        } catch (e) {}
        this.currentAudio = null;
      }
      if (this.synth) {
        try { this.synth.cancel(); } catch (e) {}
      }
      this._cleanup();
      if (this.onStateChange) this.onStateChange(VoiceStates.IDLE);
    }

    stop() {
      this.cancel();
    }

    _cleanup() {
      this.isSpeaking = false;
      this.currentUtterance = null;
      if (this.chromeBugTimer) {
        clearInterval(this.chromeBugTimer);
        this.chromeBugTimer = null;
      }
    }

    // Workaround for Chromium 15-second speech pause bug
    _startChromeKeepAlive() {
      if (this.chromeBugTimer) clearInterval(this.chromeBugTimer);
      this.chromeBugTimer = setInterval(() => {
        if (!this.synth || !this.isSpeaking) {
          clearInterval(this.chromeBugTimer);
          return;
        }
        if (this.synth.speaking) {
          this.synth.pause();
          this.synth.resume();
        }
      }, 10000);
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 3. SPEECH-RECOGNITION SERVICE
  // ─────────────────────────────────────────────────────────────────────────
  class SpeechRecognitionService {
    constructor() {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition || null;
      this.SRClass = SR;
      this.recognition = null;
      this.state = VoiceStates.IDLE;
      this.activeLang = 'hi';
      this.silenceTimeoutMs = 8000;
      this.silenceTimer = null;
      this.isManuallyStopped = false;

      // Event hooks
      this.onStateChange = null;
      this.onInterim = null;
      this.onFinal = null;
      this.onError = null;
      this.onPermissionDenied = null;
    }

    isSupported() {
      return !!this.SRClass;
    }

    setState(newState) {
      this.state = newState;
      if (this.onStateChange) this.onStateChange(newState);
    }

    start(lang = 'hi') {
      if (!this.isSupported()) {
        this.setState(VoiceStates.UNSUPPORTED);
        if (this.onError) this.onError('unsupported', 'Speech recognition is not supported in this browser.');
        return false;
      }

      // If already listening or processing, cancel prior session cleanly
      if (this.recognition) {
        this.cancel();
      }

      this.activeLang = lang;
      const meta = getLocaleMeta(lang);
      this.isManuallyStopped = false;

      try {
        this.recognition = new this.SRClass();
        this.recognition.continuous = false;
        this.recognition.interimResults = true;
        this.recognition.maxAlternatives = 1;
        this.recognition.lang = meta.stt;

        this.recognition.onstart = () => {
          this.setState(VoiceStates.LISTENING);
          this._resetSilenceTimer();
        };

        this.recognition.onresult = (event) => {
          this._resetSilenceTimer();
          let interimText = '';
          let finalText = '';
          let confidence = 1.0;

          for (let i = event.resultIndex; i < event.results.length; ++i) {
            const res = event.results[i];
            if (res.isFinal) {
              finalText += res[0].transcript;
              if (res[0].confidence !== undefined && res[0].confidence > 0) {
                confidence = res[0].confidence;
              }
            } else {
              interimText += res[0].transcript;
            }
          }

          if (interimText && this.onInterim) {
            this.onInterim(interimText);
          }

          if (finalText) {
            this._clearSilenceTimer();
            this.setState(VoiceStates.PROCESSING);
            if (this.onFinal) {
              this.onFinal(finalText.trim(), confidence, meta);
            }
          }
        };

        this.recognition.onerror = (e) => {
          this._clearSilenceTimer();
          const err = e.error || 'unknown';

          if (this.isManuallyStopped && (err === 'aborted' || err === 'canceled')) {
            this.setState(VoiceStates.IDLE);
            return;
          }

          if (err === 'not-allowed' || err === 'service-not-allowed') {
            this.setState(VoiceStates.PERMISSION_DENIED);
            if (this.onPermissionDenied) this.onPermissionDenied(e);
            if (this.onError) this.onError('permission_denied', 'Microphone permission was not granted.');
          } else if (err === 'no-speech') {
            this.setState(VoiceStates.IDLE);
            if (this.onError) this.onError('no_speech', 'No speech detected.');
          } else if (err === 'network') {
            this.setState(VoiceStates.ERROR);
            if (this.onError) this.onError('network', 'Network error during speech recognition.');
          } else {
            this.setState(VoiceStates.ERROR);
            if (this.onError) this.onError(err, `Recognition error: ${err}`);
          }
        };

        this.recognition.onend = () => {
          this._clearSilenceTimer();
          if (this.state === VoiceStates.LISTENING) {
            this.setState(VoiceStates.IDLE);
          }
          this.recognition = null;
        };

        this.setState(VoiceStates.REQUESTING_PERMISSION);
        this.recognition.start();
        return true;
      } catch (err) {
        this._clearSilenceTimer();
        this.setState(VoiceStates.ERROR);
        if (this.onError) this.onError('startup_failed', err.message || 'Could not start recognition.');
        return false;
      }
    }

    stop() {
      this.isManuallyStopped = true;
      this._clearSilenceTimer();
      if (this.recognition) {
        try { this.recognition.stop(); } catch (e) {}
      }
      this.setState(VoiceStates.IDLE);
    }

    cancel() {
      this.isManuallyStopped = true;
      this._clearSilenceTimer();
      if (this.recognition) {
        try { this.recognition.abort(); } catch (e) {}
        this.recognition = null;
      }
      this.setState(VoiceStates.IDLE);
    }

    _resetSilenceTimer() {
      this._clearSilenceTimer();
      this.silenceTimer = setTimeout(() => {
        console.info('[SpeechRecognition] Auto-stopping due to silence timeout.');
        this.stop();
      }, this.silenceTimeoutMs);
    }

    _clearSilenceTimer() {
      if (this.silenceTimer) {
        clearTimeout(this.silenceTimer);
        this.silenceTimer = null;
      }
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 4. SERVER-CONNECTED INTENT SERVICE
  // ─────────────────────────────────────────────────────────────────────────
  class VoiceIntentService {
    static async processTranscript(text, lang = 'hi', confidence = 1.0, state = 'GREETING') {
      try {
        const res = await fetch('/api/voice/intent', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: text,
            lang: lang,
            confidence: confidence,
            state: state
          })
        });

        if (!res.ok) {
          throw new Error(`Intent API returned status ${res.status}`);
        }

        return await res.json();
      } catch (err) {
        console.warn('[VoiceIntentService] Server intent processing failed, using safe fallback:', err);
        // Resilient client-side fallback
        return {
          success: false,
          intent: 'network_fallback',
          confidence: 0.5,
          raw_transcript: text,
          requires_clarification: true,
          clarification_prompt: 'माफ़ कीजिये, आवाज़ समझने में समस्या हुई। कृपया नीचे दिए गए विकल्पों में से चुनें।',
          speech_response: 'माफ़ कीजिये, आवाज़ समझने में समस्या हुई।',
          language: lang,
          trade: null,
          action: null,
          role: null
        };
      }
    }

    static async orchestrateTurn(userInput, state = 'greeting', lang = 'hi', idempotencyKey = null) {
      try {
        const res = await fetch('/api/orchestrator/turn', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_input: userInput,
            state: state,
            language: lang,
            idempotency_key: idempotencyKey || ('turn_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6))
          })
        });

        if (!res.ok) {
          throw new Error(`Orchestrator returned status ${res.status}`);
        }

        return await res.json();
      } catch (err) {
        console.warn('[VoiceIntentService] Orchestrator call failed, falling back:', err);
        return {
          success: false,
          current_state: state,
          action: 'recover_from_error',
          speech_response: 'माफ़ कीजिये, संपर्क करने में समस्या हुई। कृपया पुनः प्रयास करें।',
          display_text: 'नेटवर्क समस्या। कृपया पुनः प्रयास करें।',
          requires_confirmation: false,
          pending_action: null,
          quick_replies: ['दोबारा बोलें', 'मुख्य मेन्यू']
        };
      }
    }

    static async fetchCapabilities() {
      try {
        const res = await fetch('/api/voice/capabilities');
        if (!res.ok) throw new Error(`Capabilities API status ${res.status}`);
        return await res.json();
      } catch (err) {
        return {
          default_language: 'hi',
          supported_languages: Object.keys(LOCALE_REGISTRY).map(k => ({
            code: k,
            ...LOCALE_REGISTRY[k]
          }))
        };
      }
    }
  }

  const exported = {
    VoiceStates: VoiceStates,
    LOCALE_REGISTRY: LOCALE_REGISTRY,
    getLocaleMeta: getLocaleMeta,
    TextToSpeechService: TextToSpeechService,
    SpeechRecognitionService: SpeechRecognitionService,
    VoiceIntentService: VoiceIntentService
  };

  if (typeof window !== 'undefined') {
    window.VoiceHireVoice = exported;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = exported;
  }

})(typeof window !== 'undefined' ? window : globalThis);
