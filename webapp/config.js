const config = (() => {
  const isDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
  
  const defaultConfig = {
    API_URL: isDev ? 'http://localhost:8000' : 'https://botsazgram-wnw5.onrender.com',
    WEBAPP_URL: window.location.origin,
  };

  if (typeof window.GRAMSAZ_CONFIG !== 'undefined') {
    return Object.freeze({ ...defaultConfig, ...window.GRAMSAZ_CONFIG });
  }

  return Object.freeze(defaultConfig);
})();

export default config;
