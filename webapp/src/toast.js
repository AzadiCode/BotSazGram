const TOAST = (() => {
  const container = document.getElementById('toast-root');
  let toastId = 0;

  function createToast(message, type = 'info', duration = 4000) {
    if (!container) return;

    const id = ++toastId;
    const icons = {
      success: '✓',
      error: '✕',
      warning: '⚠',
      info: 'ℹ',
    };

    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.innerHTML = `
      <span class="toast-icon">${icons[type] || icons.info}</span>
      <span class="toast-content">${escapeHtml(message)}</span>
      <button class="toast-close" aria-label="بستن">✕</button>
    `;

    const closeBtn = el.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => removeToast(el));

    container.appendChild(el);

    if (duration > 0) {
      setTimeout(() => removeToast(el), duration);
    }

    return el;
  }

  function removeToast(el) {
    if (!el || !el.parentNode) return;
    el.classList.add('removing');
    el.addEventListener('animationend', () => {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, { once: true });
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  return {
    success: (msg, dur) => createToast(msg, 'success', dur),
    error: (msg, dur) => createToast(msg, 'error', dur),
    warning: (msg, dur) => createToast(msg, 'warning', dur),
    info: (msg, dur) => createToast(msg, 'info', dur),
    show: createToast,
  };
})();

export default TOAST;