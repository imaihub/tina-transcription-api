// Folders overview: table of folders, expandable to their transcriptions.

import { api } from './api.js';
import { refreshSidebar } from './sidebar.js';
import { el, clear, fmtDate, fmtDur, toast, promptModal, confirmModal } from './util.js';

const FOLDER_SVG = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
const expanded = new Set();

export async function renderFolders(root) {
  clear(root);

  root.appendChild(el('div', { class: 'page-head' }, [
    el('h2', {}, 'Folders'),
    el('button', { class: 'btn', onclick: onNewFolder }, '+ New Folder'),
  ]));

  let folders;
  try {
    folders = await api.listFolders();
  } catch (e) {
    root.appendChild(el('div', { class: 'placeholder' }, `Could not load folders: ${e.message}`));
    return;
  }

  const table = el('table', {}, [
    el('thead', {}, el('tr', {}, [
      el('th', {}, 'Name'),
      el('th', {}, 'Created'),
      el('th', { class: 'right' }, 'Actions'),
    ])),
  ]);
  const tbody = el('tbody');
  table.appendChild(tbody);
  root.appendChild(table);

  for (const f of folders) {
    tbody.appendChild(folderRow(f, tbody));
    if (expanded.has(f.id)) await appendChildren(tbody, f);
  }
}

function folderRow(f, tbody) {
  const row = el('tr', { class: 'folder-row' + (expanded.has(f.id) ? ' open' : ''), 'data-id': f.id }, [
    el('td', {}, el('div', { class: 'folder-name' }, [
      el('span', { class: 'chev' }, '›'),
      el('span', { class: 'folder-icon', html: FOLDER_SVG }),
      el('span', {}, `${f.name} (${f.count})`),
    ])),
    el('td', {}, fmtDate(f.created_at)),
    el('td', { class: 'right' }, el('div', { class: 'row-actions' }, [
      el('button', { class: 'btn-ghost', title: 'Rename', onclick: (e) => { e.stopPropagation(); onRename(f); } }, 'Rename'),
      el('button', { class: 'btn-ghost btn-danger', title: 'Delete', onclick: (e) => { e.stopPropagation(); onDelete(f); } }, 'Delete'),
    ])),
  ]);
  row.addEventListener('click', () => toggle(f, tbody, row));
  return row;
}

async function toggle(f, tbody, row) {
  if (expanded.has(f.id)) {
    expanded.delete(f.id);
    row.classList.remove('open');
    removeChildren(tbody, f.id);
  } else {
    expanded.add(f.id);
    row.classList.add('open');
    await appendChildren(tbody, f, row);
  }
}

async function appendChildren(tbody, f, afterRow = null) {
  let items = [];
  try { items = await api.listTranscriptions({ folder_id: f.id }); } catch {}
  const rows = [];
  if (!items.length) {
    rows.push(el('tr', { class: 'child-row', 'data-parent': f.id }, [
      el('td', { colspan: 3 }, el('div', { class: 'child-name', style: 'color:var(--text-muted);cursor:default' }, 'No transcriptions yet')),
    ]));
  } else {
    for (const t of items) {
      rows.push(el('tr', { class: 'child-row', 'data-parent': f.id }, [
        el('td', {}, el('div', { class: 'child-name', onclick: () => { location.hash = `#/t/${t.id}`; } }, [
          el('span', {}, '📄'),
          el('span', {}, t.name),
        ])),
        el('td', {}, fmtDate(t.created_at)),
        el('td', { class: 'right' }, fmtDur(t.duration_s)),
      ]));
    }
  }
  // Insert right after the folder row (or after its existing children).
  const anchor = afterRow || [...tbody.querySelectorAll('tr')].find(r => r.dataset.id == f.id);
  if (anchor) rows.reverse().forEach(r => anchor.after(r));
  else rows.forEach(r => tbody.appendChild(r));
}

function removeChildren(tbody, folderId) {
  tbody.querySelectorAll(`tr.child-row[data-parent="${folderId}"]`).forEach(r => r.remove());
}

async function onNewFolder() {
  const name = await promptModal({ title: 'New folder', label: 'Folder name', confirmText: 'Create' });
  if (!name) return;
  try {
    await api.createFolder(name);
    toast('Folder created');
    refreshSidebar();
    renderFolders(document.getElementById('detail'));
  } catch (e) { toast(e.message); }
}

async function onRename(f) {
  const name = await promptModal({ title: 'Rename folder', label: 'Folder name', value: f.name, confirmText: 'Rename' });
  if (!name || name === f.name) return;
  try {
    await api.updateFolder(f.id, { name });
    toast('Renamed');
    refreshSidebar();
    renderFolders(document.getElementById('detail'));
  } catch (e) { toast(e.message); }
}

async function onDelete(f) {
  const msg = f.count > 0
    ? `Delete "${f.name}" and its ${f.count} transcription${f.count === 1 ? '' : 's'}?`
    : `Delete "${f.name}"?`;
  if (!await confirmModal({ title: msg })) return;
  try {
    await api.deleteFolder(f.id);
    expanded.delete(f.id);
    toast('Folder deleted');
    refreshSidebar();
    renderFolders(document.getElementById('detail'));
  } catch (e) { toast(e.message); }
}
