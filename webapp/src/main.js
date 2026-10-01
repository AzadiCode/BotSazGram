import config from '../config.js';
import API from './api.js';
import AUTH from './auth.js';
import TOAST from './toast.js';
import ROUTER from './router.js';
import BOTS_VIEW from './views/bots.js';
import STUDIO_VIEW from './views/studio.js';
import PROFILE_VIEW from './views/profile.js';
import ADMIN_VIEW from './views/admin.js';

API.setBaseUrl(config.API_URL);

const TAB_ROUTES = {
  bots: '/bots',
  studio: '/studio',
  profile: '/profile',
  admin: '/admin',
};

const TAB_KEYS = {
  bots: 'bots',
  studio: null,
  profile: 'profile',
  admin: 'admin',
};

function updateTabbar(route) {
  const tabs = document.querySelectorAll('.tabbar .tab');
  tabs.forEach(tab => {
    const routeKey = tab.dataset.route;
    const targetPath = TAB_ROUTES[routeKey];
    const isActive = route === targetPath || (routeKey === 'studio' && route.startsWith('/studio'));
    tab.classList.toggle('active', isActive);
  });
}

function updateAdminTab() {
  const adminTab = document.getElementById('admin-tab');
  if (!adminTab) return;
  const user = AUTH.getUser();
  const show = !!(user && user.is_admin);
  adminTab.style.display = show ? 'flex' : 'none';
  if (!show && ROUTER.getCurrentRoute() === '/admin') {
    ROUTER.navigate('/bots');
  }
}

async function renderView() {
  const viewContainer = document.getElementById('view');
  const route = ROUTER.getCurrentRoute();

  viewContainer.innerHTML = '<div class="loading-state"><div class="spinner"></div>در حال بارگذاری...</div>';

  try {
    if (route === '/bots') {
      await BOTS_VIEW.init(viewContainer);
    } else if (route.startsWith('/studio')) {
      const botId = route.split('/').pop();
      if (botId && botId !== 'studio') {
        await STUDIO_VIEW.init(viewContainer, botId);
      } else {
        await BOTS_VIEW.init(viewContainer);
        ROUTER.navigate('/bots');
      }
    } else if (route === '/profile') {
      PROFILE_VIEW.init(viewContainer);
    } else if (route === '/admin') {
      if (!AUTH.getUser()?.is_admin) {
        viewContainer.innerHTML = '<div class="empty-state"><div class="empty-state-icon">🚫</div><div class="empty-state-title">دسترسی محدود</div></div>';
      } else {
        ADMIN_VIEW.init(viewContainer);
      }
    } else if (route === '/') {
      ROUTER.navigate('/bots');
    } else {
      viewContainer.innerHTML = '<div class="empty-state"><div class="empty-state-icon">❓</div><div class="empty-state-title">صفحه یافت نشد</div></div>';
    }
  } catch (e) {
    TOAST.error('خطا در بارگذاری صفحه: ' + e.message);
    viewContainer.innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠️</div><div class="empty-state-title">خطا در بارگذاری</div></div>';
  }

  updateTabbar(route);
}

function initTabbar() {
  const tabbar = document.querySelector('.tabbar');
  if (!tabbar) return;

  const tabs = tabbar.querySelectorAll('.tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const route = tab.dataset.route;
      if (route === 'bots') ROUTER.navigate('/bots');
      else if (route === 'profile') ROUTER.navigate('/profile');
      else if (route === 'studio' && AUTH.isAuthenticated()) ROUTER.navigate('/bots');
      else if (route === 'admin') ROUTER.navigate('/admin');
    });
  });
}

async function init() {
  await AUTH.tryAutoLogin();
  updateAdminTab();

  AUTH.onAuthChange(() => {
    updateAdminTab();
  });

  ROUTER.onBeforeEach(async (path) => {
    const requiresAuth = path.startsWith('/profile') || path === '/admin' || path.startsWith('/studio');
    if (requiresAuth && !AUTH.isAuthenticated()) {
      ROUTER.navigate('/bots');
      return false;
    }
    if (path === '/admin' && !AUTH.getUser()?.is_admin) {
      ROUTER.navigate('/bots');
      return false;
    }
    return true;
  });

  ROUTER.onAfterEach(() => {
    renderView();
  });

  ROUTER.onNotFound(() => {
    const view = document.getElementById('view');
    view.innerHTML = '<div class="empty-state"><div class="empty-state-icon">❓</div><div class="empty-state-title">صفحه یافت نشد</div></div>';
    updateTabbar('/');
  });

  initTabbar();

  if (window.Telegram?.WebApp?.ready) {
    window.Telegram.WebApp.ready();
  }

  ROUTER.start();
}

document.addEventListener('DOMContentLoaded', init);

window.GramSaz = {
  API,
  AUTH,
  ROUTER,
  TOAST,
  config,
};

export { API, AUTH, ROUTER, TOAST, config };
