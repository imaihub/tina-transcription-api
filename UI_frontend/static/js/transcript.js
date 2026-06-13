// Transcription detail view: Transcript + Content tabs, speaker blocks with
// per-segment playback, and an audio player. Editing (search/replace, split) is
// added in TODO item 4; copy/export in item 5.

import { api } from './api.js';
import { el, clear, langLabel } from './util.js';

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

  // Stable speaker → colour mapping.
  const speakers = [...new Set(segments.map(s => s.speaker))].sort();
  const colorOf = (spk) => SPEAKER_COLORS[speakers.indexOf(spk) % SPEAKER_COLORS.length];

  const audio = el('audio', { controls: '', src: api.audioUrl(t.id), style: 'width:100%' });

  // Group consecutive segments by speaker into turns.
  const turns = [];
  for (const s of segments) {
    const last = turns[turns.length - 1];
    if (last && last.speaker === s.speaker) last.segments.push(s);
    else turns.push({ speaker: s.speaker, segments: [s] });
  }

  const body = el('div', { class: 'transcript-body' });
  for (const turn of turns) {
    const c = colorOf(turn.speaker);
    const seg0 = turn.segments[0];
    const langs = [...new Set(turn.segments.map(s => s.lang).filter(Boolean))];

    const playBtn = el('button', { class: 'seg-play', title: 'Play', onclick: () => playRange(audio, playBtn, seg0.start, turn.segments[turn.segments.length - 1].end) }, '▶');

    const head = el('div', { class: 'turn-head' }, [
      el('span', { class: 'turn-speaker', style: `color:${c.fg}` }, turn.speaker),
      ...langs.map(l => el('span', { class: 'lang-badge', style: `background:${c.bg};color:${c.fg};border:1px solid ${c.border}` }, langLabel(l))),
      el('span', { class: 'turn-time' }, `${fmtClock(seg0.start)}`),
    ]);

    const textEl = el('div', { class: 'turn-text', style: `border-left:3px solid ${c.border}` });
    for (const s of turn.segments) {
      const inaudible = s.note === 'overlapping_speech';
      textEl.appendChild(el('span', {
        class: 'seg-text' + (inaudible ? ' inaudible' : ''),
        title: `${fmtClock(s.start)}–${fmtClock(s.end)}`,
      }, inaudible ? '[inaudible]' : (s.text || '')));
      textEl.appendChild(document.createTextNode(' '));
    }

    body.appendChild(el('div', { class: 'turn' }, [
      el('div', { class: 'turn-aside' }, playBtn),
      el('div', { class: 'turn-main' }, [head, textEl]),
    ]));
  }

  pane.appendChild(body);
  pane.appendChild(el('div', { class: 'player-bar' }, audio));
}

// ── Per-segment playback ───────────────────────────────────────────────────

let activeBtn = null;
let stopActive = null;

function playRange(audio, btn, start, end) {
  if (stopActive) stopActive();
  if (btn === activeBtn) return; // toggled off above

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
