import API from '../api.js';
import AUTH from '../auth.js';
import TOAST from '../toast.js';
import SHEET from '../sheet.js';

const PROFILE_VIEW = (() => {
  let user = null;
  let loading = false;
  let container = null;

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  async function loadUser() {
    if (loading) return;

    if (!AUTH.isAuthenticated()) {
      user = null;
      render();
      return;
    }

    loading = true;
    render();

    try {
      user = await API.get('/api/auth/me');
    } catch (e) {
      TOAST.error('خطا در بارگذاری پروفایل: ' + e.message);
      user = null;
    } finally {
      loading = false;
      render();
    }
  }

  function render() {
    if (!container) return;

    let html = `
      <div class="page-header">
        <h1 class="page-title">پروفایل من</h1>
      </div>
    `;

    if (loading) {
      html += `<div class="loading-state"><div class="spinner"></div>در حال بارگذاری...</div>`;
      container.innerHTML = html;
      return;
    }

    if (!user) {
      html += renderLoginCard();
      container.innerHTML = html;
      attachLoginEvents();
      return;
    }

    const avatarUrl = user.photo_url
      ? user.photo_url
      : `https://ui-avatars.com/api/?background=0d6efd&color=fff&name=${encodeURIComponent(user.first_name || user.username || 'U')}`;

    const coins = user.coins || 0;
    const referrals = user.referrals || user.referral_count || 0;
    const referralCode = user.referral_code || 'ندارید';

    html += `
      <div class="card">
        <div class="card-header">
          <div class="flex items-center gap-3">
            <img src="${avatarUrl}" alt="avatar" class="avatar lg">
            <div>
              <div class="card-title">${escapeHtml(user.first_name || '')} ${escapeHtml(user.last_name || '')}</div>
              <div class="text-sm text-muted">@${escapeHtml(user.username || 'unknown')}</div>
            </div>
          </div>
          <span class="badge badge-primary">🪙 ${coins.toLocaleString()} سکه</span>
        </div>
        <div class="input-group">
          <label>آی‌دی عددی</label>
          <input type="text" value="${user.uid}" disabled>
        </div>
        <div class="input-group">
          <label>کد رفرال</label>
          <input type="text" value="${escapeHtml(referralCode)}" disabled>
          <div class="input-hint">تعداد ارجاع‌ها: ${referrals.toLocaleString()}</div>
        </div>
        <div class="input-group">
          <label>تاریخ عضویت</label>
          <input type="text" value="${new Date(user.created_at || Date.now()).toLocaleDateString('fa-IR')}" disabled>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">تنظیمات</div>
        </div>
        <div class="input-group">
          <label class="flex items-center justify-between">
            <span>اعلان‌ها</span>
            <label class="switch">
              <input type="checkbox" id="notify-toggle" ${user.settings?.notify ? 'checked' : ''}>
              <span class="switch-slider"></span>
            </label>
          </label>
        </div>
        <div class="input-group">
          <label class="flex items-center justify-between">
            <span>ورود با رمز عبور</label>
            <span class="text-sm text-muted">${user.has_password ? 'فعال' : 'غیرفعال'}</span>
          </label>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-secondary flex-1" id="logout-btn">🚪 خروج</button>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">راهنمای رفرال</div>
        </div>
        <div class="text-sm text-muted mb-2">
          کد رفرال شما: <strong>${escapeHtml(referralCode)}</strong>
        </div>
        <div class="text-sm text-muted">
          برای هر کاربری که با کد شما ثبت نام کند، ${50} سکه دریافت خواهید کرد.
        </div>
      </div>
    `;

    container.innerHTML = html;
    attachEvents();
  }

  function renderLoginCard() {
    return `
      <div class="card">
        <div class="card-header">
          <div class="card-title">ورود به حساب</div>
        </div>
        <div class="flex flex-col gap-2">
          <button class="btn btn-primary btn-block" id="login-tg-btn">ورود با تلگرام</button>
          <button class="btn btn-secondary btn-block" id="login-cred-btn">ورود با نام کاربری</button>
          <button class="btn btn-secondary btn-block" id="register-btn">ثبت‌نام حساب وب</button>
        </div>
      </div>
    `;
  }

  function attachLoginEvents() {
    const tgBtn = container?.querySelector('#login-tg-btn');
    tgBtn?.addEventListener('click', () => {
      if (window.Telegram?.WebApp?.initData) {
        AUTH.loginWithInitData(window.Telegram.WebApp.initData).then(() => {
          loadUser();
        }).catch(e => {
          TOAST.error('ورود ناموفق: ' + e.message);
        });
      } else {
        TOAST.info('ورود از طریق تلگرام WebApp در دسترس نیست');
      }
    });

    const credBtn = container?.querySelector('#login-cred-btn');
    credBtn?.addEventListener('click', () => showLoginForm());

    const regBtn = container?.querySelector('#register-btn');
    regBtn?.addEventListener('click', () => showRegisterFlow());
  }

  function showLoginForm() {
    const form = document.createElement('form');
    form.innerHTML = `
      <div class="input-group">
        <label>نام کاربری</label>
        <input type="text" name="username" placeholder="نام کاربری وب" required autocomplete="off">
      </div>
      <div class="input-group">
        <label>رمز عبور</label>
        <input type="password" name="password" placeholder="••••••••" required>
      </div>
    `;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = form.username.value.trim();
      const password = form.password.value;
      if (!username || !password) return;

      const submitBtn = SHEET.el?.querySelector('.sheet-footer button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'در حال ورود...';
      }

      try {
        await AUTH.loginWithCredentials(username, password);
        TOAST.success('ورود موفق');
        SHEET.close();
        await loadUser();
      } catch (e) {
        TOAST.error('خطا: ' + e.message);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = 'ورود';
        }
      }
    });

    SHEET.open(form, {
      title: 'ورود با نام کاربری',
      footer: `
        <button type="button" class="btn btn-secondary" onclick="this.closest('.sheet-root').querySelector('.sheet-close').click()">انصراف</button>
        <button type="submit" form="${form.id || ''}" class="btn btn-primary">ورود</button>
      `,
    });

    form.querySelector('input[name="username"]')?.focus();
  }

  function showRegisterFlow() {
    const form = document.createElement('form');
    form.innerHTML = `
      <div class="input-group">
        <label>نام کاربری تلگرام</label>
        <input type="text" name="telegram_username" placeholder="مثال: ali" required autocomplete="off">
        <div class="input-hint">ابتدا ربات مادر را /start کنید</div>
      </div>
      <div class="input-group">
        <label>نام کاربری وب</label>
        <input type="text" name="username" placeholder="حداقل ۳ کاراکتر" required>
      </div>
      <div class="input-group">
        <label>رمز عبور</label>
        <input type="password" name="password" placeholder="حداقل ۶ کاراکتر" required>
      </div>
      <div class="input-group">
        <label>کد تأیید (۶ رقمی)</label>
        <input type="text" name="code" placeholder="کد از ربات مادر" required>
        <div class="input-hint">دکمهٔ ارسال کد را بزنید</div>
        <button type="button" class="btn btn-secondary btn-sm" id="send-code-btn" style="align-self: flex-start;">📨 ارسال کد</button>
      </div>
      <div class="input-group">
        <label>کد رفرال (اختیاری)</label>
        <input type="text" name="referral_code" placeholder="اگر دارید وارد کنید">
      </div>
    `;

    let currentCode = '';

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const telegramUsername = form.telegram_username.value.trim().replace(/^@/, '');
      const username = form.username.value.trim();
      const password = form.password.value;
      const code = form.code.value.trim();
      const referralCode = form.referral_code.value.trim();
      if (!telegramUsername || !username || !password || !code) return;

      const submitBtn = SHEET.el?.querySelector('.sheet-footer button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'در حال ثبت‌نام...';
      }

      try {
        await AUTH.register(username, password, telegramUsername, referralCode, code);
        TOAST.success('ثبت‌نام موفق! 🎉');
        SHEET.close();
        await loadUser();
      } catch (e) {
        TOAST.error('خطا: ' + e.message);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = 'ثبت‌نام';
        }
      }
    });

    const sendCodeBtn = form.querySelector('#send-code-btn');
    sendCodeBtn?.addEventListener('click', async () => {
      const tgUsername = form.telegram_username.value.trim().replace(/^@/, '');
      if (!tgUsername) {
        TOAST.error('ابتدا نام کاربری تلگرام را وارد کنید');
        return;
      }
      sendCodeBtn.disabled = true;
      sendCodeBtn.textContent = 'در حال ارسال...';
      try {
        const result = await AUTH.sendCode(tgUsername);
        if (result.sent) {
          TOAST.success('کد تأیید ارسال شد');
        } else if (result.code) {
          currentCode = result.code;
          TOAST.success('کد تأیید: ' + result.code + ' (ربات مادر آماده نیست)');
          form.code.value = result.code;
        }
      } catch (e) {
        TOAST.error('خطا: ' + e.message);
      } finally {
        sendCodeBtn.disabled = false;
        sendCodeBtn.textContent = '📨 ارسال کد';
      }
    });

    SHEET.open(form, {
      title: 'ثبت‌نام حساب وب',
      footer: `
        <button type="button" class="btn btn-secondary" onclick="this.closest('.sheet-root').querySelector('.sheet-close').click()">انصراف</button>
      `,
    });

    form.querySelector('input[name="telegram_username"]')?.focus();
  }

  function attachEvents() {
    const logoutBtn = container?.querySelector('#logout-btn');
    logoutBtn?.addEventListener('click', () => {
      AUTH.logout();
      loadUser();
      TOAST.success('با موفقیت خارج شدید');
    });

    const notifyToggle = container?.querySelector('#notify-toggle');
    notifyToggle?.addEventListener('change', async () => {
      try {
        await API.patch('/api/auth/settings', { notify: notifyToggle.checked });
        TOAST.success('تنظیمات ذخیره شد');
      } catch (e) {
        TOAST.error('خطا: ' + e.message);
        notifyToggle.checked = !notifyToggle.checked;
      }
    });
  }

  function init(el) {
    container = el;
    loadUser();

    AUTH.onAuthChange(() => {
      user = null;
      loadUser();
    });
  }

  return { init };
})();

export default PROFILE_VIEW;
