// Mock browser globals
globalThis.window = globalThis;
globalThis.addEventListener = function() {};
globalThis.removeEventListener = function() {};
globalThis.location = { pathname: '/', search: '', origin: 'http://localhost:8080', hash: '' };
globalThis.history = { pushState: function() {}, replaceState: function() {}, back: function() {}, forward: function() {} };
globalThis.fetch = () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
globalThis.URLSearchParams = URLSearchParams;
globalThis.HTMLElement = function() {};
globalThis.HTMLFormElement = function() {};
globalThis.Node = function() {};
globalThis.customElements = { define: function() {} };
globalThis.getComputedStyle = () => ({ getPropertyValue: () => '' });

// Mock localStorage
const localStorageStore = {};
globalThis.localStorage = {
  getItem: (k) => localStorageStore[k] || null,
  setItem: (k, v) => { localStorageStore[k] = v; },
  removeItem: (k) => { delete localStorageStore[k]; },
  clear: () => { for (const k in localStorageStore) delete localStorageStore[k]; },
};

// Mock document with proper implementation
const elements = new Map();
function createEl(tag) {
  const children = [];
  const el = {
    tagName: tag.toUpperCase(),
    id: '',
    className: '',
    classList: { 
      _set: new Set(),
      add(c) { this._set.add(c); },
      remove(c) { this._set.delete(c); },
      toggle(c, force) { 
        if (force === undefined) {
          if (this._set.has(c)) this._set.delete(c);
          else this._set.add(c);
        } else if (force) this._set.add(c);
        else this._set.delete(c);
      },
      contains(c) { return this._set.has(c); },
    },
    _dataset: {},
    get dataset() { return this._dataset; },
    innerHTML: '',
    style: { setProperty: () => {}, removeProperty: () => {} },
    _style: '',
    get styleStr() { return this._style; },
    appendChild(child) { children.push(child); child.parentNode = this; return child; },
    removeChild(child) { const i = children.indexOf(child); if (i >= 0) children.splice(i, 1); },
    addEventListener(type, fn, opts) { 
      if (!this._listeners) this._listeners = {};
      if (!this._listeners[type]) this._listeners[type] = [];
      this._listeners[type].push(fn);
    },
    removeEventListener(type, fn) {
      if (!this._listeners) return;
      if (this._listeners[type]) this._listeners[type] = this._listeners[type].filter(f => f !== fn);
    },
    querySelector(sel) { return el._query(sel, children); },
    querySelectorAll(sel) { return el._queryAll(sel, children); },
    focus() {},
    value: '',
    disabled: false,
    setAttribute(name, value) { el[name] = value; },
    getAttribute(name) { return el[name] || null; },
    parentNode: null,
    _listeners: {},
    _query(sel, arr) {
      for (const child of arr) {
        if (this._match(child, sel)) return child;
        const found = this._query(sel, child.children || []);
        if (found) return found;
      }
      return null;
    },
    _queryAll(sel, arr) {
      let results = [];
      for (const child of arr) {
        if (this._match(child, sel)) results.push(child);
        results = results.concat(this._queryAll(sel, child.children || []));
      }
      return results;
    },
    _match(el, sel) {
      if (sel.startsWith('.')) {
        return el.classList._set.has(sel.substring(1));
      }
      if (sel.startsWith('#')) {
        return el.id === sel.substring(1);
      }
      if (sel.startsWith('[')) {
        const match = sel.match(/\[data-([^\s\]]+)\]/);
        if (match) {
          return el._dataset[match[1]] !== undefined;
        }
      }
      return el.tagName === sel.toUpperCase();
    },
    children: [],
  };
  // Make children observable
  const originalAppend = el.appendChild;
  el.appendChild = (child) => {
    children.push(child);
    el.children.push(child);
    child.parentNode = el;
    return child;
  };
  return el;
}

globalThis.document = {
  _elements: new Map(),
  getElementById(id) {
    if (!this._elements.has(id)) {
      const el = createEl('div');
      el.id = id;
      this._elements.set(id, el);
    }
    return this._elements.get(id);
  },
  querySelector(sel) {
    if (sel === '.tabbar') {
      const nav = createEl('nav');
      nav.id = 'tabbar';
      nav.className = 'tabbar';
      // Add tab buttons
      const routes = ['bots', 'studio', 'profile', 'admin'];
      for (const r of routes) {
        const btn = createEl('button');
        btn.className = 'tab';
        btn._dataset.route = r;
        btn.innerHTML = r;
        nav.appendChild(btn);
      }
      return nav;
    }
    return null;
  },
  querySelectorAll(sel) {
    if (sel === '.tabbar .tab' || sel === '.tab') {
      // Return mock tab elements
      const tabs = [];
      for (const r of ['bots', 'studio', 'profile', 'admin']) {
        const btn = createEl('button');
        btn.className = 'tab';
        btn._dataset.route = r;
        tabs.push(btn);
      }
      return tabs;
    }
    return [];
  },
  addEventListener(type, fn) {
    // Store event listeners for testing
    if (!this._listeners) this._listeners = {};
    if (!this._listeners[type]) this._listeners[type] = [];
    this._listeners[type].push(fn);
  },
  removeEventListener() {},
  body: createEl('body'),
  createElement(tag) { return createEl(tag); },
  baseURI: 'http://localhost:8080/',
  location: globalThis.location,
};

// Now test the actual flow
console.log('=== Testing module loading ===');

const errors = [];

try {
  const { default: config } = await import('./config.js');
  console.log('config.js: OK, API_URL =', config.API_URL);
  
  const { default: API } = await import('./src/api.js');
  API.setBaseUrl(config.API_URL);
  console.log('api.js: OK');
  
  const { default: AUTH } = await import('./src/auth.js');
  console.log('auth.js: OK');
  
  const { default: TOAST } = await import('./src/toast.js');
  console.log('toast.js: OK');
  
  const { default: ROUTER } = await import('./src/router.js');
  console.log('router.js: OK');
  
  const { default: SHEET } = await import('./src/sheet.js');
  console.log('sheet.js: OK');
  
  const { default: BOTS_VIEW } = await import('./src/views/bots.js');
  console.log('bots.js: OK');
  
  const { default: STUDIO_VIEW } = await import('./src/views/studio.js');
  console.log('studio.js: OK');
  
  const { default: PROFILE_VIEW } = await import('./src/views/profile.js');
  console.log('profile.js: OK');
  
  const { default: ADMIN_VIEW } = await import('./src/views/admin.js');
  console.log('admin.js: OK');
  
  const mainModule = await import('./src/main.js');
  console.log('main.js: OK');
  
  // Wait a bit for init() to complete
  await new Promise(r => setTimeout(r, 500));
  
  console.log('\n=== Testing navigation ===');
  console.log('Current route:', ROUTER.getCurrentRoute());
  
  // Try navigating to profile
  try {
    await ROUTER.navigate('/profile');
    console.log('Navigate to /profile: OK');
    console.log('Current route after navigation:', ROUTER.getCurrentRoute());
  } catch(e) {
    console.error('Navigate to /profile: ERROR -', e.message);
    errors.push('navigate /profile: ' + e.message);
  }
  
  // Try navigating to bots
  try {
    await ROUTER.navigate('/bots');
    console.log('Navigate to /bots: OK');
    console.log('Current route after navigation:', ROUTER.getCurrentRoute());
  } catch(e) {
    console.error('Navigate to /bots: ERROR -', e.message);
    errors.push('navigate /bots: ' + e.message);
  }
  
  // Try navigating to studio
  try {
    await ROUTER.navigate('/studio');
    console.log('Navigate to /studio: OK');
    console.log('Current route after navigation:', ROUTER.getCurrentRoute());
  } catch(e) {
    console.error('Navigate to /studio: ERROR -', e.message);
    errors.push('navigate /studio: ' + e.message);
  }

  // Try navigating to admin
  try {
    await ROUTER.navigate('/admin');
    console.log('Navigate to /admin: OK');
    console.log('Current route after navigation:', ROUTER.getCurrentRoute());
  } catch(e) {
    console.error('Navigate to /admin: ERROR -', e.message);
    errors.push('navigate /admin: ' + e.message);
  }

} catch(e) {
  console.error('IMPORT ERROR:', e.message);
  console.error('Stack:', e.stack);
  errors.push('import: ' + e.message);
}

console.log('\n=== Summary ===');
if (errors.length === 0) {
  console.log('All tests passed!');
} else {
  console.log('Errors found:');
  errors.forEach(e => console.log('  -', e));
}
