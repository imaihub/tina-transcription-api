// New Transcript flow: pick/drop an audio file, set name/folder/language, transcribe.
// Calls POST /api/transcriptions (the backend proxies to the transcription API and
// stores the result), then opens the new transcription.

import { api } from './api.js';
import { refreshSidebar } from './sidebar.js';
import { getActiveFolderId, setActiveFolderId, resolveActiveFolder } from './state.js';
import { el, clear, toast } from './util.js';

const ACCEPT = '.wav,.mp3,.flac,.ogg,.m4a,.aac';
const LANG_OPTIONS = [
  { value: 'nld+fry', label: 'Dutch + Frisian' },
  { value: 'nld', label: 'Dutch' },
  { value: 'fry', label: 'Frisian' },
];

export async function renderNewTranscript(root) {
  let folders = [];
  try { folders = await api.listFolders(); } catch {}
  const active = resolveActiveFolder(folders);
  if (active && getActiveFolderId() !== active.id) setActiveFolderId(active.id);

  const state = {
    folders,
    file: null,
    duration: null,
    name: '',
    folderId: active ? active.id : null,
    language: 'nld+fry',
    busy: false,
  };

  draw(root, state);
}

function draw(root, state) {
  clear(root);

  const folderName = state.folders.find(f => f.id === state.folderId)?.name || '—';
  root.appendChild(el('div', { class: 'breadcrumb' }, [
    el('a', { onclick: () => { location.hash = '#/folders'; } }, 'Folders'),
    document.createTextNode(` / ${folderName} / New Transcript`),
  ]));
  root.appendChild(el('div', { class: 'page-head' }, el('h2', {}, 'New Transcript')));

  if (state.busy) { root.appendChild(progressCard(state)); return; }

  root.appendChild(state.file ? selectedFileCard(root, state) : dropZone(root, state));
  root.appendChild(settingsPanel(state));

  const transcribeBtn = el('button', {
    class: 'btn', disabled: state.file ? null : 'disabled',
    onclick: () => transcribe(root, state),
  }, 'Transcribe Now');
  root.appendChild(el('div', { class: 'action-bar' }, transcribeBtn));
}

// ── File selection ───────────────────────────────────────────────────────────

function dropZone(root, state) {
  const input = el('input', {
    type: 'file', accept: ACCEPT, style: 'display:none',
    onchange: (e) => { if (e.target.files[0]) selectFile(root, state, e.target.files[0]); },
  });
  const zone = el('div', { class: 'dropzone' }, [
    el('div', { class: 'dz-icon' }, '⬆'),
    el('button', { class: 'btn', onclick: () => input.click() }, 'Select a file'),
    el('div', { class: 'dz-hint' }, 'or drag & drop a file here'),
    el('div', { class: 'dz-formats' }, `Supported: ${ACCEPT.replaceAll('.', '').replaceAll(',', ', ')}`),
    input,
  ]);
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault(); zone.classList.remove('drag');
    if (e.dataTransfer.files[0]) selectFile(root, state, e.dataTransfer.files[0]);
  });
  return zone;
}

function selectFile(root, state, file) {
  state.file = file;
  if (!state.name) state.name = file.name.replace(/\.[^.]+$/, '');
  state.duration = null;
  draw(root, state);
  // Read duration asynchronously and patch the label in place.
  readDuration(file).then((d) => {
    state.duration = d;
    const span = document.querySelector('.selected-dur');
    if (span && d != null) span.textContent = fmtClock(d);
  });
}

function selectedFileCard(root, state) {
  return el('div', { class: 'selected-file' }, [
    el('div', {}, [
      el('span', { class: 'selected-dur' }, state.duration != null ? fmtClock(state.duration) : '··:··'),
      el('span', { class: 'selected-name' }, state.file.name),
    ]),
    el('button', { class: 'btn-ghost btn-danger', title: 'Remove', onclick: () => { state.file = null; state.duration = null; draw(root, state); } }, '🗑'),
  ]);
}

// ── Settings ───────────────────────────────────────────────────────────────

function settingsPanel(state) {
  const nameInput = el('input', {
    type: 'text', value: state.name, placeholder: 'My transcription',
    oninput: (e) => { state.name = e.target.value; },
  });

  const folderSelect = el('select', {
    class: 'filter-select',
    onchange: (e) => { state.folderId = Number(e.target.value); setActiveFolderId(state.folderId); },
  }, state.folders.map(f => el('option', { value: String(f.id) }, f.name)));
  if (state.folderId) folderSelect.value = String(state.folderId);

  const langSelect = el('select', {
    class: 'filter-select',
    onchange: (e) => { state.language = e.target.value; },
  }, LANG_OPTIONS.map(o => el('option', { value: o.value }, o.label)));
  langSelect.value = state.language;

  return el('div', { class: 'settings-card' }, [
    el('h3', { class: 'settings-title' }, 'Settings'),
    field('Transcription name', nameInput),
    field('Save to folder', folderSelect),
    field('Language', langSelect),
    el('p', { class: 'settings-note' },
      'Speaker diarization runs automatically. Choosing an exact number of speakers and custom spelling will be available once the transcription API supports them.'),
  ]);
}

function field(label, control) {
  return el('div', { class: 'field' }, [el('label', {}, label), control]);
}

// ── Transcribe ───────────────────────────────────────────────────────────────

async function transcribe(root, state) {
  if (!state.file || !state.folderId) return;
  state.busy = true;
  draw(root, state);
  try {
    const form = new FormData();
    form.append('file', state.file, state.file.name);
    form.append('folder_id', String(state.folderId));
    form.append('name', state.name.trim());
    form.append('language', state.language);
    const t = await api.createTranscription(form);
    setActiveFolderId(state.folderId);
    refreshSidebar();
    toast('Transcription complete');
    location.hash = `#/t/${t.id}`;
  } catch (e) {
    state.busy = false;
    draw(root, state);
    toast(`Transcription failed: ${e.message}`);
  }
}

function progressCard(state) {
  return el('div', { class: 'progress-card' }, [
    el('div', { class: 'spinner-lg' }),
    el('div', { class: 'progress-title' }, `Transcribing ${state.name || state.file?.name || ''}…`),
    el('div', { class: 'progress-hint' }, 'This can take a while for long recordings. Please keep this tab open.'),
  ]);
}

// ── Utilities ──────────────────────────────────────────────────────────────

function readDuration(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    audio.preload = 'metadata';
    audio.onloadedmetadata = () => { URL.revokeObjectURL(url); resolve(isFinite(audio.duration) ? audio.duration : null); };
    audio.onerror = () => { URL.revokeObjectURL(url); resolve(null); };
    audio.src = url;
  });
}

function fmtClock(s) {
  const m = Math.floor(s / 60), sec = Math.round(s % 60);
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}
