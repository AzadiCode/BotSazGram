import API from '../api.js';
import TOAST from '../toast.js';
import ROUTER from '../router.js';
import SHEET from '../sheet.js';

const STUDIO_VIEW = (() => {
  let registry = null;
  let flow = null;
  let botId = null;
  let selectedNode = null;
  let selectedEdge = null;
  let edgeCreating = null;
  let validationErrors = [];
  let canvasOffset = { x: 0, y: 0 };
  let isPanning = false;
  let panStart = { x: 0, y: 0 };
  let nodes = [];
  let edges = [];
  let scale = 1;
  let container = null;

  function renderHeader() {
    return `
      <div class="studio-header">
        <div class="flex items-center gap-3">
          <button class="btn btn-ghost btn-sm" id="back-btn">← بازگشت</button>
          <span class="page-title">استودیو</span>
          ${botId ? `<span class="badge badge-neutral mx-2">@${botId.substring(0, 8)}...</span>` : ''}
        </div>
         <div class="studio-toolbar">
           <button class="btn btn-secondary btn-sm" id="save-btn">💾 ذخیره</button>
           <button class="btn btn-primary btn-sm" id="add-node-btn">➕ افزودن</button>
           ${edgeCreating ? '<button class="btn btn-danger btn-sm" id="cancel-edge-btn">✕ لغو یال</button>' : ''}
         </div>
      </div>
       <div class="flow-info-bar" id="flow-info">
         <span class="flow-info-item">🟢 ${nodes.length} کارت</span>
         <span class="flow-info-item">🔗 ${edges.length} ارتباط</span>
         ${validationErrors.length ? `<span class="flow-info-item" style="color: var(--color-danger);">⚠ ${validationErrors.length} خطا</span>` : ''}
       </div>
    `;
  }

  function render() {
    if (!container) return;

    let html = renderHeader();

    if (!registry) {
      html += '<div class="loading-state"><div class="spinner"></div>در حال بارگذاری رجیستری...</div>';
      container.innerHTML = html;
      return;
    }

    if (validationErrors.length > 0) {
      html += `
        <div class="validation-errors">
          <div class="validation-errors-title">⚠ خطاها در گراف:</div>
          ${validationErrors.map(e => `<div class="validation-error">• ${escapeHtml(e)}</div>`).join('')}
        </div>
      `;
    }

    html += `
      <div class="studio-body">
        <div class="studio-sidebar" id="palette-sidebar">
          <div class="sidebar-tabs">
            <button class="sidebar-tab active" data-tab="palette">🧩 کارت‌ها</button>
            <button class="sidebar-tab" data-tab="settings">⚙ تنظیمات</button>
          </div>
          <div class="sidebar-content">
            <div class="tab-content" id="palette-tab">
              ${renderPalette()}
            </div>
            <div class="tab-content" style="display:none;" id="settings-tab">
              ${renderSettings()}
            </div>
          </div>
        </div>
        <div class="studio-canvas">
          <div class="canvas-wrapper" id="canvas-wrapper">
            <div class="canvas-grid" id="canvas-grid"></div>
            <div class="canvas-nodes" id="canvas-nodes"></div>
            <svg class="canvas-edges" id="canvas-edges">
              <defs>
                <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                  <polygon points="0 0, 8 3.5, 0 7" fill="var(--color-border-strong)" />
                </marker>
              </defs>
            </svg>
            <div class="canvas-controls">
              <button class="canvas-btn" id="zoom-in">🔍</button>
              <button class="canvas-btn" id="zoom-out">🔬</button>
              <button class="canvas-btn" id="zoom-reset">⚪</button>
              <button class="canvas-btn" id="duplicate-btn" title="Duplicate (Ctrl+D)">📋</button>
            </div>
          </div>
          <div class="canvas-minimap" id="canvas-minimap">
            <div class="minimap-viewport" id="minimap-viewport"></div>
          </div>
        </div>
        ${selectedNode || selectedEdge || edgeCreating ? '<div class="node-properties-panel open" id="properties-panel">' + renderProperties() + '</div>' : '<div id="properties-panel-placeholder" style="display:none;"></div>'}
      </div>
    `;

    container.innerHTML = html;
    attachEvents();
    renderCanvas();
    renderEdges();
    renderMinimap();
    validationErrors = validateFlow();
  }

  function renderPalette(paletteFilter = '') {
    const categories = registry.cats;
    const filter = paletteFilter.toLowerCase().trim();

    let html = `
      <div class="palette-search">
        <input type="text" id="palette-search" class="palette-search-input" placeholder="جستجو کارت..." value="${escapeHtml(paletteFilter)}" />
      </div>
      <div class="card-palette">
    `;

    const byCategory = {};
    for (const [kind, card] of Object.entries(registry.cards)) {
      if (card.cat === 'int') continue;
      if (filter && !kind.toLowerCase().includes(filter) && !card.label.toLowerCase().includes(filter)) continue;
      if (!byCategory[card.cat]) byCategory[card.cat] = [];
      byCategory[card.cat].push({ kind, ...card });
    }

    let noResults = filter && Object.keys(byCategory).every(c => byCategory[c].length === 0);

    for (const [catId, catLabel] of Object.entries(categories)) {
      if (!byCategory[catId] || byCategory[catId].length === 0) continue;
      html += `<div class="palette-category">`;
      html += `<div class="palette-category-title">${catLabel}</div>`;
      html += `<div class="palette-items">`;
      for (const card of byCategory[catId]) {
        html += `
          <div class="palette-item" data-card-kind="${card.kind}" draggable="true">
            <span class="palette-item-icon">${getCardIcon(card.kind)}</span>
            <span class="palette-item-label">${card.label}</span>
          </div>
        `;
      }
      html += `</div></div>`;
    }

    html += '</div>';
    return html;
  }

  function getCardIcon(kind) {
    const icons = {
      cmd: '⧉',
      reply: '↩',
      image: '🖼',
      album: '📚',
      link: '🔗',
      ticket: '🎫',
      trigger: '🔍',
      input: '⌨',
      menu: '☰',
      keyboard: '⌨',
      condition: '?',
      setvar: '⊚',
      random: '🎲',
      notify: '🔔',
      delay: '⏱',
      api: '🌐',
      ai: '🧠',
    };
    return icons[kind] || '•';
  }

   function renderSettings() {
    const aiSection = registry && (botId
      ? `<div class="input-group">
          <label>هوش مصنوعی</label>
          <div class="ai-status" id="ai-status">
            <div class="spinner" style="display:none"></div>
            <span>در حال بارگذاری...</span>
          </div>
        </div>`
      : '');
    return `
      <div class="input-group">
        <label>نام ربات</label>
        <input type="text" id="bot-name" placeholder="نام ربات...">
      </div>
      <div class="input-group">
        <label>توکن ربات</label>
        <input type="text" id="bot-token" placeholder="توکن..." disabled>
      </div>
      ${aiSection}
    `;
  }

  function renderProperties() {
    if (selectedEdge) {
      const headerHtml = `
        <div class="properties-header">
          <h3 class="properties-title">🔗 یال</h3>
          <button class="sheet-close" id="close-properties">✕</button>
        </div>
      `;
      const content = `
        <div class="properties-content">
          <div class="property-row">
            <span class="property-label">از</span>
            <span class="property-value" style="direction: ltr;">${escapeHtml(selectedEdge.from)}</span>
          </div>
          <div class="property-row">
            <span class="property-label">به</span>
            <span class="property-value" style="direction: ltr;">${escapeHtml(selectedEdge.to)}</span>
          </div>
          <div class="property-row">
            <span class="property-label">پورت مبدأ</span>
            <span class="property-value">${escapeHtml(selectedEdge.from_port || 'run')}</span>
          </div>
          <div class="property-row">
            <span class="property-label">پورت مقصد</span>
            <span class="property-value">${escapeHtml(selectedEdge.to_port || 'run')}</span>
          </div>
          <div class="property-row">
            <button class="btn btn-danger btn-sm" id="delete-edge-btn" style="width: 100%;">🗑 حذف یال</button>
          </div>
        </div>
      `;
      return headerHtml + content;
    }

    if (edgeCreating) {
      return `
        <div class="properties-header">
          <h3 class="properties-title">➕ در حال ساخت یال</h3>
          <button class="sheet-close" id="close-properties">✕</button>
        </div>
        <div class="properties-content">
          <div class="text-muted">روی یک پورت دیگر کلیک کنید یا Esc را بزنید</div>
        </div>
      `;
    }

    if (!selectedNode) {
      return `
        <div class="properties-empty">
          <div class="properties-empty-icon">⚙</div>
          <div class="properties-empty-title">هیچ کارتی انتخاب نشده</div>
          <div class="properties-empty-desc">کارتی را انتخاب کنید یا روی یک پورت کلیک کنید تا یال بکشید</div>
        </div>
      `;
    }

    const cardDef = registry.cards[selectedNode.kind];
    if (!cardDef) {
      return '<div class="properties-content"><div class="text-muted">کارت ناشناس</div></div>';
    }

    let fieldsHtml = '';
    for (const field of cardDef.fields) {
      const value = selectedNode[field.name] ?? field.default ?? '';
      fieldsHtml += `
        <div class="node-field">
          <label class="node-field-label">
            ${escapeHtml(field.label)}
            ${field.required ? '<span class="node-field-required">*</span>' : ''}
          </label>
          ${renderField(field, value)}
        </div>
      `;
    }

    const headerHtml = `
      <div class="properties-header">
        <h3 class="properties-title">${cardDef.label}</h3>
        <button class="sheet-close" id="close-properties">✕</button>
      </div>
    `;

    return headerHtml + `<div class="properties-content">${fieldsHtml}</div>`;
  }

  function renderField(field, value) {
    switch (field.type) {
      case 'bool':
        return `
          <label class="switch">
            <input type="checkbox" data-field="${field.name}" ${value ? 'checked' : ''}>
            <span class="switch-slider"></span>
          </label>
        `;
      case 'enum':
        return `
          <select data-field="${field.name}" class="node-field-select">
            ${field.options.map(opt => `<option value="${opt}" ${opt === value ? 'selected' : ''}>${capitalize(opt)}</option>`).join('')}
          </select>
        `;
      case 'number':
        return `<input type="number" data-field="${field.name}" min="${field.min || 0}" max="${field.max || ''}" value="${value}" class="node-field-input">`;
      case 'text':
      case 'string':
      case 'ident':
      case 'url':
        return `<input type="text" data-field="${field.name}" value="${escapeHtml(String(value))}" placeholder="${escapeHtml(field.label)}" class="node-field-input">`;
      case 'strlist':
        return `<input type="text" data-field="${field.name}" value="${escapeHtml(String(Array.isArray(value) ? value.join(', ') : value))}" placeholder="کاما جدا شده" class="node-field-input">`;
      default:
        return `<input type="text" data-field="${field.name}" value="${escapeHtml(String(value))}" class="node-field-input">`;
    }
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function capitalize(s) {
    const translations = {
      exact: 'دقیق',
      contains: 'شامل شونده',
      regex: 'الگو',
      default: 'پیش‌فرض',
      glass: 'شیشه‌ای',
      persistent: 'دائمی',
      popup: 'شناور',
      inline: 'اینلاین',
      reply: 'زیر صفحه چت',
      new: 'جدید',
      edit: 'ویرایش',
      HTML: 'HTML',
      Markdown: 'Markdown',
      none: 'بدون قالب',
      GET: 'دریافت',
      POST: 'ارسال',
      url: 'آدرس',
      webapp: 'مینیوب‌اپ',
      share: 'اشتراک',
      single: 'تک‌کاربره',
      group: 'گروهی',
      low: 'پایین',
      normal: 'معمولی',
      high: 'بالا',
    };
    return translations[s] || s;
  }

  function renderCanvas() {
    const nodesContainer = container?.querySelector('#canvas-nodes');
    if (!nodesContainer) return;

    nodesContainer.innerHTML = '';

    for (const node of nodes) {
      const el = document.createElement('div');
      el.className = 'canvas-node';
      if (node.id === selectedNode?.id) el.classList.add('selected');
      el.style.left = `${node.x}px`;
      el.style.top = `${node.y}px`;
      el.dataset.nodeId = node.id;
      el.dataset.nodeKind = node.kind;

      const cardDef = registry.cards[node.kind];
      const ports = cardDef ? cardDef.ports || [{ id: 'run', label: 'run' }] : [{ id: 'run', label: 'run' }];

      el.innerHTML = `
        <div class="node-header" draggable="true">
          <span class="node-type-badge ${cardDef?.cat || 'msg'}">${getCardIcon(node.kind)}</span>
          <div class="node-id">${escapeHtml(String(node.kind))}: ${escapeHtml(String(node.id))}</div>
          <button class="node-delete" data-node-id="${node.id}" aria-label="حذف">✕</button>
        </div>
        <div class="node-body">
          <div class="node-ports">
            ${ports.map(p => `
              <div class="node-port">
                <span class="text-muted">${escapeHtml(p.label || p.id)}</span>
                <div class="port-connections" data-node-id="${node.id}" data-port="${p.id}">
                  ${getConnectedEdges(node.id, p.id).map(e => `<span class="port-connection">🔗</span>`).join('')}
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `;

      nodesContainer.appendChild(el);
    }
  }

  function getConnectedEdges(nodeId, portId) {
    return edges.filter(e =>
      (e.from === nodeId && e.from_port === portId) ||
      (e.to === nodeId && e.to_port === portId)
    );
  }

  function renderEdges() {
    const svg = container?.querySelector('#canvas-edges');
    if (!svg) return;

    svg.innerHTML = `
      <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 8 3.5, 0 7" fill="var(--color-border-strong)" />
        </marker>
      </defs>
    `;

    if (edgeCreating) {
      const fromNode = nodes.find(n => n.id === edgeCreating.nodeId);
      if (fromNode) {
        const fromEl = container?.querySelector(`[data-node-id="${edgeCreating.nodeId}"]`);
        if (fromEl) {
          const fromRect = fromEl.getBoundingClientRect();
          const canvasRect = container?.querySelector('.canvas-nodes').getBoundingClientRect();
          if (canvasRect) {
            const x1 = fromRect.right - canvasRect.left;
            const y1 = fromRect.top + fromRect.height / 2 - canvasRect.top;
            const x2 = x1 + 100;
            const y2 = y1;
            const dashPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            dashPath.className = 'edge-path creating';
            dashPath.setAttribute('d', `M ${x1} ${y1} L ${x2} ${y2}`);
            dashPath.style.strokeDasharray = '5,5';
            svg.appendChild(dashPath);
          }
        }
      }
    }

    for (const edge of edges) {
      const sourceNode = nodes.find(n => n.id === edge.from);
      const targetNode = nodes.find(n => n.id === edge.to);
      if (!sourceNode || !targetNode) continue;

      const sourceEl = container?.querySelector(`[data-node-id="${edge.from}"]`);
      const targetEl = container?.querySelector(`[data-node-id="${edge.to}"]`);
      if (!sourceEl || !targetEl) continue;

      const sourceRect = sourceEl.getBoundingClientRect();
      const targetRect = targetEl.getBoundingClientRect();
      const canvasRect = container?.querySelector('.canvas-nodes').getBoundingClientRect();

      if (!canvasRect) continue;

      const x1 = sourceRect.right - canvasRect.left;
      const y1 = sourceRect.top + sourceRect.height / 2 - canvasRect.top;
      const x2 = targetRect.left - canvasRect.left;
      const y2 = targetRect.top + targetRect.height / 2 - canvasRect.top;

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.className = 'edge-path' + (edge === selectedEdge ? ' selected' : '');
      path.setAttribute('d', `M ${x1} ${y1} C ${(x1+x2)/2} ${y1}, ${(x1+x2)/2} ${y2}, ${x2} ${y2}`);
      path.style.cursor = 'pointer';
      path.addEventListener('click', (e) => {
        e.stopPropagation();
        selectedEdge = edge;
        selectedNode = null;
        render();
      });
      svg.appendChild(path);
    }

    renderMinimap();
  }

  function validateFlow() {
    const errors = [];
    if (nodes.length === 0) {
      errors.push('گراف خالی است — کارتی اضافه کنید');
      return errors;
    }

    const cmdNodes = nodes.filter(n => n.kind === 'cmd');
    if (cmdNodes.length > 0) {
      const names = new Set();
      cmdNodes.forEach(n => {
        const name = n.name || n.command;
        if (!name) {
          errors.push(`کارت دستور "${n.id}" نام ندارد`);
        } else if (names.has(name)) {
          errors.push(`نام دستور تکراری: "${escapeHtml(name)}"`);
        } else {
          names.add(name);
        }
      });
    }

    const nodeIds = new Set(nodes.map(n => n.id));
    edges.forEach((e, i) => {
      if (!nodeIds.has(e.from)) errors.push(`یال ${i + 1}: مبدأ یافت نشد (${e.from})`);
      if (!nodeIds.has(e.to)) errors.push(`یال ${i + 1}: مقصد یافت نشد (${e.to})`);
    });

    if (nodes.length > 200) errors.push(`تعداد نودها بیش از حد مجاز (${nodes.length} > 200)`);
    if (edges.length > 500) errors.push(`تعداد یال‌ها بیش از حد مجاز (${edges.length} > 500)`);

    return errors;
  }

  function renderMinimap() {
    const minimap = container?.querySelector('#canvas-minimap');
    const viewport = container?.querySelector('#minimap-viewport');
    if (!minimap || !viewport || !registry) return;

    let dots = '';
    const nodeRadius = 2;
    const edgeColor = getComputedStyle(document.documentElement).getPropertyValue('--color-border-strong');

    if (nodes.length === 0) {
      minimap.innerHTML = '<div style="padding:4px;font-size:10px;color:var(--color-text-muted)">خالی</div>';
      return;
    }

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    nodes.forEach(n => {
      minX = Math.min(minX, n.x);
      minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x);
      maxY = Math.max(maxY, n.y);
    });
    const margin = 20;
    minX -= margin; minY -= margin;
    maxX += margin; maxY += margin;
    const width = Math.max(maxX - minX, 1);
    const height = Math.max(maxY - minY, 1);
    const scale = Math.min(130 / width, 80 / height);

    const offsetX = -minX * scale;
    const offsetY = -minY * scale;

    let svgContent = `<svg width="150" height="100" style="width:100%;height:100%">`;
    svgContent += `<rect width="150" height="100" fill="var(--color-bg)" />`;

    edges.forEach(e => {
      const fromNode = nodes.find(n => n.id === e.from);
      const toNode = nodes.find(n => n.id === e.to);
      if (!fromNode || !toNode) return;
      const x1 = fromNode.x * scale + offsetX + 10;
      const y1 = fromNode.y * scale + offsetY + 10;
      const x2 = toNode.x * scale + offsetX + 10;
      const y2 = toNode.y * scale + offsetY + 10;
      svgContent += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${edgeColor}" stroke-width="1" />`;
    });

    nodes.forEach(n => {
      const cx = n.x * scale + offsetX + 10;
      const cy = n.y * scale + offsetY + 10;
      const color = n.kind === 'cmd' ? '#22c56e' : n.kind === 'condition' ? '#f59e0b' : '#6b7280';
      svgContent += `<circle cx="${cx}" cy="${cy}" r="${nodeRadius}" fill="${color}" />`;
    });

    svgContent += '</svg>';
    minimap.innerHTML = svgContent;

    const viewportRect = minimap.querySelector('svg')?.getBoundingClientRect();
    if (viewportRect) {
      viewport.style.width = `${viewportRect.width}px`;
      viewport.style.height = `${viewportRect.height}px`;
    }
  }

  async function loadFlow() {
    try {
      const flow = await API.get(`/api/bots/${botId}/flow`);
      nodes = flow.nodes || [];
      edges = flow.edges || [];
      for (const node of nodes) {
        if (typeof node.x === 'undefined') node.x = 100;
        if (typeof node.y === 'undefined') node.y = 100;
      }
    } catch (e) {
      if (e.status === 404) {
        nodes = [];
        edges = [];
      } else {
        TOAST.error('خطا در بارگذاری گراف: ' + e.message);
      }
    }
  }

  function attachEvents() {
    const backBtn = container?.querySelector('#back-btn');
    backBtn?.addEventListener('click', () => ROUTER.navigate('/bots'));

    const saveBtn = container?.querySelector('#save-btn');
    saveBtn?.addEventListener('click', saveFlow);

    const aiStatus = container?.querySelector('#ai-status');
    if (aiStatus && botId) {
      loadAiConfig(aiStatus);
    }

    const addBtn = container?.querySelector('#add-node-btn');
    addBtn?.addEventListener('click', showAddNodeSheet);

    const paletteItems = container?.querySelectorAll('.palette-item');
    paletteItems.forEach(item => {
      item.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('application/json', JSON.stringify({
          kind: item.dataset.cardKind,
        }));
        item.classList.add('dragging');
      });
      item.addEventListener('dragend', () => item.classList.remove('dragging'));
    });

    const paletteSearch = container?.querySelector('#palette-search');
    paletteSearch?.addEventListener('input', (e) => {
      const filter = e.target.value;
      const html = renderPalette(filter);
      const tab = container?.querySelector('#palette-tab');
      if (tab) {
        tab.innerHTML = html;
        const items = tab.querySelectorAll('.palette-item');
        items.forEach(item => {
          item.addEventListener('dragstart', (ev) => {
            ev.dataTransfer.setData('application/json', JSON.stringify({
              kind: item.dataset.cardKind,
            }));
            item.classList.add('dragging');
          });
          item.addEventListener('dragend', () => item.classList.remove('dragging'));
        });
      }
    });

    const canvasWrapper = container?.querySelector('#canvas-wrapper');
    if (canvasWrapper) {
      canvasWrapper.addEventListener('dragover', (e) => e.preventDefault());
      canvasWrapper.addEventListener('drop', (e) => {
        e.preventDefault();
        const data = JSON.parse(e.dataTransfer.getData('application/json'));
        const rect = canvasWrapper.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        addNode(data.kind, x, y);
      });
      canvasWrapper.addEventListener('mousedown', startPan);
      canvasWrapper.addEventListener('mousemove', doPan);
      canvasWrapper.addEventListener('mouseup', endPan);
      canvasWrapper.addEventListener('click', (e) => {
        if (e.target === canvasWrapper) {
          selectedNode = null;
          selectedEdge = null;
          edgeCreating = null;
          render();
        }
      });
    }

    const tabButtons = container?.querySelectorAll('.sidebar-tab');
    tabButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.dataset.tab;
        container?.querySelectorAll('.sidebar-tab').forEach(b => b.classList.remove('active'));
        container?.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
        btn.classList.add('active');
        container?.querySelector(`#${tab}-tab`)?.style?.setProperty('display', 'block');
      });
    });

    const closeProps = container?.querySelector('#close-properties');
    closeProps?.addEventListener('click', () => {
      selectedNode = null;
      selectedEdge = null;
      edgeCreating = null;
      render();
    });

    const nodeHeaders = container?.querySelectorAll('.node-header');
    nodeHeaders.forEach(header => {
      header.addEventListener('mousedown', startNodeDrag);
    });

    const deleteBtns = container?.querySelectorAll('.node-delete');
    deleteBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        deleteNode(btn.dataset.nodeId);
      });
    });

    const nodeClickHandlers = container?.querySelectorAll('.canvas-node');
    nodeClickHandlers.forEach(nodeEl => {
      nodeEl.addEventListener('click', (e) => {
        e.stopPropagation();
        if (edgeCreating) return;
        const nodeId = nodeEl.dataset.nodeId;
        selectedNode = nodes.find(n => n.id === nodeId) || null;
        selectedEdge = null;
        render();
      });
    });

    const fieldInputs = container?.querySelectorAll('[data-field]');
    fieldInputs.forEach(input => {
      input.addEventListener('change', () => {
        const fieldName = input.dataset.field;
        if (!fieldName || !selectedNode) return;
        if (input.type === 'checkbox') {
          selectedNode[fieldName] = input.checked;
        } else if (input.type === 'number') {
          selectedNode[fieldName] = parseFloat(input.value) || 0;
        } else {
          selectedNode[fieldName] = input.value;
        }
        render();
      });
    });

    const portElements = container?.querySelectorAll('.port-connections');
    portElements.forEach(port => {
      port.addEventListener('click', (e) => {
        e.stopPropagation();
        e.preventDefault();
        handlePortClick(port.dataset.nodeId, port.dataset.port);
      });
    });

    if (selectedEdge) {
      const deleteEdgeBtn = container?.querySelector('#delete-edge-btn');
      deleteEdgeBtn?.addEventListener('click', deleteSelectedEdge);
    }

    const cancelEdgeBtn = container?.querySelector('#cancel-edge-btn');
    cancelEdgeBtn?.addEventListener('click', () => {
      edgeCreating = null;
      render();
    });

    document.addEventListener('keydown', handleKeydown);

    const zoomIn = container?.querySelector('#zoom-in');
    const zoomOut = container?.querySelector('#zoom-out');
    const zoomReset = container?.querySelector('#zoom-reset');

    zoomIn?.addEventListener('click', () => { scale = Math.min(scale * 0.9, 2); updateScale(); });
    zoomOut?.addEventListener('click', () => { scale = Math.max(scale * 1.1, 0.3); updateScale(); });
    zoomReset?.addEventListener('click', () => { scale = 1; updateScale(); });

    const dupBtn = container?.querySelector('#duplicate-btn');
    dupBtn?.addEventListener('click', () => {
      if (!selectedNode) return;
      duplicateNode(selectedNode);
    });

    document.removeEventListener('keydown', handleKeydown);
    document.addEventListener('keydown', handleKeydown);
  }

  function handlePortClick(nodeId, portId) {
    if (edgeCreating) {
      if (edgeCreating.nodeId === nodeId) {
        edgeCreating = null;
        render();
        return;
      }
      addEdge(edgeCreating.nodeId, edgeCreating.portId, nodeId, portId);
      edgeCreating = null;
      render();
    } else {
      edgeCreating = { nodeId, portId };
      render();
    }
  }

  function addEdge(fromNodeId, fromPort, toNodeId, toPort) {
    if (fromNodeId === toNodeId) return;
    const exists = edges.some(e =>
      e.from === fromNodeId && e.to === toNodeId &&
      (e.from_port || 'run') === (fromPort || 'run') &&
      (e.to_port || 'run') === (toPort || 'run')
    );
    if (exists) return;
    edges.push({
      from: fromNodeId,
      to: toNodeId,
      from_port: fromPort || 'run',
      to_port: toPort || 'run',
    });
  }

  function deleteSelectedEdge() {
    if (!selectedEdge) return;
    edges = edges.filter(e => e !== selectedEdge);
    selectedEdge = null;
    render();
  }

  function duplicateNode(node) {
    const newNodeId = `n${Date.now()}`;
    const newNode = { ...node, id: newNodeId, x: node.x + 30, y: node.y + 30 };
    nodes.push(newNode);
    selectedNode = newNode;
    selectedEdge = null;
    edgeCreating = null;
    render();
  }

  function handleKeydown(e) {
    if (!container) return;
    if (e.key === 'Escape') {
      if (edgeCreating) { edgeCreating = null; render(); return; }
      if (selectedNode) { selectedNode = null; }
      if (selectedEdge) { selectedEdge = null; }
      render();
    }
    if (e.key === 'Delete') {
      if (selectedEdge) {
        edges = edges.filter(e => e !== selectedEdge);
        selectedEdge = null;
        render();
        return;
      }
      if (selectedNode) {
        deleteNode(selectedNode.id);
      }
    }
    if (e.key === 'd' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      if (selectedNode) {
        duplicateNode(selectedNode);
      }
    }
  }

  function startPan(e) {
    if (e.target.closest('.canvas-node')) return;
    isPanning = true;
    panStart = { x: e.clientX, y: e.clientY };
  }

  function doPan(e) {
    if (!isPanning) return;
    // جابجایی نسبی به آخرین موقعیت موس — وگرنه با هر حرکت،
    // جابجایی از نقطهٔ شروع دوباره انباشته می‌شد.
    const dx = e.clientX - panStart.x;
    const dy = e.clientY - panStart.y;
    panStart = { x: e.clientX, y: e.clientY };
    canvasOffset.x += dx;
    canvasOffset.y += dy;
    applyCanvasTransform();
  }

  function endPan() {
    isPanning = false;
  }

  function applyCanvasTransform() {
    const nodesContainer = container?.querySelector('.canvas-nodes');
    if (nodesContainer) {
      nodesContainer.style.transform =
        `translate(${canvasOffset.x}px, ${canvasOffset.y}px) scale(${scale})`;
    }
  }

  function updateScale() {
    applyCanvasTransform();
  }

  function startNodeDrag(e) {
    e.stopPropagation();
    const nodeEl = e.target.closest('.canvas-node');
    const nodeId = nodeEl?.dataset?.nodeId;
    if (!nodeId) return;

    const node = nodes.find(n => n.id === nodeId);
    if (!node) return;

    nodeEl.classList.add('dragging');

    // فاصلهٔ نقطهٔ کلیک تا گوشهٔ کارت (در فضای صفحه، شامل pan/zoom)
    const nodeRect = nodeEl.getBoundingClientRect();
    const offsetX = e.clientX - nodeRect.left;
    const offsetY = e.clientY - nodeRect.top;

    const onMouseMove = (ev) => {
      ev.preventDefault();
      // جابجایی دلخواه موس اعمال می‌شود — نه انتقال مطلق.
      // بدون این اصلاح، کارت با هر حرکت موس پرتاب می‌شد.
      node.x += ev.movementX;
      node.y += ev.movementY;
      nodeEl.style.left = `${node.x}px`;
      nodeEl.style.top = `${node.y}px`;
    };

    const onMouseUp = () => {
      nodeEl.classList.remove('dragging');
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      renderEdges();
      renderMinimap();
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }

  function addNode(kind, x, y) {
    const nodeId = `n${Date.now()}`;
    const newNode = {
      id: nodeId,
      kind: kind,
      x: x,
      y: y,
      ...registry.cards[kind].fields.reduce((acc, f) => {
        acc[f.name] = f.default ?? (f.type === 'bool' ? false : '');
        return acc;
      }, {}),
    };
    nodes.push(newNode);
    selectedNode = newNode;
    render();
  }

  function deleteNode(nodeId) {
    nodes = nodes.filter(n => n.id !== nodeId);
    edges = edges.filter(e => e.from !== nodeId && e.to !== nodeId);
    if (selectedNode?.id === nodeId) selectedNode = null;
    if (selectedEdge?.from === nodeId || selectedEdge?.to === nodeId) selectedEdge = null;
    render();
  }

  function showAddNodeSheet() {
    let html = '<div class="card-palette">';
    for (const [kind, card] of Object.entries(registry.cards)) {
      if (card.cat === 'int') continue;
      html += `
        <div class="palette-item" data-card-kind="${kind}" style="cursor: pointer;">
          <span class="palette-item-icon">${getCardIcon(kind)}</span>
          <span class="palette-item-label">${escapeHtml(card.label)}</span>
        </div>
      `;
    }
    html += '</div>';

    const sheet = SHEET.open(html, { title: 'افزودن کارت' });
    if (sheet) {
      const items = sheet.el.querySelectorAll('[data-card-kind]');
      items.forEach(item => {
        item.addEventListener('click', () => {
          addNode(item.dataset.cardKind, 200, 200);
          SHEET.close();
        });
      });
    }
  }

  async function loadAiConfig(aiStatusEl) {
    if (!botId) return;
    try {
      const cfg = await API.get(`/api/bots/${botId}/ai-config`);
      const hasKey = cfg.has_api_key;
      const keyDisplay = hasKey ? '•••••••• متصل ✅' : '🔓 وصل نشده';
      aiStatusEl.innerHTML = `
        <div class="ai-config-summary">
          <div class="ai-key-status ${hasKey ? 'configured' : 'not-configured'}">${keyDisplay}</div>
          <div class="ai-model">${escapeHtml(cfg.model || '')}</div>
        </div>
        <button class="btn btn-ghost btn-sm" id="edit-ai-btn" style="margin-top: var(--spacing-2);">✏️ ویرایش</button>
      `;
      const editBtn = aiStatusEl.querySelector('#edit-ai-btn');
      editBtn?.addEventListener('click', () => showAiConfigSheet(cfg));
    } catch (e) {
      aiStatusEl.innerHTML = '<span class="text-muted">خطا در بارگذاری</span>';
    }
  }

  function showAiConfigSheet(currentCfg) {
    const form = document.createElement('form');
    form.innerHTML = `
      <div class="input-group">
        <label>کلید API</label>
        <input type="password" name="api_key" placeholder="sk-..." autocomplete="off" ${currentCfg.has_api_key ? 'value="••••••••"' : ''}>
        <div class="input-hint">کلید OpenAI یا سرویس سازگار (در صورت وارد کردن، جایگزین می‌شود)</div>
      </div>
      <div class="input-group">
        <label>آدرس سرور</label>
        <input type="url" name="base_url" placeholder="https://api.openai.com/v1" value="${escapeHtml(currentCfg.base_url || '')}">
      </div>
      <div class="input-group">
        <label>مدل</label>
        <input type="text" name="model" placeholder="gpt-4o-mini" value="${escapeHtml(currentCfg.model || '')}">
      </div>
    `;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {};
      if (form.api_key.value.trim() && !form.api_key.value.includes('•')) {
        payload.api_key = form.api_key.value.trim();
      }
      if (form.base_url.value.trim()) {
        payload.base_url = form.base_url.value.trim();
      }
      if (form.model.value.trim()) {
        payload.model = form.model.value.trim();
      }
      if (!Object.keys(payload).length) {
        TOAST.error('هیچ تغییری نیست');
        return;
      }
      const submitBtn = SHEET.el?.querySelector('.sheet-footer button[type="submit"]');
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'در حال ذخیره...';
      }
      try {
        await API.patch(`/api/bots/${botId}/ai-config`, payload);
        TOAST.success('تنظیمات AI ذخیره شد');
        SHEET.close();
        const aiStatus = container?.querySelector('#ai-status');
        if (aiStatus) loadAiConfig(aiStatus);
      } catch (err) {
        TOAST.error('خطا: ' + err.message);
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = 'ذخیره';
        }
      }
    });

    SHEET.open(form, {
      title: 'تنظیمات هوش مصنوعی',
      footer: `
        <button type="button" class="btn btn-secondary" onclick="this.closest('.sheet-root').querySelector('.sheet-close').click()">انصراف</button>
        <button type="submit" form="${form.id || ''}" class="btn btn-primary">ذخیره</button>
      `,
    });

    form.querySelector('input[name="api_key"]').focus();
  }

  async function saveFlow() {
    if (!registry || !botId) return;

    validationErrors = validateFlow();

    const graph = {
      // مختصات کارت‌ها نگه داشته می‌شوند تا چیدمان بعد از بارگذاری
      // دوباره به هم نریزد (بک‌اند clean_flow این دو فیلد را می‌پذیرد).
      nodes: nodes.map(n => ({ ...n })),
      edges: edges.map(e => {
        const out = { from: e.from, to: e.to };
        if (e.from_port) out.from_port = e.from_port;
        if (e.to_port) out.to_port = e.to_port;
        return out;
      }),
    };

    try {
      await API.put(`/api/bots/${botId}/flow`, graph);
      validationErrors = [];
      TOAST.success('گراف با موفقیت ذخیره شد');
      render();
    } catch (e) {
      validationErrors = [e.message || 'خطا در ذخیره گراف'];
      TOAST.error('خطا در ذخیره: ' + e.message);
      render();
    }
  }

  async function init(el, id) {
    container = el;
    botId = id;

    // ریست کامل وضعیت — وگرنه کارت‌های ربات قبلی روی ربات جدید می‌مانند
    nodes = [];
    edges = [];
    selectedNode = null;
    selectedEdge = null;
    edgeCreating = null;
    validationErrors = [];
    scale = 1;

    await loadFlow();
    registry = await API.get('/api/flow/registry').catch(e => {
      TOAST.error('خطا در بارگذاری رجیستری: ' + e.message);
      return null;
    });
    render();
  }

  return { init, loadFlow };
})();

export default STUDIO_VIEW;