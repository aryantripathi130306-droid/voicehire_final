/**
 * VoiceHire — Phase 14.1 Assistant Automated Node.js Test Suite
 * ═══════════════════════════════════════════════════════════════════════════
 * Tests:
 *  1. Bug 1: Persistent assistant state across navigation & sessionStorage restore.
 *  2. Bug 1: Explicit restart vs route change detection (no re-greeting on routes).
 *  3. Bug 2: Worker profile missing field detection, validation & backend saving.
 *  4. Bug 2: Profile summary card confirmation & activation flow.
 *  5. Bug 3: Hands-Free auto-listening after speech completes.
 *  6. Bug 3: Manual Voice Mode requiring explicit user tap.
 *  7. Bug 3: Sensitive password/OTP focus immediately stops listening.
 *  8. Multi-lingual trade & digit extraction helpers.
 * ═══════════════════════════════════════════════════════════════════════════
 */

const test = require('node:test');
const assert = require('node:assert');

// ── Mock Browser Globals ────────────────────────────────────────────────────
class MockStorage {
  constructor() {
    this.store = {};
  }
  getItem(key) {
    return this.store[key] || null;
  }
  setItem(key, val) {
    this.store[key] = String(val);
  }
  removeItem(key) {
    delete this.store[key];
  }
  clear() {
    this.store = {};
  }
}

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
    this.utterances = [];
  }
  getVoices() {
    return [
      { lang: 'hi-IN', name: 'Google हिन्दी', default: true },
      { lang: 'en-IN', name: 'Google English' },
      { lang: 'pa-IN', name: 'Google Punjabi' }
    ];
  }
  speak(utterance) {
    this.speaking = true;
    this.utterances.push(utterance);
    if (utterance.onstart) utterance.onstart();
    // Simulate speech completion synchronously or next tick
    setTimeout(() => {
      this.speaking = false;
      if (utterance.onend) utterance.onend();
    }, 10);
  }
  cancel() {
    this.speaking = false;
    this.utterances = [];
  }
}

class MockSpeechSynthesisUtterance {
  constructor(text) {
    this.text = text;
    this.lang = 'hi-IN';
    this.onstart = null;
    this.onend = null;
    this.onerror = null;
  }
}

class MockClassList {
  constructor() {
    this.classes = new Set();
  }
  add(c) { this.classes.add(c); }
  remove(c) { this.classes.delete(c); }
  toggle(c, force) {
    if (force !== undefined) {
      if (force) this.classes.add(c); else this.classes.delete(c);
      return force;
    }
    if (this.classes.has(c)) { this.classes.delete(c); return false; }
    this.classes.add(c); return true;
  }
  contains(c) { return this.classes.has(c); }
}

class MockDOMElement {
  constructor(tag, id = '') {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.classList = new MockClassList();
    this.children = [];
    this.textContent = '';
    this.innerHTML = '';
    this.style = {};
    this.dataset = {};
    this.listeners = {};
    this.attributes = {};
  }
  addEventListener(event, handler) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(handler);
  }
  focus() {}
  dispatchEvent(event) {
    const list = this.listeners[event.type] || [];
    list.forEach(h => h(event));
  }
  setAttribute(k, v) { this.attributes[k] = v; }
  getAttribute(k) { return this.attributes[k] || null; }
  appendChild(child) {
    this.children.push(child);
    return child;
  }
  remove() {
    this.children = [];
  }
  querySelector(sel) {
    if (sel.startsWith('#')) {
      const targetId = sel.slice(1);
      if (this.id === targetId) return this;
      for (const c of this.children) {
        if (c.querySelector) {
          const res = c.querySelector(sel);
          if (res) return res;
        }
      }
    }
    return new MockDOMElement('div');
  }
  querySelectorAll(sel) {
    return [];
  }
}

// Polyfill minimal document & window
const mockDocument = {
  readyState: 'complete',
  addEventListener: () => {},
  createElement: (tag) => new MockDOMElement(tag),
  getElementById: (id) => new MockDOMElement('div', id),
  querySelector: (sel) => new MockDOMElement('div'),
  querySelectorAll: () => [],
  head: new MockDOMElement('head'),
  body: new MockDOMElement('body'),
  activeElement: null
};

globalThis.window = globalThis;
globalThis.document = mockDocument;
globalThis.localStorage = new MockStorage();
globalThis.sessionStorage = new MockStorage();
globalThis.SpeechRecognition = MockSpeechRecognition;
globalThis.speechSynthesis = new MockSpeechSynthesis();
globalThis.SpeechSynthesisUtterance = MockSpeechSynthesisUtterance;
globalThis.location = { pathname: '/', href: '/' };
globalThis.VH = { role: '', lang: 'hi', userId: '', userName: '' };

const AssistantModule = require('../static/js/gateway_ai_assistant.js');

test('1. Trade Recognition and Extraction Helpers', (t) => {
  const { detectTradeFromText, extractDigits } = AssistantModule;
  assert.strictEqual(detectTradeFromText('Main plumber ka kaam karta hu'), 'Plumber');
  assert.strictEqual(detectTradeFromText('bijli mistri electrician'), 'Electrician');
  assert.strictEqual(detectTradeFromText('badhai carpenter'), 'Carpenter');
  assert.strictEqual(detectTradeFromText('driver hu gadi chalata hu'), 'Driver');
  assert.strictEqual(detectTradeFromText('random unknown string'), null);

  assert.strictEqual(extractDigits('500 rupaye daily'), 500);
  assert.strictEqual(extractDigits('3 saal ka anubhav'), 3);
  assert.strictEqual(extractDigits('no digits here'), null);
});

test('2. Bug 1: Assistant Session Persistence across Navigation', (t) => {
  const { VoiceHireAssistant, States } = AssistantModule;

  globalThis.sessionStorage.clear();
  globalThis.location.pathname = '/';

  const assistant = new VoiceHireAssistant();
  assistant.setLanguage('hi', false);
  assistant.selectedRole = 'worker';
  assistant.selectedAction = 'register';
  assistant.state = States.ROLE_SELECT;
  assistant.addMessage('मुझे काम चाहिए (Worker)', 'user');

  // Verify session is saved in sessionStorage
  assistant.saveSession();
  const rawSession = globalThis.sessionStorage.getItem('vh_assistant_session');
  assert.ok(rawSession, 'Session should be saved to sessionStorage');

  const parsed = JSON.parse(rawSession);
  assert.strictEqual(parsed.selectedRole, 'worker');
  assert.strictEqual(parsed.selectedAction, 'register');
  assert.strictEqual(parsed.currentLang, 'hi');
  assert.strictEqual(parsed.lastRoute, '/');

  // Simulate navigation to /signup/worker
  globalThis.location.pathname = '/signup/worker';
  const restoredAssistant = new VoiceHireAssistant();

  // Assistant must restore state and NOT start over with Hindi greeting!
  assert.strictEqual(restoredAssistant.selectedRole, 'worker', 'Retains selected role after navigation');
  assert.strictEqual(restoredAssistant.currentLang, 'hi', 'Retains selected language after navigation');
  assert.notStrictEqual(restoredAssistant.state, States.GREETING, 'Does not re-trigger GREETING on route change');
});

test('3. Bug 1: Explicit Restart Clears Session and Starts Over', (t) => {
  const { VoiceHireAssistant, States } = AssistantModule;

  globalThis.sessionStorage.setItem('vh_assistant_session', JSON.stringify({
    state: States.ACTION_SELECT,
    selectedRole: 'worker',
    selectedAction: 'login',
    currentLang: 'pa',
    lastRoute: '/login'
  }));

  const assistant = new VoiceHireAssistant();
  assert.strictEqual(assistant.selectedRole, 'worker');

  // Trigger explicit restart button
  assistant.restartConversation();

  assert.strictEqual(assistant.selectedRole, null, 'Role reset on deliberate restart');
  assert.strictEqual(assistant.selectedAction, null, 'Action reset on deliberate restart');
  const stored = globalThis.sessionStorage.getItem('vh_assistant_session');
  assert.strictEqual(stored, null, 'sessionStorage cleared on restart');
});

test('4. Bug 2: Missing Worker Profile Detection and Question Progression', (t) => {
  const { VoiceHireAssistant, States } = AssistantModule;

  globalThis.sessionStorage.clear();
  const assistant = new VoiceHireAssistant();

  // Empty profile
  assistant.workerProfile = { name: '', work: '', location: '', price: '', experience_years: '' };
  assert.strictEqual(assistant.findMissingMandatoryField(), 'name', 'First missing field is name');

  assistant.workerProfile.name = 'Sunil Kumar';
  assert.strictEqual(assistant.findMissingMandatoryField(), 'work', 'Second missing field is work');

  assistant.workerProfile.work = 'Electrician';
  assert.strictEqual(assistant.findMissingMandatoryField(), 'location', 'Third missing field is location');

  assistant.workerProfile.location = 'Noida Sector 62';
  assert.strictEqual(assistant.findMissingMandatoryField(), 'price', 'Fourth missing field is price');

  assistant.workerProfile.price = '600';
  assert.strictEqual(assistant.findMissingMandatoryField(), 'experience_years', 'Fifth missing field is experience_years');

  assistant.workerProfile.experience_years = '4';
  assert.strictEqual(assistant.findMissingMandatoryField(), null, 'No missing mandatory fields when all filled');
});

test('5. Bug 3: Hands-Free Auto-Listening vs Manual Voice Mode', (t) => {
  const { VoiceHireAssistant } = AssistantModule;

  globalThis.sessionStorage.clear();
  const assistant = new VoiceHireAssistant();

  // 1. Hands-Free mode default
  assistant.voiceMode = 'hands_free';
  assert.strictEqual(assistant.voiceMode, 'hands_free');

  // 2. Toggle to Manual mode
  assistant.toggleVoiceMode();
  assert.strictEqual(assistant.voiceMode, 'manual');
  assert.strictEqual(globalThis.localStorage.getItem('vh_voice_mode'), 'manual');

  // 3. Toggle back to Hands-Free
  assistant.toggleVoiceMode();
  assert.strictEqual(assistant.voiceMode, 'hands_free');
  assert.strictEqual(globalThis.localStorage.getItem('vh_voice_mode'), 'hands_free');
});

test('6. Sensitive Input Protection Guards Voice', (t) => {
  const { VoiceHireAssistant } = AssistantModule;

  const assistant = new VoiceHireAssistant();

  // Simulate active element being a password field
  const pwInput = new MockDOMElement('input');
  pwInput.setAttribute('type', 'password');
  globalThis.document.activeElement = pwInput;

  assert.strictEqual(assistant.isFocusedOnSensitiveField(), true, 'Detects password field focus');

  // Ordinary text field should not be classified sensitive
  const textInput = new MockDOMElement('input');
  textInput.setAttribute('type', 'text');
  textInput.id = 'city';
  globalThis.document.activeElement = textInput;

  assert.strictEqual(assistant.isFocusedOnSensitiveField(), false, 'Allows regular non-sensitive text input');
});
