// Transcription detail view — minimal for now; editing arrives in TODO items 4–5.

import { api } from './api.js';
import { el, clear, fmtDate } from './util.js';

export async function renderTranscript(root, id) {
  clear(root);
  let t;
  try {
    t = await api.getTranscription(id);
  } catch (e) {
    root.appendChild(el('div', { class: 'placeholder' }, `Could not load transcription: ${e.message}`));
    return;
  }

  root.appendChild(el('div', { class: 'breadcrumb' }, [
    el('a', { onclick: () => { location.hash = '#/folders'; } }, 'Folders'),
    document.createTextNode(` / ${t.folder_name} / ${t.name}`),
  ]));
  root.appendChild(el('div', { class: 'page-head' }, el('h2', {}, t.name)));
  root.appendChild(el('div', { class: 'placeholder' },
    'Transcript editing and tabs are coming in the next steps (TODO items 4–5).'));
}
