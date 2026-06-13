// Transcription detail view: Transcript + Content tabs, speaker blocks with
// per-segment playback, and an audio player. Editing (search/replace, split) is
// added in TODO item 4; copy/export in item 5.

import { api } from './api.js';
import { el, clear, langLabel, toast } from './util.js';

const SPEAKER_COLORS = [
  { fg: '#2563eb', bg: '#eff6ff', border: '#bfdbfe' },
  { fg: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0' },
  { fg: '#d97706', bg: '#fffbeb', border: '#fde68a' },
  { fg: '#9333ea', bg: '#faf5ff', border: '#e9d5ff' },
  { fg: '#0891b2', bg: '#ecfeff', border: '#a5f3fc' },
  { fg: '#e11d48', bg: '#fff1f2', border: '#fecdd3' },
];

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

  // Tabs
  const transcriptPane = el('div', { class: 'tab-pane' });
  const contentPane = el('div', { class: 'tab-pane', style: 'display:none' },
    el('div', { class: 'placeholder' }, 'Content Hub — coming soon (TODO item 6).'));

  const tabTranscript = el('button', { class: 'tab active', onclick: () => switchTab(0) }, 'Transcript');
  const tabContent = el('button', { class: 'tab', onclick: () => switchTab(1) }, 'Content');

  function switchTab(i) {
    tabTranscript.classList.toggle('active', i === 0);
    tabContent.classList.toggle('active', i === 1);
    transcriptPane.style.display = i === 0 ? '' : 'none';
    contentPane.style.display = i === 1 ? '' : 'none';
  }

  root.appendChild(el('div', { class: 'tabs' }, [tabTranscript, tabContent]));
  root.appendChild(transcriptPane);
  root.appendChild(contentPane);

  renderTranscriptPane(transcriptPane, t);
}

function renderTranscriptPane(pane, t) {
  clear(pane);

  const segments = t.segments || [];
  if (!segments.length) {
    pane.appendChild(el('div', { class: 'placeholder' }, 'No speech segments were detected in this audio.'));
    return;
  }

  // Speaker → colour by first-appearance order, so colours stay stable across renames.
  const order = [];
  for (const s of segments) if (!order.includes(s.speaker)) order.push(s.speaker);
  const colorOf = (spk) => SPEAKER_COLORS[Math.max(0, order.indexOf(spk)) % SPEAKER_COLORS.length];

  // Click a speaker label to rename it; Enter saves and renames every segment with
  // that speaker, Escape cancels.
  function speakerLabel(name, color) {
    const span = el('span', { class: 'turn-speaker editable', style: `color:${color}`, title: 'Click to rename', contenteditable: 'false' }, name);
    span.addEventListener('click', () => {
      if (span.getAttribute('contenteditable') === 'true') return;
      span.setAttribute('contenteditable', 'true');
      span.focus();
      getSelection().selectAllChildren(span);
    });
    span.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); span.blur(); }
      else if (e.key === 'Escape') { e.preventDefault(); span.textContent = name; span.blur(); }
    });
    span.addEventListener('blur', () => {
      span.setAttribute('contenteditable', 'false');
      const newName = span.textContent.trim();
      if (!newName || newName === name) { span.textContent = name; return; }
      renameSpeaker(name, newName);
    });
    return span;
  }

  async function renameSpeaker(oldName, newName) {
    for (const s of t.segments) if (s.speaker === oldName) s.speaker = newName;
    renderTranscriptPane(pane, t);   // optimistic: update all turns immediately
    try {
      await api.updateTranscription(t.id, { segments: t.segments });
      toast('Speaker renamed');
    } catch (e) {
      toast(`Save failed: ${e.message}`);
    }
  }

  const audio = el('audio', { controls: '', src: api.audioUrl(t.id), style: 'width:100%' });

  // Re-transcribe a single segment in a forced language (no re-diarization).
  async function retranscribe(seg, language, ddEl) {
    ddEl.replaceChildren(el('span', { class: 'seg-spinner' }));
    try {
      const updated = await api.retranscribeSegment(t.id, seg.id, language);
      const target = t.segments.find(s => String(s.id) === String(seg.id));
      target.text = updated.text;
      target.lang = updated.lang;
      target.note = 'ok';
      toast(`Re-transcribed as ${langLabel(language)}`);
    } catch (e) {
      toast(`Re-transcribe failed: ${e.message}`);
    }
    renderTranscriptPane(pane, t);
  }

  // Language badge with a "Re-transcribe as" dropdown.
  function langDropdown(seg, c) {
    const badge = el('button', {
      class: 'lang-badge-btn', title: 'Change language',
      style: `background:${c.bg};color:${c.fg};border:1px solid ${c.border}`,
    }, [el('span', {}, langLabel(seg.lang) || '—'), el('span', { class: 'caret' }, '▾')]);

    const menu = el('div', { class: 'lang-menu', style: 'display:none' }, [
      el('div', { class: 'lang-menu-label' }, 'Re-transcribe as'),
      ...[['nld', 'Dutch'], ['fry', 'Frisian']].map(([code, label]) =>
        el('div', {
          class: 'lang-menu-item' + (seg.lang === code ? ' current' : ''),
          onclick: (e) => { e.stopPropagation(); closeMenus(); retranscribe(seg, code, dd); },
        }, label)),
    ]);

    badge.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = menu.style.display !== 'none';
      closeMenus();
      menu.style.display = isOpen ? 'none' : 'block';
    });

    const dd = el('div', { class: 'lang-dd' }, [badge, menu]);
    return dd;
  }

  // Group consecutive segments by speaker into turns (one speaker header per turn).
  const turns = [];
  for (const s of segments) {
    const last = turns[turns.length - 1];
    if (last && last.speaker === s.speaker) last.segments.push(s);
    else turns.push({ speaker: s.speaker, segments: [s] });
  }

  const body = el('div', { class: 'transcript-body' });
  for (const turn of turns) {
    const c = colorOf(turn.speaker);
    const turnEl = el('div', { class: 'turn', style: `border-left:3px solid ${c.border}` });
    turnEl.appendChild(el('div', { class: 'turn-head' }, speakerLabel(turn.speaker, c.fg)));

    for (const seg of turn.segments) {
      const inaudible = seg.note === 'overlapping_speech';
      const play = el('button', { class: 'seg-play', title: 'Play', onclick: () => playRange(audio, play, seg.start, seg.end) }, '▶');
      const text = el('div', { class: 'seg-text-cell' + (inaudible ? ' inaudible' : ''), title: `${fmtClock(seg.start)}–${fmtClock(seg.end)}` },
        inaudible ? '[inaudible]' : (seg.text || ''));
      const meta = el('div', { class: 'seg-meta' }, inaudible ? [] : langDropdown(seg, c));

      turnEl.appendChild(el('div', { class: 'seg-row' }, [
        el('div', { class: 'seg-aside' }, play),
        text,
        meta,
      ]));
    }
    body.appendChild(turnEl);
  }

  pane.appendChild(body);
  pane.appendChild(el('div', { class: 'player-bar' }, audio));
}

// Close any open language dropdown when clicking elsewhere.
function closeMenus() {
  document.querySelectorAll('.lang-menu').forEach(m => { m.style.display = 'none'; });
}
document.addEventListener('click', closeMenus);

// ── Per-segment playback ───────────────────────────────────────────────────

let activeBtn = null;
let stopActive = null;

function playRange(audio, btn, start, end) {
  const wasActive = btn === activeBtn;
  if (stopActive) stopActive();
  if (wasActive) return; // re-click on the playing segment → stop (toggle off)

  const onTime = () => { if (audio.currentTime >= end) stop(); };
  function stop() {
    audio.removeEventListener('timeupdate', onTime);
    audio.pause();
    btn.textContent = '▶';
    activeBtn = null; stopActive = null;
  }

  activeBtn = btn; stopActive = stop;
  btn.textContent = '⏸';
  audio.currentTime = start;
  audio.play();
  audio.addEventListener('timeupdate', onTime);
}

function fmtClock(s) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}
