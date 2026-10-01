import API from '../api.js';
import AUTH from '../auth.js';
import TOAST from '../toast.js';

const ADMIN_VIEW = (() => {
  let stats = null;
  let loading = false;
  let container = null;

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  async function loadStats() {
    if (loading) return;
    loading = true;
    render();

    try {
      stats = await API.get('/api/admin/stats');
    } catch (e) {
      TOAST.error('خطا در بارگذاری آمار: ' + e.message);
      stats = null;
    } finally {
      loading = false;
      render();
    }
  }

  function render() {
    if (!container) return;

    let html = `
      <div class="page-header">
        <h1 class="page-title">پنل ادمین</h1>
        <button class="btn btn-secondary btn-sm" id="refresh-btn">🔄</button>
      </div>
    `;

    if (loading) {
      html += `<div class="loading-state"><div class="spinner"></div>در حال بارگذاری...</div>`;
      container.innerHTML = html;
      return;
    }

    if (!stats) {
      html += `
        <div class="card">
          <div class="card-header">
            <div class="card-title">دسترسی محدود</div>
          </div>
          <p class="text-sm text-muted">
            فقط ادمین‌ها می‌توانند این صفحه را ببینند.
          </p>
        </div>
      `;
      container.innerHTML = html;
      return;
    }

    const u = stats.users || {};
    const b = stats.bots || {};

    html += `
      <div class="row mb-4">
        <div class="card">
          <div class="card-header">
            <div class="card-title">👥 کاربران</div>
          </div>
          <div class="property-row"><span class="property-label">کل کاربران</span><span class="property-value">${u.total || 0}</span></div>
          <div class="property-row"><span class="property-label">ثبت‌نام‌شده</span><span class="property-value">${u.registered || 0}</span></div>
          <div class="property-row"><span class="property-label">فعال</span><span class="property-value">${u.active || 0}</span></div>
          <div class="property-row"><span class="property-label">مسدود</span><span class="property-value">${u.banned || 0}</span></div>
          <div class="property-row"><span class="property-label">سکه‌ها</span><span class="property-value">${(u.coins || 0).toLocaleString()}</span></div>
          <div class="property-row"><span class="property-label">ارجاع‌ها</span><span class="property-value">${u.referrals || 0}</span></div>
        </div>
        <div class="card">
          <div class="card-header">
            <div class="card-title">🤖 ربات‌ها</div>
          </div>
          <div class="property-row"><span class="property-label">کل ربات‌ها</span><span class="property-value">${b.total || 0}</span></div>
          <div class="property-row"><span class="property-label">فعال</span><span class="property-value">${b.active || 0}</span></div>
          <div class="property-row"><span class="property-label">پیام‌ دریافتی</span><span class="property-value">${(b.messages_received || 0).toLocaleString()}</span></div>
          <div class="property-row"><span class="property-label">پیام‌ ارسالی</span><span class="property-value">${(b.messages_sent || 0).toLocaleString()}</span></div>
          <div class="property-row"><span class="property-label">پخش همگانی</span><span class="property-value">${(b.broadcasts_sent || 0).toLocaleString()}</span></div>
          <div class="property-row"><span class="property-label">کاربران ربات‌ها</span><span class="property-value">${b.bot_users || 0}</span></div>
        </div>
      </div>
    `;

    if (stats.top_bots && stats.top_bots.length > 0) {
      html += `
        <div class="card">
          <div class="card-header">
            <div class="card-title">🏆 برترین ربات‌ها</div>
          </div>
          <div class="table-wrapper">
            <table class="table">
              <thead>
                <tr>
                  <th>ربات</th>
                  <th>مالک</th>
                  <th>پیام</th>
                  <th>کاربران</th>
                  <th>وضعیت</th>
                </tr>
              </thead>
              <tbody>
                ${stats.top_bots.map(bot => `
                  <tr>
                    <td>@${escapeHtml(bot.username || '')}</td>
                    <td>${escapeHtml(bot.owner_name || '')}</td>
                    <td>${(bot.messages || 0).toLocaleString()}</td>
                    <td>${bot.users || 0}</td>
                    <td>${bot.is_active ? '<span class="badge badge-success">فعال</span>' : '<span class="badge badge-neutral">غیرفعال</span>'}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }

    if (stats.top_users && stats.top_users.length > 0) {
      html += `
        <div class="card">
          <div class="card-header">
            <div class="card-title">🏆 برترین کاربران</div>
          </div>
          <div class="table-wrapper">
            <table class="table">
              <thead>
                <tr>
                  <th>کاربر</th>
                  <th>ربات‌ها</th>
                  <th>سکه</th>
                  <th>وضعیت</th>
                </tr>
              </thead>
              <tbody>
                ${stats.top_users.map(u => `
                  <tr>
                    <td>${escapeHtml(u.name || '')} <span class="text-muted">@${escapeHtml(u.username || '')}</span></td>
                    <td>${u.bots_count || 0}</td>
                    <td>${(u.coins || 0).toLocaleString()}</td>
                    <td>
                      ${u.is_banned ? '<span class="badge badge-danger">مسدود</span>' : ''}
                      ${u.is_admin ? '<span class="badge badge-primary">ادمین</span>' : ''}
                      ${!u.is_banned && !u.is_admin ? '<span class="badge badge-success">فعال</span>' : ''}
                    </td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }

    container.innerHTML = html;
    attachEvents();
  }

  function attachEvents() {
    const refreshBtn = container?.querySelector('#refresh-btn');
    refreshBtn?.addEventListener('click', loadStats);
  }

  function init(el) {
    container = el;
    loadStats();

    AUTH.onAuthChange(() => {
      if (AUTH.isAuthenticated()) {
        loadStats();
      }
    });
  }

  return { init, loadStats };
})();

export default ADMIN_VIEW;
