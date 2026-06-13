// Transcription detail view.
//
// Two view modes over the same segment list (segments are the source of truth):
//   • Detail  — per-segment rows: play, language badge, "Re-transcribe as" dropdown.
//   • Reading — consecutive same-speaker segments merged into one flowing, editable
//               paragraph per turn. Each segment stays a distinct editable run, so
//               edits preserve per-segment language/timestamps.
// Split-on-Enter (4b) and find & replace (4c) build on the reading view.

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

// Language badge colours — consistent regardless of speaker.
const LANG_COLORS = {
  nld: { fg: '#1e40af', bg: '#eff6ff', border: '#bfdbfe' },  // Dutch — blue
  fry: { fg: '#065f46', bg: '#ecfdf5', border: '#a7f3d0' },  // Frisian — green
};
const DEFAULT_LANG_COLOR = { fg: '#6b7280', bg: '#f3f4f6', border: '#e5e7eb' };
const langColor = (l) => LANG_COLORS[l] || DEFAULT_LANG_COLOR;

const VIEW_MODE_KEY = 'tina.viewMode';

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

  // ── Tabs ───────────────────────────────────────────────────────────────────
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

  if (!(t.segments || []).length) {
    transcriptPane.appendChild(el('div', { class: 'placeholder' }, 'No speech segments were detected in this audio.'));
    return;
  }

  // ── Shared state & helpers ───────────────────────────────────────────────────
  const audio = el('audio', { controls: '', src: api.audioUrl(t.id), style: 'width:100%' });
  let mode = localStorage.getItem(VIEW_MODE_KEY) || 'detail';

  // Speaker → colour by first-appearance order, so colours stay stable across renames.
  function colorOf(spk) {
    const order = [];
    for (const s of t.segments) if (!order.includes(s.speaker)) order.push(s.speaker);
    return SPEAKER_COLORS[Math.max(0, order.indexOf(spk)) % SPEAKER_COLORS.length];
  }

  async function saveSegments(successMsg) {
    try {
      await api.updateTranscription(t.id, { segments: t.segments });
      if (successMsg) toast(successMsg);
    } catch (e) {
      toast(`Save failed: ${e.message}`);
    }
  }

  // Group consecutive segments into turns, honouring explicit break_before markers.
  function turnsOf() {
    const turns = [];
    for (const s of t.segments) {
      const last = turns[turns.length - 1];
      if (last && last.speaker === s.speaker && !s.break_before) last.segments.push(s);
      else turns.push({ speaker: s.speaker, segments: [s] });
    }
    return turns;
  }

  // Click a speaker label to rename it; Enter saves and renames every segment with
  // that speaker, Escape cancels.
  function speakerLabel(name) {
    const span = el('span', { class: 'turn-speaker editable', style: `color:${colorOf(name).fg}`, title: 'Click to rename', contenteditable: 'false' }, name);
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
    span.addEventListener('blur', async () => {
      span.setAttribute('contenteditable', 'false');
      const newName = span.textContent.trim();
      if (!newName || newName === name) { span.textContent = name; return; }
      for (const s of t.segments) if (s.speaker === name) s.speaker = newName;
      renderBody();
      await saveSegments('Speaker renamed');
    });
    return span;
  }

  // ── View-mode toggle + body ──────────────────────────────────────────────────
  const toolbar = el('div', { class: 'tx-toolbar' }, viewToggle());
  const bodyWrap = el('div', { class: 'tx-body' });
  transcriptPane.append(toolbar, bodyWrap);

  function viewToggle() {
    const make = (m, label) => el('button', {
      class: 'view-btn' + (mode === m ? ' active' : ''),
      onclick: () => {
        if (mode === m) return;
        mode = m;
        localStorage.setItem(VIEW_MODE_KEY, m);
        toggle.querySelectorAll('.view-btn').forEach(b => b.classList.toggle('active', b === (m === 'detail' ? detailBtn : readingBtn)));
        renderBody();
      },
    }, label);
    const detailBtn = make('detail', 'Detail');
    const readingBtn = make('reading', 'Reading');
    const toggle = el('div', { class: 'view-toggle' }, [detailBtn, readingBtn]);
    return toggle;
  }

  function renderBody() {
    clear(bodyWrap);
    closeMenus();
    if (mode === 'reading') renderReading(bodyWrap);
    else renderDetail(bodyWrap);
  }

  // ── Detail view ──────────────────────────────────────────────────────────────
  function renderDetail(container) {
    async function retranscribe(seg, language, ddEl) {
      ddEl.replaceChildren(el('span', { class: 'seg-spinner' }));
      try {
        const updated = await api.retranscribeSegment(t.id, seg.id, language);
        const target = t.segments.find(s => String(s.id) === String(seg.id));
        target.text = updated.text; target.lang = updated.lang; target.note = 'ok';
        toast(`Re-transcribed as ${langLabel(language)}`);
      } catch (e) {
        toast(`Re-transcribe failed: ${e.message}`);
      }
      renderBody();
    }

    function langDropdown(seg) {
      const lc = langColor(seg.lang);
      const badge = el('button', {
        class: 'lang-badge-btn', title: 'Change language',
        style: `background:${lc.bg};color:${lc.fg};border:1px solid ${lc.border}`,
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

    const body = el('div', { class: 'transcript-body' });
    for (const turn of turnsOf()) {
      const c = colorOf(turn.speaker);
      const turnEl = el('div', { class: 'turn', style: `border-left:3px solid ${c.border}` });
      turnEl.appendChild(el('div', { class: 'turn-head' }, speakerLabel(turn.speaker)));
      for (const seg of turn.segments) {
        const inaudible = seg.note === 'overlapping_speech';
        const play = el('button', { class: 'seg-play', title: 'Play', onclick: () => playRange(audio, play, seg.start, seg.end) }, '▶');
        const text = el('div', { class: 'seg-text-cell' + (inaudible ? ' inaudible' : ''), title: `${fmtClock(seg.start)}–${fmtClock(seg.end)}` },
          inaudible ? '[inaudible]' : (seg.text || ''));
        const meta = el('div', { class: 'seg-meta' }, inaudible ? [] : langDropdown(seg));
        turnEl.appendChild(el('div', { class: 'seg-row' }, [el('div', { class: 'seg-aside' }, play), text, meta]));
      }
      body.appendChild(turnEl);
    }
    container.appendChild(body);
    container.appendChild(el('div', { class: 'player-bar' }, audio));
  }

  // ── Reading view ─────────────────────────────────────────────────────────────
  function renderReading(container) {
    // Set true while a split re-renders, so the removed span's blur handler does
    // not clobber the just-applied split with its stale text.
    let splitting = false;

    function newSegId() {
      const ids = new Set(t.segments.map(s => String(s.id)));
      let n = 0; while (ids.has(String(n))) n++;
      return String(n);
    }

    function focusSegStart(id) {
      const sp = bodyWrap.querySelector(`.seg-edit[data-seg-id="${CSS.escape(String(id))}"]`);
      if (!sp) return;
      sp.focus();
      const r = document.createRange();
      r.setStart(sp.firstChild || sp, 0); r.collapse(true);
      const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
    }

    // Split the turn at the caret. Snaps to a real segment boundary when the caret
    // is at a segment edge; interpolates by character offset only inside a segment.
    function splitAt(seg, span) {
      const sel = getSelection();
      const offset = (sel && sel.rangeCount && span.contains(sel.anchorNode)) ? sel.anchorOffset : 0;
      const full = span.textContent;
      const before = full.slice(0, offset).trim();
      const after = full.slice(offset).trim();

      const idx = t.segments.findIndex(s => String(s.id) === String(seg.id));
      const target = t.segments[idx];
      target.text = full.trim();   // capture any uncommitted inline edit
      let focusId = null;

      if (!after) {
        // Caret at the segment end → snap to its end boundary; next segment in the
        // turn (if any) begins the new block.
        const next = t.segments[idx + 1];
        if (next && next.speaker === target.speaker && !next.break_before) {
          next.break_before = true; focusId = next.id;
        } else { return; }
      } else if (!before) {
        // Caret at the segment start → snap to its start boundary; this segment
        // begins the new block (unless it already starts the turn).
        const prev = t.segments[idx - 1];
        const startsTurn = !(prev && prev.speaker === target.speaker && !target.break_before);
        if (startsTurn) return;
        target.break_before = true; focusId = target.id;
      } else {
        // Caret inside the segment → interpolate the boundary time by char offset.
        const totalChars = full.trim().length || 1;
        const frac = before.length / totalChars;
        let mid = target.start + (target.end - target.start) * frac;
        mid = Math.min(target.end, Math.max(target.start, Math.round(mid * 1000) / 1000));
        const newSeg = {
          id: newSegId(), speaker: target.speaker,
          start: mid, end: target.end, text: after,
          lang: target.lang, note: target.note || 'ok', break_before: true,
        };
        target.end = mid; target.text = before;
        t.segments.splice(idx + 1, 0, newSeg);
        focusId = newSeg.id;
      }

      splitting = true;
      renderBody();
      if (focusId != null) focusSegStart(focusId);
      saveSegments();
    }

    const body = el('div', { class: 'transcript-body' });
    for (const turn of turnsOf()) {
      const c = colorOf(turn.speaker);
      const last = turn.segments[turn.segments.length - 1];
      const play = el('button', { class: 'seg-play', title: 'Play turn', onclick: () => playRange(audio, play, turn.segments[0].start, last.end) }, '▶');

      const head = el('div', { class: 'turn-head reading-head' }, [
        play,
        speakerLabel(turn.speaker),
        el('span', { class: 'turn-time' }, `${fmtClock(turn.segments[0].start)}–${fmtClock(last.end)}`),
      ]);

      // Flowing paragraph: each segment is its own editable run, so edits map back
      // to exactly one segment (preserving its language/timestamps).
      const para = el('p', { class: 'reading-text' });
      for (const seg of turn.segments) {
        const inaudible = seg.note === 'overlapping_speech';
        const span = el('span', {
          class: 'seg-edit' + (inaudible ? ' inaudible' : ''),
          'data-seg-id': seg.id,
          contenteditable: inaudible ? 'false' : 'true',
          spellcheck: 'false',
          title: `${langLabel(seg.lang) || '—'} · ${fmtClock(seg.start)}–${fmtClock(seg.end)}`,
        }, inaudible ? '[inaudible]' : (seg.text || ''));
        if (!inaudible) {
          span.addEventListener('blur', () => {
            if (splitting) return;
            const newText = span.textContent.trim();
            const target = t.segments.find(s => String(s.id) === String(seg.id));
            if (target && newText !== (target.text || '')) {
              target.text = newText;
              saveSegments();
            }
          });
          span.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); splitAt(seg, span); }
          });
        }
        para.appendChild(span);
        para.appendChild(document.createTextNode(' '));
      }

      body.appendChild(el('div', { class: 'turn reading-turn', style: `border-left:3px solid ${c.border}` }, [head, para]));
    }
    container.appendChild(body);
    container.appendChild(el('div', { class: 'player-bar' }, audio));
  }

  renderBody();
}

// ── Per-segment / per-turn playback ─────────────────────────────────────────

let activeBtn = null;
let stopActive = null;

function playRange(audio, btn, start, end) {
  const wasActive = btn === activeBtn;
  if (stopActive) stopActive();
  if (wasActive) return; // re-click on the playing item → stop (toggle off)

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

// Close any open language dropdown when clicking elsewhere.
function closeMenus() {
  document.querySelectorAll('.lang-menu').forEach(m => { m.style.display = 'none'; });
}
document.addEventListener('click', closeMenus);

function fmtClock(s) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}
