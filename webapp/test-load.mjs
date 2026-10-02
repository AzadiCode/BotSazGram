// Mock browser globals
globalThis.window = globalThis;
globalThis.location = { pathname: '/', search: '', origin: 'http://localhost:8080', hash: '' };
globalThis.document = {
  _els: {},
  getElementById: function(id) {
    if (this._els[id]) return this._els[id];
    const el = this._createEl('div');
    el.id = id;
    this._els[id] = el;
    return el;
  },
  querySelector: function(sel) {
    if (sel === '.tabbar') return this._createEl('nav');
    if (sel === '#view') return this.getElementById('view');
    return this._createEl('div');
  },
  querySelectorAll: function(sel) {
    if (sel === '.tabbar .tab' || sel === '.tab') {
      const tabs = ['bots', 'studio', 'profile'].map(route => {
        const el = this._createEl('button');
        el.className = 'tab';
        el.dataset = { route };
        el.classList = { toggle: () => {}, add: () => {}, remove: () => {}, contains: () => false };
        el.addEventListener = function() {};
        return el;
      });
      return tabs;
    }
    return [];
  },
  addEventListener: function() {},
  removeEventListener: function() {},
  body: { appendChild: function() {}, removeChild: function() {}, style: {} },
  createElement: function(tag) { return this._createEl(tag); },
  location: globalThis.location,
  _createEl: function(tag) {
    const el = {
      tagName: tag, innerHTML: '', appendChild: function() {}, addEventListener: function() {},
      style: {}, focus: function() {}, value: '', 
      querySelector: function() { return null; },
      querySelectorAll: function() { return []; },
      classList: { toggle: function() {}, add: function() {}, remove: function() {}, contains: function() { return false; } },
      dataset: {}, setAttribute: function() {}, getAttribute: function() { return null; },
      disabled: false, parentNode: null,
    };
    return el;
  },
};
globalThis.localStorage = {
  _data: {},
  getItem: function(k) { return this._data[k] || null; },
  setItem: function(k, v) { this._data[k] = v; },
  removeItem: function(k) { delete this._data[k]; },
  clear: function() {},
};
globalThis.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
globalThis.history = { pushState: function() {}, replaceState: function() {}, back: function() {}, forward: function() {} };
globalThis.URLSearchParams = URLSearchParams;
globalThis.HTMLElement = function() {};
globalThis.HTMLFormElement = function() {};
globalThis.Node = function() {};
globalThis.customElements = { define: function() {} };
globalThis.getComputedStyle = () => ({ getPropertyValue: () => '' });

// Test: Can we import all modules?
const results = {};
for (const [name, path] of [
  ['config', './config.js'],
  ['api', './src/api.js'],
  ['auth', './src/auth.js'],
  ['toast', './src/toast.js'],
  ['router', './src/router.js'],
  ['sheet', './src/sheet.js'],
  ['bots', './src/views/bots.js'],
  ['studio', './src/views/studio.js'],
  ['profile', './src/views/profile.js'],
  ['admin', './src/views/admin.js'],
  ['main', './src/main.js'],
]) {
  try {
    await import(path);
    results[name] = 'OK';
  } catch(e) {
    results[name] = 'ERROR: ' + e.message;
  }
}

console.log('Module load results:');
for (const [name, result] of Object.entries(results)) {
  console.log(`  ${name}: ${result}`);
}
