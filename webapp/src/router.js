const ROUTER = (() => {
  const routes = new Map();
  let currentRoute = null;
  let currentParams = {};
  let beforeEachHooks = [];
  let afterEachHooks = [];
  let notFoundHandler = null;

  function parseRoute(path) {
    const paramNames = [];
    const regexPattern = path
      .replace(/:([^/]+)/g, (_, name) => {
        paramNames.push(name);
        return '([^/]+)';
      })
      .replace(/\*/g, '.*');
    return {
      regex: new RegExp(`^${regexPattern}$`),
      paramNames,
    };
  }

  function matchRoute(path) {
    for (const [routePath, handler] of routes) {
      const { regex, paramNames } = parseRoute(routePath);
      const match = path.match(regex);
      if (match) {
        const params = {};
        paramNames.forEach((name, i) => {
          params[name] = decodeURIComponent(match[i + 1]);
        });
        return { handler, params };
      }
    }
    return null;
  }

  async function navigate(path, replace = false) {
    const match = matchRoute(path);
    if (!match) {
      if (notFoundHandler) {
        await notFoundHandler(path);
      } else {
        console.warn('Route not found:', path);
      }
      return false;
    }

    for (const hook of beforeEachHooks) {
      const result = await hook(path, match.params);
      if (result === false) return false;
    }

    if (replace) {
      history.replaceState(null, '', path);
    } else {
      history.pushState(null, '', path);
    }

    currentRoute = path;
    currentParams = match.params;

    try {
      await match.handler(match.params);
    } catch (e) {
      console.error('Route handler error:', e);
    }

    for (const hook of afterEachHooks) {
      await hook(path, match.params);
    }

    return true;
  }

  function addRoute(path, handler) {
    routes.set(path, handler);
  }

  function onBeforeEach(fn) {
    beforeEachHooks.push(fn);
  }

  function onAfterEach(fn) {
    afterEachHooks.push(fn);
  }

  function onNotFound(fn) {
    notFoundHandler = fn;
  }

  function getCurrentRoute() {
    return currentRoute;
  }

  function getCurrentParams() {
    return currentParams;
  }

  function start() {
    window.addEventListener('popstate', () => {
      navigate(location.pathname + location.search, true);
    });
    navigate(location.pathname + location.search, true);
  }

  function goBack() {
    history.back();
  }

  return {
    addRoute,
    navigate,
    onBeforeEach,
    onAfterEach,
    onNotFound,
    getCurrentRoute,
    getCurrentParams,
    start,
    goBack,
  };
})();

export default ROUTER;