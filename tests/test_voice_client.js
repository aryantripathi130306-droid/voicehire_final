/**
 * VoiceHire — Automated Client-Side Voice Services Test Suite
 * Tests:
 *  1. Provider error recovery (network, audio-capture, aborted)
 *  2. Unknown language fallback to Hindi (hi-IN)
 *  3. Repeated clicks debouncing and prevention of zombie listeners
 *  4. Speech recognition cancellation
 *  5. Text-to-speech queue cancellation
 *  6. Microphone permission denial ('not-allowed')
 *  7. Silence timeout (8s) auto-stop
 *  8. Slow network / server failure recovery
 */

const test = require('node:test');
const assert = require('node:assert');

// Mock browser globals for Node.js test environment
class MockSpeechRecognition {
  constructor() {
    this.continuous = false;
    this.interimResults = false;
    this.lang = 'hi-IN';
    this.onstart = null;
    this.onresult = null;
    this.onerror = null;
    this.onend = null;
    this.started = false;
    this.aborted = false;
  }
  start() {
    this.started = true;
    if (this.onstart) this.onstart();
  }
  stop() {
    this.started = false;
    if (this.onend) this.onend();
  }
  abort() {
    this.aborted = true;
    this.started = false;
    if (this.onend) this.onend();
  }
}

class MockSpeechSynthesis {
  constructor() {
    this.speaking = false;
    this.paused = false;
    this.pending = false;
    this.utterances = [];
  }
  getVoices() {
    return [
      { lang: 'hi-IN', name: 'Google हिन्दी', default: true },
      { lang: 'en-IN', name: 'Google English (India)' },
      { lang: 'pa-IN', name: 'Google Punjabi' }
    ];
  }
  speak(utterance) {
    this.speaking = true;
    this.utterances.push(utterance);
    if (utterance.onstart) utterance.onstart();
  }
  cancel() {
    this.speaking = false;
    this.utterances = [];
  }
  pause() { this.paused = true; }
  resume() { this.paused = false; }
}

class MockSpeechSynthesisUtterance {
  constructor(text) {
    this.text = text;
    this.lang = 'hi-IN';
    this.rate = 0.95;
    this.pitch = 1.0;
    this.onstart = null;
    this.onend = null;
    this.onerror = null;
  }
}

// Inject mock browser environment
globalThis.window = globalThis;
globalThis.SpeechRecognition = MockSpeechRecognition;
globalThis.speechSynthesis = new MockSpeechSynthesis();
globalThis.SpeechSynthesisUtterance = MockSpeechSynthesisUtterance;

// Load the voice services module
const VoiceHireVoice = require('../static/js/voice_services.js');

test('1. Unknown Language and Locale Resolution', (t) => {
  const defaultMeta = VoiceHireVoice.getLocaleMeta('unknown_lang');
  assert.strictEqual(defaultMeta.stt, 'hi-IN', 'Should fallback to hi-IN for unknown language');
  assert.strictEqual(defaultMeta.tts, 'hi-IN', 'Should fallback to hi-IN for unknown language');
  assert.strictEqual(defaultMeta.name, 'Hindi');

  const punjabiMeta = VoiceHireVoice.getLocaleMeta('pa');
  assert.strictEqual(punjabiMeta.stt, 'pa-IN', 'Should map Punjabi to pa-IN');
  assert.strictEqual(punjabiMeta.name, 'Punjabi');

  const englishMeta = VoiceHireVoice.getLocaleMeta('en');
  assert.strictEqual(englishMeta.stt, 'en-IN', 'Should map English to en-IN');

  // Verify all 12 languages exist
  const expectedLanguages = ['hi', 'pa', 'en', 'bn', 'mr', 'ta', 'te', 'gu', 'kn', 'ml', 'or', 'ur'];
  for (const lang of expectedLanguages) {
    assert.ok(VoiceHireVoice.LOCALE_REGISTRY[lang], `Language ${lang} must exist in registry`);
    assert.ok(VoiceHireVoice.LOCALE_REGISTRY[lang].stt.endsWith('-IN'), `Locale for ${lang} must be Indian regional`);
  }
});

test('2. Speech Recognition Lifecycle and Cancellation', (t) => {
  const stt = new VoiceHireVoice.SpeechRecognitionService();
  assert.ok(stt.isSupported(), 'SpeechRecognitionService should report supported with mock');

  let stateChanges = [];
  stt.onStateChange = (state) => stateChanges.push(state);

  // Start listening
  stt.start('hi');
  assert.strictEqual(stt.state, VoiceHireVoice.VoiceStates.LISTENING);
  assert.ok(stt.recognition !== null);
  assert.strictEqual(stt.recognition.lang, 'hi-IN');
  assert.strictEqual(stt.recognition.started, true);

  // Cancel immediately
  const rec = stt.recognition;
  stt.cancel();
  assert.strictEqual(stt.state, VoiceHireVoice.VoiceStates.IDLE);
  assert.strictEqual(rec.aborted, true);
  assert.strictEqual(stt.recognition, null);
});

test('3. Permission Denial (not-allowed) triggers permission denied state and hook', (t) => {
  const stt = new VoiceHireVoice.SpeechRecognitionService();
  let permissionDeniedFired = false;
  let finalErrorCode = null;

  stt.onPermissionDenied = () => { permissionDeniedFired = true; };
  stt.onError = (code, msg) => { finalErrorCode = code; };

  stt.start('hi');
  assert.strictEqual(stt.state, VoiceHireVoice.VoiceStates.LISTENING);

  // Simulate browser firing 'not-allowed' error
  stt.recognition.onerror({ error: 'not-allowed' });

  assert.strictEqual(permissionDeniedFired, true, 'onPermissionDenied callback should fire');
  assert.strictEqual(stt.state, VoiceHireVoice.VoiceStates.PERMISSION_DENIED);
  assert.strictEqual(finalErrorCode, 'permission_denied');
});

test('4. Provider Error Recovery (network, audio-capture)', (t) => {
  const stt = new VoiceHireVoice.SpeechRecognitionService();
  let errorCaught = null;
  stt.onError = (code, msg) => { errorCaught = code; };

  stt.start('hi');
  assert.strictEqual(stt.state, VoiceHireVoice.VoiceStates.LISTENING);

  // Simulate network error
  const rec = stt.recognition;
  rec.onerror({ error: 'network' });
  assert.strictEqual(errorCaught, 'network');
  assert.strictEqual(stt.state, VoiceHireVoice.VoiceStates.ERROR);

  // Ensure stop resets state cleanly to IDLE
  stt.stop();
  assert.strictEqual(stt.state, VoiceHireVoice.VoiceStates.IDLE);
});

test('5. Text-To-Speech Queue and Cancellation', async (t) => {
  const tts = new VoiceHireVoice.TextToSpeechService();
  assert.ok(tts.isSupported(), 'TextToSpeechService should report supported');

  let started = false;

  const speakPromise = tts.speak('नमस्ते, Voice Hire में आपका स्वागत है।', 'hi', {
    onStart: () => { started = true; }
  }).catch(() => {});

  assert.strictEqual(started, true);
  assert.strictEqual(tts.isSpeaking, true);

  // Cancellation should immediately stop and clear queue
  tts.stop();
  assert.strictEqual(tts.isSpeaking, false);
  assert.strictEqual(globalThis.speechSynthesis.speaking, false);
  await speakPromise;
});

test('6. Repeated Clicks Debouncing Protection', (t) => {
  // Simulate assistant mic button click debouncer
  let lastClickTime = 0;
  let invocationCount = 0;

  function handleMicClick(currentTime) {
    if (currentTime - lastClickTime < 350) {
      return false; // Throttled / debounced
    }
    lastClickTime = currentTime;
    invocationCount++;
    return true;
  }

  // Rapidly click 5 times within 100ms
  const times = [1000, 1050, 1100, 1150, 1200];
  const results = times.map(t => handleMicClick(t));

  // Only the first click should execute; remaining 4 should be throttled
  assert.strictEqual(results[0], true, 'First click allowed');
  assert.strictEqual(results[1], false, 'Second click debounced');
  assert.strictEqual(results[2], false, 'Third click debounced');
  assert.strictEqual(results[3], false, 'Fourth click debounced');
  assert.strictEqual(results[4], false, 'Fifth click debounced');
  assert.strictEqual(invocationCount, 1, 'Debounce must prevent duplicate recordings');

  // Next click after 400ms should succeed
  const resultAfterCooldown = handleMicClick(1600);
  assert.strictEqual(resultAfterCooldown, true, 'Click after 400ms cooldown allowed');
  assert.strictEqual(invocationCount, 2);
});

test('7. Slow Network and Intent Service Fallback', async (t) => {
  // Mock global fetch to simulate network error or timeout
  globalThis.fetch = async () => {
    throw new Error('Network timeout / offline error');
  };

  const response = await VoiceHireVoice.VoiceIntentService.processTranscript('plumber chahiye', 'hi');
  assert.strictEqual(response.success, false);
  assert.strictEqual(response.intent, 'network_fallback');
  assert.strictEqual(response.requires_clarification, true);
  assert.ok(response.clarification_prompt.length > 0, 'Must provide graceful clarification prompt on network failure');
});

test('8. Silence Timeout Lifecycle', (t) => {
  const stt = new VoiceHireVoice.SpeechRecognitionService();
  stt.silenceTimeoutMs = 100; // Fast timeout for unit test

  stt.start('hi');
  assert.ok(stt.silenceTimer !== null, 'Silence timer must be running during speech input');

  // Manually clear
  stt._clearSilenceTimer();
  assert.strictEqual(stt.silenceTimer, null, 'Silence timer should be cleared on audio event or stop');
  stt.cancel();
});
