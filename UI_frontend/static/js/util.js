// Small shared helpers.

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null) continue;
    node.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return node;
}

export function clear(node) { node.replaceChildren(); return node; }

export function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString(undefined, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function fmtDur(s) {
  if (s == null) return '';
  const m = Math.floor(s / 60), sec = Math.round(s % 60);
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
}

const LANG_LABELS = { nld: 'Dutch', fry: 'Frisian', 'nld+fry': 'Dutch + Frisian' };
export const langLabel = (l) => LANG_LABELS[l] || l || '';

let toastTimer = null;
export function toast(msg) {
  let t = document.querySelector('.toast');
  if (!t) { t = el('div', { class: 'toast' }); document.body.appendChild(t); }
  t.textContent = msg;
  requestAnimationFrame(() => t.classList.add('show'));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
}

// Minimal prompt modal returning a Promise<string|null>.
export function promptModal({ title, label, value = '', confirmText = 'Save' }) {
  return new Promise((resolve) => {
    const input = el('input', { type: 'text', value, placeholder: label || '' });
    const close = (result) => { backdrop.remove(); resolve(result); };
    const backdrop = el('div', { class: 'modal-backdrop', onclick: (e) => { if (e.target === backdrop) close(null); } }, [
      el('div', { class: 'modal' }, [
        el('h3', {}, title),
        input,
        el('div', { class: 'modal-actions' }, [
          el('button', { class: 'btn btn-secondary', onclick: () => close(null) }, 'Cancel'),
          el('button', { class: 'btn', onclick: () => close(input.value.trim() || null) }, confirmText),
        ]),
      ]),
    ]);
    document.body.appendChild(backdrop);
    input.focus();
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') close(input.value.trim() || null);
      if (e.key === 'Escape') close(null);
    });
  });
}

export function confirmModal({ title, confirmText = 'Delete', danger = true }) {
  return new Promise((resolve) => {
    const close = (r) => { backdrop.remove(); resolve(r); };
    const backdrop = el('div', { class: 'modal-backdrop', onclick: (e) => { if (e.target === backdrop) close(false); } }, [
      el('div', { class: 'modal' }, [
        el('h3', {}, title),
        el('div', { class: 'modal-actions' }, [
          el('button', { class: 'btn btn-secondary', onclick: () => close(false) }, 'Cancel'),
          el('button', { class: `btn ${danger ? 'btn-secondary btn-danger' : ''}`, onclick: () => close(true) }, confirmText),
        ]),
      ]),
    ]);
    document.body.appendChild(backdrop);
  });
}
