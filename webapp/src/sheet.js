const SHEET = (() => {
  const root = document.getElementById('sheet-root');
  let currentSheet = null;

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

    if (footer) {
      const footerEl = el.querySelector('.sheet-footer');
      if (typeof footer === 'string') {
        footerEl.innerHTML = footer;
      } else if (footer instanceof Node) {
        footerEl.appendChild(footer);
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
    const { el, close } = currentSheet;
    el.classList.remove('open');
    el.addEventListener('transitionend', () => {
      if (el.parentNode) el.parentNode.removeChild(el);
      document.body.style.overflow = '';
    }, { once: true });
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
  };
})();

export default SHEET;