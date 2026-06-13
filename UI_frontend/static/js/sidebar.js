// Left sidebar: New Transcript button, search, folder filter, recent list.

import { api } from './api.js';
import { el, clear, fmtDate, toast } from './util.js';

let state = { q: '', folderId: '' };
let listEl = null;
let filterEl = null;
let debounce = null;

export function renderSidebar() {
  const root = document.getElementById('sidebar');
  clear(root);

  root.appendChild(el('div', { class: 'brand' }, [
    el('div', { class: 'logo' }, 'T'),
    el('h1', {}, 'TINA Transcribe'),
  ]));

  root.appendChild(el('button', { class: 'btn-new', onclick: () => { location.hash = '#/new'; } }, [
    el('span', { class: 'plus' }, '+'),
    el('span', {}, 'New Transcript'),
  ]));

  const search = el('input', {
    type: 'text', placeholder: 'Search folders and files',
    oninput: (e) => { state.q = e.target.value; scheduleLoad(); },
  });
  root.appendChild(el('div', { class: 'search-box' }, search));

  filterEl = el('select', {
    class: 'filter-select',
    onchange: (e) => { state.folderId = e.target.value; loadList(); },
  });
  root.appendChild(filterEl);

  root.appendChild(el('div', { class: 'side-section-head' }, [
    el('span', {}, 'Latest files'),
    el('span', { class: 'link', onclick: () => { location.hash = '#/folders'; } }, 'All folders'),
  ]));

  listEl = el('div', { class: 'recent-list' });
  root.appendChild(listEl);

  root.appendChild(el('div', { class: 'side-footer' }, 'TINA Transcribe · v0.1'));

  loadFolders();
  loadList();
}

function scheduleLoad() {
  clearTimeout(debounce);
  debounce = setTimeout(loadList, 220);
}

async function loadFolders() {
  if (!filterEl) return;
  try {
    const folders = await api.listFolders();
    const current = state.folderId;
    clear(filterEl);
    filterEl.appendChild(el('option', { value: '' }, 'All folders'));
    for (const f of folders) {
      filterEl.appendChild(el('option', { value: String(f.id) }, `${f.name} (${f.count})`));
    }
    filterEl.value = current;
  } catch (e) { /* sidebar filter is non-critical */ }
}

async function loadList() {
  if (!listEl) return;
  try {
    const items = await api.listTranscriptions({ q: state.q, folder_id: state.folderId, limit: 50 });
    clear(listEl);
    if (!items.length) {
      listEl.appendChild(el('div', { class: 'empty-hint' },
        state.q ? 'No matches.' : 'No transcriptions yet.'));
      return;
    }
    const activeId = currentTranscriptionId();
    for (const t of items) {
      const item = el('div', {
        class: 'recent-item' + (t.id === activeId ? ' active' : ''),
        onclick: () => { location.hash = `#/t/${t.id}`; },
      }, [
        el('div', { class: 'name' }, t.name),
        el('div', { class: 'meta' }, [
          el('span', {}, t.folder_name),
          el('span', {}, fmtDate(t.created_at).split(',')[0]),
        ]),
      ]);
      listEl.appendChild(item);
    }
  } catch (e) {
    clear(listEl);
    listEl.appendChild(el('div', { class: 'empty-hint' }, `Could not load: ${e.message}`));
  }
}

function currentTranscriptionId() {
  const m = location.hash.match(/^#\/t\/(\d+)/);
  return m ? Number(m[1]) : null;
}

// Called by views after data changes (new folder/transcription, deletes, route change).
export function refreshSidebar() {
  loadFolders();
  loadList();
}
