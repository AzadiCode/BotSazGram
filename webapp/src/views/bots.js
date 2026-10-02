import API from '../api.js';
import AUTH from '../auth.js';
import TOAST from '../toast.js';
import SHEET from '../sheet.js';
import ROUTER from '../router.js';

const BOTS_VIEW = (() => {
  let bots = [];
  let loading = false;
  let container = null;

  function renderBotCard(bot) {
    const statusClass = bot.is_active ? 'badge-success' : 'badge-neutral';
    const statusText = bot.is_active ? 'فعال' : 'غیرفعال';
    const runningClass = bot.is_running ? 'badge-primary' : 'badge-neutral';
    const runningText = bot.is_running ? 'در حال اجرا' : 'متوقف';

    return `
      <article class="card" data-bot-id="${bot.bot_id}">
        <div class="card-header">
          <div>
             <div class="card-title">@${escapeHtml(bot.username || 'بدون نام')}</div>
             <div class="text-sm text-muted">${escapeHtml(bot.bot_id || 'unknown')}</div>
          </div>
          <div class="card-actions">
            <span class="badge ${statusClass}">${statusText}</span>
            <span class="badge ${runningClass}">${runningText}</span>
          </div>
        </div>
        <div class="flex gap-2 mb-3">
          <button class="btn btn-secondary btn-sm flex-1" data-action="studio" data-bot-id="${bot.bot_id}">
            🧩 استودیو
          </button>
          <button class="btn btn-secondary btn-sm flex-1" data-action="settings" data-bot-id="${bot.bot_id}">
            ⚙ تنظیمات
          </button>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-primary btn-sm flex-1" data-action="toggle" data-bot-id="${bot.bot_id}">
            ${bot.is_active ? 'غیرفعال کردن' : 'فعال کردن'}
          </button>
          <button class="btn btn-danger btn-sm flex-1" data-action="delete" data-bot-id="${bot.bot_id}">
            حذف
          </button>
        </div>
      </article>
    `;
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  async function loadBots() {
    if (loading) return;
    loading = true;
    render();

    try {
      const data = await API.get('/api/bots');
      bots = data.bots || [];
    } catch (e) {
      TOAST.error('خطا در بارگذاری ربات‌ها: ' + e.message);
      bots = [];
    } finally {
      loading = false;
      render();
    }
  }

  function render() {
    if (!container) return;

    let html = `
      <div class="page-header">
        <h1 class="page-title">ربات‌های من</h1>
        <button class="btn btn-primary" id="add-bot-btn">+ افزودن ربات</button>
      </div>
    `;

    if (loading) {
      html += `<div class="loading-state"><div class="spinner"></div>در حال بارگذاری...</div>`;
    } else if (bots.length === 0) {
      html += `
        <div class="empty-state">
          <div class="empty-state-icon">🤖</div>
          <div class="empty-state-title">هنوز رباتی ندارید</div>
          <div class="empty-state-desc">اولین ربات خود را بسازید و مدیریت کنید</div>
        </div>
      `;
    } else {
      html += bots.map(renderBotCard).join('');
    }

    container.innerHTML = html;
    attachEvents();
  }

  function attachEvents() {
    if (!container) return;

    container.querySelector('#add-bot-btn')?.addEventListener('click', showAddBotSheet);

    container.querySelectorAll('[data-action="studio"]').forEach(btn => {
      btn.addEventListener('click', () => {
        ROUTER.navigate(`/studio/${btn.dataset.botId}`);
      });
    });

    container.querySelectorAll('[data-action="settings"]').forEach(btn => {
      btn.addEventListener('click', () => showBotSettings(btn.dataset.botId));
    });

    container.querySelectorAll('[data-action="toggle"]').forEach(btn => {
      btn.addEventListener('click', () => toggleBot(btn.dataset.botId));
    });

    container.querySelectorAll('[data-action="delete"]').forEach(btn => {
      btn.addEventListener('click', () => deleteBot(btn.dataset.botId));
    });
  }

  function showAddBotSheet() {
    const form = document.createElement('form');
    form.innerHTML = `
      <div class="input-group">
        <label>توکن ربات</label>
        <input type="text" name="token" placeholder="123456:ABC-DEF..." required autocomplete="off">
        <div class="input-hint">توکن را از @BotFather دریافت کنید</div>
      </div>
    `;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const token = form.token.value.trim();
      if (!token) return;

      const submitBtn = SHEET.el?.querySelector('.sheet-footer button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'در حال افزودن...';
      }

      try {
        await API.post('/api/bots', { token });
        TOAST.success('ربات با موفقیت افزوده شد');
        SHEET.close();
        await loadBots();
      } catch (e) {
        TOAST.error('خطا: ' + e.message);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = 'افزودن';
        }
      }
    });

    SHEET.open(form, {
      title: 'افزودن ربات جدید',
      footer: `
        <button type="button" class="btn btn-secondary" onclick="this.closest('.sheet-root').querySelector('.sheet-close').click()">انصراف</button>
        <button type="submit" form="${form.id || ''}" class="btn btn-primary">افزودن</button>
      `,
    });

    form.querySelector('input').focus();
  }

  async function toggleBot(botId) {
    const bot = bots.find(b => b.bot_id === botId);
    if (!bot) return;

    try {
      await API.patch(`/api/bots/${botId}`, { is_active: !bot.is_active });
      TOAST.success(bot.is_active ? 'ربات غیرفعال شد' : 'ربات فعال شد');
      await loadBots();
    } catch (e) {
      TOAST.error('خطا: ' + e.message);
    }
  }

  async function deleteBot(botId) {
    const bot = bots.find(b => b.bot_id === botId);
    if (!bot) return;

    if (!confirm(`آیا از حذف ربات @${bot.username} مطمئن هستید؟`)) return;

    try {
      await API.delete(`/api/bots/${botId}`);
      TOAST.success('ربات حذف شد');
      await loadBots();
    } catch (e) {
      TOAST.error('خطا: ' + e.message);
    }
  }

  function showBotSettings(botId) {
    const bot = bots.find(b => b.bot_id === botId);
    if (!bot) return;

    const form = document.createElement('form');
    form.innerHTML = `
      <div class="input-group">
        <label>نام کاربری</label>
        <input type="text" name="username" value="${escapeHtml(bot.username || '')}" disabled>
        <div class="input-hint">نام کاربری از تلگرام دریافت می‌شود</div>
      </div>
      <div class="input-group">
        <label>وضعیت</label>
        <select name="is_active" disabled>
          <option value="true" ${bot.is_active ? 'selected' : ''}>فعال</option>
          <option value="false" ${!bot.is_active ? 'selected' : ''}>غیرفعال</option>
        </select>
      </div>
      <div class="input-group">
        <label> توکن (مخفی)</label>
        <input type="password" value="••••••••" disabled>
      </div>
    `;

    SHEET.open(form, {
      title: `تنظیمات @${escapeHtml(bot.username)}`,
      footer: `
        <button type="button" class="btn btn-secondary" onclick="this.closest('.sheet-root').querySelector('.sheet-close').click()">بستن</button>
      `,
    });
  }

  function init(el) {
    container = el;
    loadBots();

    AUTH.onAuthChange(() => {
      if (AUTH.isAuthenticated()) {
        loadBots();
      } else {
        bots = [];
        render();
      }
    });
  }

  return { init, loadBots };
})();

export default BOTS_VIEW;