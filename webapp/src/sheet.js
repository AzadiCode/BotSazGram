const SHEET = (() => {
  const root = document.getElementById('sheet-root');
  let currentSheet = null;
  let sheetSeq = 0;

  function createSheet(content, options = {}) {
    if (!root) return null;

    closeSheet();

    const { title = '', showHandle = true, footer = null } = options;

    const el = document.createElement('div');
    el.className = 'sheet-root';
    el.innerHTML = `
      <div class="sheet-backdrop"></div>
      <div class="sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-title">
        ${showHandle ? '<div class="sheet-handle"></div>' : ''}
        <div class="sheet-header">
          <h3 id="sheet-title" class="sheet-title">${escapeHtml(title)}</h3>
          <button class="sheet-close" aria-label="بستن">✕</button>
        </div>
        <div class="sheet-content"></div>
        ${footer ? '<div class="sheet-footer"></div>' : ''}
      </div>
    `;

    const contentEl = el.querySelector('.sheet-content');
    if (typeof content === 'string') {
      contentEl.innerHTML = content;
    } else if (content instanceof Node) {
      contentEl.appendChild(content);
    }

    // اگر محتوا یک فرم است، به آن id بده تا دکمه‌های footer بتوانند
    // با ویژگی form="" به آن وصل شوند و submit واقعاً کار کند.
    const formEl = content instanceof HTMLFormElement ? content : null;
    if (formEl && !formEl.id) {
      formEl.id = `gs-sheet-form-${++sheetSeq}`;
    }

    if (footer) {
      const footerEl = el.querySelector('.sheet-footer');
      if (typeof footer === 'string') {
        footerEl.innerHTML = footer;
      } else if (footer instanceof Node) {
        footerEl.appendChild(footer);
      }
      if (formEl) {
        footerEl.querySelectorAll('button[type="submit"]').forEach(btn => {
          btn.setAttribute('form', formEl.id);
        });
      }
    }

    const backdrop = el.querySelector('.sheet-backdrop');
    const closeBtn = el.querySelector('.sheet-close');
    const sheet = el.querySelector('.sheet');

    const close = () => closeSheet();

    backdrop.addEventListener('click', close);
    closeBtn.addEventListener('click', close);

    document.body.appendChild(el);
    document.body.style.overflow = 'hidden';

    requestAnimationFrame(() => {
      el.classList.add('open');
    });

    currentSheet = { el, close };

    return { el, close };
  }

  function closeSheet() {
    if (!currentSheet) return;
    const { el } = currentSheet;
    el.classList.remove('open');
    const cleanup = () => {
      if (el.parentNode) el.parentNode.removeChild(el);
      document.body.style.overflow = '';
    };
    // اگر transition اجرا نشد (مثلاً display:none یا بدون انیمیشن)،
    // شیت تا ابد روی صفحه می‌ماند و بقیهٔ اپ را مسدود می‌کرد.
    el.addEventListener('transitionend', cleanup, { once: true });
    setTimeout(cleanup, 300);
    currentSheet = null;
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  return {
    open: createSheet,
    close: closeSheet,
    get el() { return currentSheet?.el || null; },
  };
})();

export default SHEET;