import API from './api.js';

const AUTH = (() => {
  const STORAGE_KEY = 'gramsaaz_auth';
  const DEVICE_KEY = 'gramsaaz_device';
  let currentUser = null;
  let listeners = [];

  function notify() {
    listeners.forEach(fn => fn(currentUser));
  }

  function loadFromStorage() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const data = JSON.parse(stored);
        currentUser = data.user;
        if (data.token) API.setAuthToken(data.token);
        if (data.initData) API.setInitData(data.initData);
      }
    } catch (e) {
      console.warn('Failed to load auth from storage:', e);
    }
  }

  function saveToStorage() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        user: currentUser,
        token: API.getAuthToken(),
        initData: API.getInitData(),
      }));
    } catch (e) {
      console.warn('Failed to save auth to storage:', e);
    }
  }

  function clearStorage() {
    localStorage.removeItem(STORAGE_KEY);
  }

  function getDeviceId() {
    try {
      let id = localStorage.getItem(DEVICE_KEY);
      if (!id) {
        id = 'web_' + Math.random().toString(36).substring(2, 15);
        localStorage.setItem(DEVICE_KEY, id);
      }
      return id;
    } catch (e) {
      return '';
    }
  }

  async function loginWithInitData(initData) {
    API.setInitData(initData);
    const user = await API.get('/api/auth/me');
    currentUser = user;
    saveToStorage();
    notify();
    return user;
  }

  async function loginWithCredentials(username, password) {
    const data = await API.post('/api/auth/login', {
      username,
      password,
      device_id: getDeviceId(),
    });
    API.setAuthToken(data.token);
    API.setInitData(null);
    currentUser = data.user;
    saveToStorage();
    notify();
    return data.user;
  }

  async function sendCode(telegramUsername) {
    const data = await API.post('/api/auth/send-code', {
      telegram_username: telegramUsername,
      device_id: getDeviceId(),
    });
    return {
      sent: data.sent,
      code: data.code,
      message: data.message,
    };
  }

  async function register(username, password, telegramUsername, referralCode, code) {
    const data = await API.post('/api/auth/register', {
      username,
      password,
      telegram_username: telegramUsername,
      referral_code: referralCode,
      code,
      device_id: getDeviceId(),
    });
    API.setAuthToken(data.token);
    API.setInitData(null);
    currentUser = data.user;
    saveToStorage();
    notify();
    return data.user;
  }

  async function refreshUser() {
    if (!currentUser) return null;
    try {
      const user = await API.get('/api/auth/me');
      currentUser = user;
      saveToStorage();
      notify();
      return user;
    } catch (e) {
      logout();
      throw e;
    }
  }

  async function logout() {
    const token = API.getAuthToken();
    if (token) {
      try {
        await API.post('/api/auth/logout');
      } catch (e) {
        console.warn('Logout API error:', e);
      }
    }
    currentUser = null;
    API.setAuthToken(null);
    API.setInitData(null);
    clearStorage();
    notify();
  }

  function getUser() {
    return currentUser;
  }

  function isAuthenticated() {
    return !!currentUser;
  }

  function onAuthChange(fn) {
    listeners.push(fn);
    return () => {
      listeners = listeners.filter(l => l !== fn);
    };
  }

  function getInitDataFromURL() {
    const params = new URLSearchParams(window.location.search);
    return params.get('initData') || params.get('tgWebAppData');
  }

  function getInitDataFromTelegramWebApp() {
    if (window.Telegram?.WebApp?.initData) {
      return window.Telegram.WebApp.initData;
    }
    return null;
  }

  async function tryAutoLogin() {
    loadFromStorage();

    if (currentUser) {
      try {
        await refreshUser();
        return currentUser;
      } catch (e) {
        return null;
      }
    }

    const initData = getInitDataFromTelegramWebApp() || getInitDataFromURL();
    if (initData) {
      try {
        return await loginWithInitData(initData);
      } catch (e) {
        console.warn('Auto login with initData failed:', e);
        return null;
      }
    }

    return null;
  }

  return {
    loginWithInitData,
    loginWithCredentials,
    sendCode,
    register,
    refreshUser,
    logout,
    getUser,
    isAuthenticated,
    onAuthChange,
    tryAutoLogin,
    getDeviceId,
  };
})();

export default AUTH;
