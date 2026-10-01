const API = (() => {
  let baseUrl = window.GRAMSAZ_CONFIG?.API_URL || '';
  let authToken = null;
  let initData = null;

  function setBaseUrl(url) {
    baseUrl = url || '';
  }

  function getBaseUrl() {
    return baseUrl;
  }

  function setAuthToken(token) {
    authToken = token;
  }

  function setInitData(data) {
    initData = data;
  }

  function getHeaders(extra = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...extra,
    };
    if (initData) {
      headers['X-Telegram-Init-Data'] = initData;
    } else if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    return headers;
  }

  async function request(path, options = {}) {
    const url = `${baseUrl}${path}`;
    const config = {
      ...options,
      headers: getHeaders(options.headers),
    };

    try {
      const response = await fetch(url, config);
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const error = new Error(data.error || `HTTP ${response.status}`);
        error.status = response.status;
        error.data = data;
        throw error;
      }

      return data;
    } catch (e) {
      if (e instanceof TypeError && e.message.includes('fetch')) {
        const error = new Error('خطای شبکه — سرور در دسترس نیست');
        error.isNetworkError = true;
        throw error;
      }
      throw e;
    }
  }

  const api = {
    setBaseUrl,
    getBaseUrl,
    get: (path) => request(path, { method: 'GET' }),
    post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) }),
    put: (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) }),
    patch: (path, body) => request(path, { method: 'PATCH', body: JSON.stringify(body) }),
    delete: (path) => request(path, { method: 'DELETE' }),

    setAuthToken,
    setInitData,
    getAuthToken: () => authToken,
    getInitData: () => initData,
  };

  return api;
})();

export default API;