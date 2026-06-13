// New Transcript flow. The upload drop zone + transcribe wiring arrive in TODO
// item 3; for now this establishes the folder target: the breadcrumb shows the
// active folder, and the "Save to folder" picker (defaulting to it) keeps them in sync.

import { api } from './api.js';
import { getActiveFolderId, setActiveFolderId, resolveActiveFolder } from './state.js';
import { el, clear } from './util.js';

export async function renderNewTranscript(root) {
  clear(root);

  let folders = [];
  try { folders = await api.listFolders(); } catch {}
  const active = resolveActiveFolder(folders);
  // Persist the resolved fallback so the rest of the app agrees on the active folder.
  if (active && getActiveFolderId() !== active.id) setActiveFolderId(active.id);

  const folderNameEl = el('span', {}, active ? active.name : '—');
  root.appendChild(el('div', { class: 'breadcrumb' }, [
    el('a', { onclick: () => { location.hash = '#/folders'; } }, 'Folders'),
    document.createTextNode(' / '),
    folderNameEl,
    document.createTextNode(' / New Transcript'),
  ]));

  root.appendChild(el('div', { class: 'page-head' }, el('h2', {}, 'New Transcript')));

  // Save-to-folder picker — defaults to the active folder, updates the breadcrumb.
  const select = el('select', {
    class: 'filter-select', style: 'max-width:320px',
    onchange: (e) => {
      const id = Number(e.target.value);
      setActiveFolderId(id);
      const f = folders.find(x => x.id === id);
      folderNameEl.textContent = f ? f.name : '—';
    },
  }, folders.map(f => el('option', { value: String(f.id) }, f.name)));
  if (active) select.value = String(active.id);

  root.appendChild(el('div', { class: 'settings-row' }, [
    el('label', {}, 'Save to folder'),
    select,
  ]));

  root.appendChild(el('div', { class: 'placeholder' },
    'Upload + transcription settings are coming in the next step (TODO item 3).'));
}
