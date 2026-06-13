// Transcription detail view — a single "reading" view: consecutive same-speaker
// segments merged into one flowing, editable paragraph per turn.
//
//   • Edit text inline; each segment is its own editable run, so edits preserve
//     per-segment language/timestamps.
//   • Enter splits the turn at the caret (snap to a real boundary, else interpolate).
//   • Per-segment actions (play, re-transcribe as Dutch/Frisian) live in a context
//     menu, opened by right-click or the language chip shown on hover/active.
//   • A "Show language" toggle adds an always-on subtle per-language tint.

import { api } from './api.js';
import { refreshSidebar } from './sidebar.js';
import { el, clear, langLabel, toast, promptModal, confirmModal } from './util.js';

const SPEAKER_COLORS = [
  { fg: '#2563eb', bg: '#eff6ff', border: '#bfdbfe' },
  { fg: '#16a34a', bg: '#f0fdf4', border: '#bbf7d0' },
  { fg: '#d97706', bg: '#fffbeb', border: '#fde68a' },
  { fg: '#9333ea', bg: '#faf5ff', border: '#e9d5ff' },
  { fg: '#0891b2', bg: '#ecfeff', border: '#a5f3fc' },
  { fg: '#e11d48', bg: '#fff1f2', border: '#fecdd3' },
];

const LANG_COLORS = {
  nld: { fg: '#1e40af', bg: '#eff6ff', border: '#bfdbfe', short: 'NL' },  // Dutch — blue
  fry: { fg: '#065f46', bg: '#ecfdf5', border: '#a7f3d0', short: 'FY' },  // Frisian — green
};
const DEFAULT_LANG_COLOR = { fg: '#6b7280', bg: '#f3f4f6', border: '#e5e7eb', short: '?' };
const langColor = (l) => LANG_COLORS[l] || DEFAULT_LANG_COLOR;

const SHOW_LANG_KEY = 'tina.showLang';

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
  const titleMenuBtn = el('button', { class: 'toolbar-btn caret-btn', title: 'Transcription options', onclick: (e) => { e.stopPropagation(); openTitleMenu(titleMenuBtn); } }, '⋮');
  root.appendChild(el('div', { class: 'page-head' }, el('div', { class: 'title-row' }, [el('h2', {}, t.name), titleMenuBtn])));

  // ── Transcription management (rename / move / delete) ────────────────────────
  async function renameTranscription() {
    const name = await promptModal({ title: 'Rename transcription', label: 'Name', value: t.name, confirmText: 'Rename' });
    if (!name || name === t.name) return;
    try { await api.updateTranscription(t.id, { name }); refreshSidebar(); renderTranscript(root, t.id); }
    catch (e) { toast(e.message); }
  }
  async function moveTranscription(folderId) {
    if (folderId === t.folder_id) return;
    try { await api.updateTranscription(t.id, { folder_id: folderId }); refreshSidebar(); renderTranscript(root, t.id); }
    catch (e) { toast(e.message); }
  }
  async function deleteTranscription() {
    if (!await confirmModal({ title: `Delete "${t.name}"? This cannot be undone.` })) return;
    try { await api.deleteTranscription(t.id); toast('Transcription deleted'); refreshSidebar(); location.hash = '#/folders'; }
    catch (e) { toast(e.message); }
  }
  async function openTitleMenu(anchor) {
    closeToolbarMenus();
    let folders = [];
    try { folders = await api.listFolders(); } catch {}
    const item = (label, fn, opts = {}) =>
      el('div', { class: 'tb-menu-item' + (opts.current ? ' current' : '') + (opts.danger ? ' danger' : ''), onclick: (e) => { e.stopPropagation(); closeToolbarMenus(); fn(); } }, label);
    const items = [item('Rename…', renameTranscription)];
    if (folders.length > 1) {
      items.push(el('div', { class: 'tb-menu-label' }, 'Move to folder'));
      for (const f of folders) items.push(item(f.name, () => moveTranscription(f.id), { current: f.id === t.folder_id }));
    }
    items.push(el('div', { class: 'tb-menu-sep' }));
    items.push(item('Delete transcription', deleteTranscription, { danger: true }));
    positionMenu(el('div', { class: 'tb-menu' }, items), anchor);
  }

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
  let showLang = localStorage.getItem(SHOW_LANG_KEY) === '1';

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

  // Undo/redo over segment-state snapshots. pushUndo() is called just before each
  // mutating action; undo/redo swap whole-segment snapshots and persist.
  const undoStack = [], redoStack = [];
  const snapshot = () => structuredClone(t.segments);
  function pushUndo() {
    undoStack.push(snapshot());
    if (undoStack.length > 60) undoStack.shift();
    redoStack.length = 0;
  }
  async function undo() {
    document.activeElement?.blur?.();   // commit any in-progress edit (its blur records an undo step)
    if (!undoStack.length) { toast('Nothing to undo'); return; }
    redoStack.push(snapshot());
    t.segments = undoStack.pop();
    renderBody();
    await saveSegments();
  }
  async function redo() {
    document.activeElement?.blur?.();
    if (!redoStack.length) { toast('Nothing to redo'); return; }
    undoStack.push(snapshot());
    t.segments = redoStack.pop();
    renderBody();
    await saveSegments();
  }

  // A turn starts at the first segment or wherever an explicit break_before marker is
  // set. Boundaries are baked in at load (ensureTurnBoundaries) and only ever added (on
  // split) — never inferred from the speaker name. So renaming or reassigning a turn to
  // a name matching its neighbour never auto-merges them.
  function turnsOf() {
    const turns = [];
    for (const s of t.segments) {
      if (!turns.length || s.break_before) turns.push({ speaker: s.speaker, segments: [s] });
      else turns[turns.length - 1].segments.push(s);
    }
    return turns;
  }

  // Make the diarizer's initial turn boundaries explicit, so grouping no longer depends
  // on the (mutable) speaker name. Only ever adds markers; never removes them.
  function ensureTurnBoundaries() {
    for (let i = 1; i < t.segments.length; i++) {
      const s = t.segments[i];
      if (!s.break_before && s.speaker !== t.segments[i - 1].speaker) s.break_before = true;
    }
  }

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
      pushUndo();
      for (const s of t.segments) if (s.speaker === name) s.speaker = newName;
      renderBody();
      await saveSegments('Speaker renamed');
    });
    return span;
  }

  // Speaker control: an editable name (click to rename the speaker everywhere) plus a
  // caret that opens a menu to assign THIS turn to a different / new speaker.
  function speakerControl(turn) {
    const caret = el('button', {
      class: 'speaker-caret', title: 'Assign this turn to a speaker',
      onclick: (e) => { e.stopPropagation(); openSpeakerMenu(turn, caret); },
    }, '▾');
    return el('span', { class: 'speaker-ctl' }, [speakerLabel(turn.speaker), caret]);
  }

  function distinctSpeakers() {
    const out = [];
    for (const s of t.segments) if (!out.includes(s.speaker)) out.push(s.speaker);
    return out;
  }

  function openSpeakerMenu(turn, anchor) {
    closeToolbarMenus(); closeSegMenu();
    const item = (label, onClick, current = false) =>
      el('div', { class: 'tb-menu-item' + (current ? ' current' : ''), onclick: (e) => { e.stopPropagation(); closeToolbarMenus(); onClick(); } }, label);

    const items = [el('div', { class: 'tb-menu-label' }, 'Assign turn to')];
    for (const s of distinctSpeakers()) items.push(item(s, () => reassignTurn(turn, s), s === turn.speaker));
    items.push(el('div', { class: 'tb-menu-sep' }));
    items.push(item('New speaker…', async () => {
      const name = await promptModal({ title: 'New speaker', label: 'Speaker name', confirmText: 'Assign' });
      if (name) reassignTurn(turn, name);
    }));

    // Offer to merge with the following turn only when it has the same speaker.
    const next = nextTurnOf(turn);
    if (next && next.speaker === turn.speaker) {
      items.push(el('div', { class: 'tb-menu-sep' }));
      items.push(item('Merge with next turn', () => mergeTurn(turn)));
    }
    positionMenu(el('div', { class: 'tb-menu' }, items), anchor);
  }

  async function reassignTurn(turn, newSpeaker) {
    newSpeaker = (newSpeaker || '').trim();
    if (!newSpeaker || newSpeaker === turn.speaker) return;
    pushUndo();
    for (const s of turn.segments) s.speaker = newSpeaker;   // only this turn's segments
    renderBody();
    await saveSegments('Turn reassigned');
  }

  function nextTurnOf(turn) {
    const turns = turnsOf();
    const i = turns.findIndex(tn => String(tn.segments[0].id) === String(turn.segments[0].id));
    return (i >= 0 && i + 1 < turns.length) ? turns[i + 1] : null;
  }

  // Merge a turn with the one after it by dropping the boundary marker between them.
  async function mergeTurn(turn) {
    const next = nextTurnOf(turn);
    if (!next || next.speaker !== turn.speaker) return;
    pushUndo();
    next.segments[0].break_before = false;   // ensureTurnBoundaries won't re-add it (same speaker)
    renderBody();
    await saveSegments('Turns merged');
  }

  async function retranscribe(seg, language) {
    const span = bodyWrap.querySelector(`.seg-edit[data-seg-id="${CSS.escape(String(seg.id))}"]`);
    if (span) span.classList.add('seg-loading');
    try {
      const updated = await api.retranscribeSegment(t.id, seg.id, language);
      const target = t.segments.find(s => String(s.id) === String(seg.id));
      pushUndo();
      target.text = updated.text; target.lang = updated.lang; target.note = 'ok';
      toast(`Re-transcribed as ${langLabel(language)}`);
    } catch (e) {
      toast(`Re-transcribe failed: ${e.message}`);
    }
    renderBody();
  }

  // Play a segment — optionally through to the end of its turn — driving that turn's
  // play button so it shows ⏸ and can be paused no matter how playback was started.
  function playTurnRange(seg, toEndOfTurn) {
    const turn = turnsOf().find(tn => tn.segments.some(s => String(s.id) === String(seg.id)));
    if (!turn) return;
    const end = toEndOfTurn ? turn.segments[turn.segments.length - 1].end : seg.end;
    const btn = bodyWrap.querySelector(`.seg-play[data-turn-id="${CSS.escape(String(turn.segments[0].id))}"]`);
    const segSpans = turn.segments
      .map(s => ({ seg: s, span: bodyWrap.querySelector(`.seg-edit[data-seg-id="${CSS.escape(String(s.id))}"]`) }))
      .filter(x => x.span);
    playRange(audio, btn, seg.start, end, {
      onTick: (ct) => highlightPlaying(segSpans, ct),
      onStop: () => highlightPlaying(segSpans, -1),
    });
  }

  // Per-segment context menu (right-click or chip).
  function openSegMenu(seg, x, y) {
    closeSegMenu();
    const item = (label, onClick, current = false) =>
      el('div', { class: 'seg-menu-item' + (current ? ' current' : ''), onclick: (e) => { e.stopPropagation(); closeSegMenu(); onClick(); } }, label);

    const menu = el('div', { class: 'seg-menu' }, [
      el('div', { class: 'seg-menu-head' }, `${langLabel(seg.lang) || 'Unknown'} · ${fmtClock(seg.start)}–${fmtClock(seg.end)}`),
      item('▶  Play segment', () => playTurnRange(seg, false)),
      item('▶  Play from here', () => playTurnRange(seg, true)),
      el('div', { class: 'seg-menu-label' }, 'Re-transcribe as'),
      item('Dutch', () => retranscribe(seg, 'nld'), seg.lang === 'nld'),
      item('Frisian', () => retranscribe(seg, 'fry'), seg.lang === 'fry'),
    ]);
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    document.body.appendChild(menu);
    // Clamp to the viewport.
    const r = menu.getBoundingClientRect();
    if (r.right > innerWidth) menu.style.left = `${Math.max(8, innerWidth - r.width - 8)}px`;
    if (r.bottom > innerHeight) menu.style.top = `${Math.max(8, y - r.height)}px`;
  }

  // ── Toolbar: find/replace + language toggle ──────────────────────────────────
  const bodyWrap = el('div', { class: 'tx-body' + (showLang ? ' show-lang' : '') });

  const langToggle = el('button', {
    class: 'toolbar-btn' + (showLang ? ' active' : ''), title: "Highlight each segment's transcribed language",
    onclick: () => {
      showLang = !showLang;
      localStorage.setItem(SHOW_LANG_KEY, showLang ? '1' : '0');
      langToggle.classList.toggle('active', showLang);
      bodyWrap.classList.toggle('show-lang', showLang);
    },
  }, [el('span', { class: 'lang-swatch' }), 'Show language']);

  // Find & replace. Matches are computed over segment text; highlighting uses the CSS
  // Custom Highlight API so it doesn't mutate the contenteditable DOM.
  const findInput = el('input', { class: 'find-input', type: 'text', placeholder: 'Find' });
  const replaceInput = el('input', { class: 'replace-input', type: 'text', placeholder: 'Replace with' });
  const countEl = el('span', { class: 'find-count' }, '');
  const prevBtn = el('button', { class: 'find-nav', title: 'Previous (Shift+Enter)' }, '‹');
  const nextBtn = el('button', { class: 'find-nav', title: 'Next (Enter)' }, '›');
  const replaceBtn = el('button', { class: 'toolbar-btn', title: 'Replace current match' }, 'Replace');
  const replaceAllBtn = el('button', { class: 'toolbar-btn', title: 'Replace all matches' }, 'All');
  const findBar = el('div', { class: 'find-bar' }, [
    el('span', { class: 'find-icon' }, '🔍'), findInput, countEl, prevBtn, nextBtn,
    el('span', { class: 'find-sep' }), replaceInput, replaceBtn, replaceAllBtn,
  ]);

  let matches = [], current = -1;
  const HL_OK = typeof Highlight !== 'undefined' && CSS.highlights;
  const hlAll = HL_OK ? new Highlight() : null;
  const hlCur = HL_OK ? new Highlight() : null;
  if (HL_OK) { CSS.highlights.set('tina-find', hlAll); CSS.highlights.set('tina-find-current', hlCur); }

  function commitEdits() {
    bodyWrap.querySelectorAll('.seg-edit:not(.inaudible)').forEach(span => {
      const seg = t.segments.find(s => String(s.id) === span.dataset.segId);
      if (seg) { const txt = span.textContent.trim(); if (txt !== (seg.text || '')) seg.text = txt; }
    });
  }
  function clearHighlights() {
    if (HL_OK) { hlAll.clear(); hlCur.clear(); }
    bodyWrap.querySelectorAll('.seg-edit.find-current').forEach(s => s.classList.remove('find-current'));
  }
  function computeMatches() {
    matches = [];
    const q = findInput.value;
    if (!q) return;
    const ql = q.toLowerCase();
    bodyWrap.querySelectorAll('.seg-edit:not(.inaudible)').forEach(span => {
      const tl = span.textContent.toLowerCase();
      let i = tl.indexOf(ql);
      while (i !== -1) { matches.push({ segId: span.dataset.segId, start: i, end: i + q.length }); i = tl.indexOf(ql, i + q.length); }
    });
  }
  function spanById(id) { return bodyWrap.querySelector(`.seg-edit[data-seg-id="${CSS.escape(id)}"]`); }
  function renderHighlights() {
    clearHighlights();
    if (!matches.length) return;
    if (HL_OK) {
      matches.forEach((m, idx) => {
        const node = spanById(m.segId)?.firstChild;
        if (!node || node.nodeType !== Node.TEXT_NODE) return;
        const r = new Range();
        try { r.setStart(node, m.start); r.setEnd(node, m.end); } catch { return; }
        (idx === current ? hlCur : hlAll).add(r);
      });
    } else if (matches[current]) {
      spanById(matches[current].segId)?.classList.add('find-current');
    }
  }
  function updateCount() {
    countEl.textContent = matches.length ? `${current + 1}/${matches.length}` : (findInput.value ? '0/0' : '');
  }
  function scrollToCurrent() {
    if (matches[current]) spanById(matches[current].segId)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
  function updateFind(keepCurrent) {
    commitEdits();
    computeMatches();
    if (!matches.length) current = -1;
    else if (!keepCurrent || current < 0 || current >= matches.length) current = 0;
    renderHighlights(); updateCount();
  }
  function refreshFind() { if (findInput.value) updateFind(true); else clearHighlights(); }
  function gotoMatch(delta) {
    if (!matches.length) return;
    current = (current + delta + matches.length) % matches.length;
    renderHighlights(); updateCount(); scrollToCurrent();
  }
  function replaceAllCI(text, q, repl) {
    const ql = q.toLowerCase(), tl = text.toLowerCase();
    let out = '', i = 0, idx;
    while ((idx = tl.indexOf(ql, i)) !== -1) { out += text.slice(i, idx) + repl; i = idx + q.length; }
    return out + text.slice(i);
  }
  async function doReplace(all) {
    commitEdits();
    const q = findInput.value;
    if (!q || !matches.length) return;
    const repl = replaceInput.value;
    pushUndo();
    if (all) {
      for (const seg of t.segments) {
        if (seg.note === 'overlapping_speech' || !seg.text) continue;
        seg.text = replaceAllCI(seg.text, q, repl);
      }
    } else {
      const m = matches[current];
      const seg = m && t.segments.find(s => String(s.id) === m.segId);
      if (seg) seg.text = seg.text.slice(0, m.start) + repl + seg.text.slice(m.end);
    }
    await saveSegments();
    renderBody();          // rebuilds spans + refreshFind()
    scrollToCurrent();
  }
  findInput.addEventListener('input', () => { updateFind(false); scrollToCurrent(); });
  findInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); gotoMatch(e.shiftKey ? -1 : 1); }
    else if (e.key === 'Escape') { e.preventDefault(); findInput.value = ''; updateFind(false); }
  });
  prevBtn.addEventListener('click', () => gotoMatch(-1));
  nextBtn.addEventListener('click', () => gotoMatch(1));
  replaceBtn.addEventListener('click', () => doReplace(false));
  replaceAllBtn.addEventListener('click', () => doReplace(true));

  // ── Copy & export ────────────────────────────────────────────────────────────
  const COPY_SPK_KEY = 'tina.copy.speakers', COPY_TS_KEY = 'tina.copy.timestamps';
  const copyOpts = {
    speakers: localStorage.getItem(COPY_SPK_KEY) !== '0',   // default on
    timestamps: localStorage.getItem(COPY_TS_KEY) === '1',  // default off
  };

  function buildTranscriptText({ speakers, timestamps }) {
    const out = [];
    for (const turn of turnsOf()) {
      const head = [];
      if (speakers) head.push(turn.speaker);
      if (timestamps) head.push(`[${fmtClock(turn.segments[0].start)} – ${fmtClock(turn.segments[turn.segments.length - 1].end)}]`);
      if (head.length) out.push(head.join('  '));
      out.push(turn.segments.map(s => s.note === 'overlapping_speech' ? '[inaudible]' : (s.text || '')).join(' ').replace(/\s+/g, ' ').trim());
      out.push('');
    }
    return out.join('\n').trim() + '\n';
  }
  function safeName(ext) { return `${(t.name || 'transcript').replace(/[^\w.-]+/g, '_')}.${ext}`; }
  function download(filename, content, mime) {
    const url = URL.createObjectURL(new Blob([content], { type: mime }));
    const a = el('a', { href: url, download: filename });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function copyTranscript() {
    commitEdits();
    const text = buildTranscriptText(copyOpts);
    try {
      await navigator.clipboard.writeText(text);
      toast('Transcript copied to clipboard');
    } catch {
      const ta = el('textarea', { style: 'position:fixed;opacity:0' }); ta.value = text;
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); toast('Transcript copied to clipboard'); }
      catch { toast('Could not copy'); }
      ta.remove();
    }
  }

  const copyBtn = el('button', { class: 'toolbar-btn', title: 'Copy transcript to clipboard', onclick: copyTranscript }, 'Copy');
  const copyOptsBtn = el('button', { class: 'toolbar-btn caret-btn', title: 'Copy options', onclick: (e) => { e.stopPropagation(); openCopyOpts(); } }, '▾');
  const copyGroup = el('div', { class: 'btn-group' }, [copyBtn, copyOptsBtn]);

  function openCopyOpts() {
    closeToolbarMenus();
    const toggleRow = (label, key, storeKey) => {
      const row = el('div', { class: 'tb-menu-item toggle', onclick: (e) => {
        e.stopPropagation();
        copyOpts[key] = !copyOpts[key];
        localStorage.setItem(storeKey, copyOpts[key] ? '1' : '0');
        row.classList.toggle('on', copyOpts[key]);
      } }, [el('span', { class: 'tb-check' }), label]);
      row.classList.toggle('on', copyOpts[key]);
      return row;
    };
    positionMenu(el('div', { class: 'tb-menu' }, [
      toggleRow('Include speaker names', 'speakers', COPY_SPK_KEY),
      toggleRow('Include timestamps', 'timestamps', COPY_TS_KEY),
    ]), copyOptsBtn);
  }

  const exportBtn = el('button', { class: 'toolbar-btn', title: 'Export transcript', onclick: (e) => { e.stopPropagation(); openExport(); } }, ['Export', el('span', { class: 'caret' }, '▾')]);

  function openExport() {
    closeToolbarMenus();
    const item = (label, fn) => el('div', { class: 'tb-menu-item', onclick: (e) => { e.stopPropagation(); closeToolbarMenus(); fn(); } }, label);
    positionMenu(el('div', { class: 'tb-menu' }, [
      item('Plain text (.txt)', () => { commitEdits(); download(safeName('txt'), buildTranscriptText({ speakers: true, timestamps: true }), 'text/plain'); }),
      item('JSON (.json)', () => { commitEdits(); download(safeName('json'), JSON.stringify(t, null, 2), 'application/json'); }),
    ]), exportBtn);
  }

  const undoBtn = el('button', { class: 'toolbar-btn caret-btn undo-redo', title: 'Undo (Cmd/Ctrl+Z)', onclick: undo }, '↺');
  const redoBtn = el('button', { class: 'toolbar-btn caret-btn undo-redo', title: 'Redo (Shift+Cmd/Ctrl+Z)', onclick: redo }, '↻');
  const undoGroup = el('div', { class: 'btn-group' }, [undoBtn, redoBtn]);

  const toolbar = el('div', { class: 'tx-toolbar' }, [findBar, el('span', { style: 'margin-left:auto' }), undoGroup, copyGroup, exportBtn, langToggle]);
  transcriptPane.append(toolbar, bodyWrap);

  // ── Reading view ─────────────────────────────────────────────────────────────
  function renderReading(container) {
    let splitting = false;

    function newSegId() {
      const ids = new Set(t.segments.map(s => String(s.id)));
      let n = 0; while (ids.has(String(n))) n++;
      return String(n);
    }
    function focusSegStart(id) {
      const sp = container.querySelector(`.seg-edit[data-seg-id="${CSS.escape(String(id))}"]`);
      if (!sp) return;
      sp.focus();
      const r = document.createRange();
      r.setStart(sp.firstChild || sp, 0); r.collapse(true);
      const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
    }

    function splitAt(seg, span) {
      const sel = getSelection();
      const offset = (sel && sel.rangeCount && span.contains(sel.anchorNode)) ? sel.anchorOffset : 0;
      const full = span.textContent;
      const before = full.slice(0, offset).trim();
      const after = full.slice(offset).trim();

      const idx = t.segments.findIndex(s => String(s.id) === String(seg.id));
      const target = t.segments[idx];
      target.text = full.trim();
      let focusId = null;

      if (!after) {
        const next = t.segments[idx + 1];
        if (next && !next.break_before) { pushUndo(); next.break_before = true; focusId = next.id; }  // split after target
        else return;
      } else if (!before) {
        if (idx === 0 || target.break_before) return;   // already starts a turn
        pushUndo(); target.break_before = true; focusId = target.id;
      } else {
        const totalChars = full.trim().length || 1;
        let mid = target.start + (target.end - target.start) * (before.length / totalChars);
        mid = Math.min(target.end, Math.max(target.start, Math.round(mid * 1000) / 1000));
        pushUndo();
        const newSeg = { id: newSegId(), speaker: target.speaker, start: mid, end: target.end, text: after, lang: target.lang, note: target.note || 'ok', break_before: true };
        target.end = mid; target.text = before;
        t.segments.splice(idx + 1, 0, newSeg);
        focusId = newSeg.id;
      }

      splitting = true;
      renderBody();
      if (focusId != null) focusSegStart(focusId);
      saveSegments();
    }

    // Backspace at the very start of a turn-leading segment merges it into the previous
    // turn (same speaker only) — the inverse of split-on-Enter ("delete the newline").
    function caretAtSpanStart(span) {
      const sel = getSelection();
      return !!(sel && sel.rangeCount && sel.getRangeAt(0).collapsed
                && span.contains(sel.anchorNode) && sel.anchorOffset === 0);
    }
    function canMergeIntoPrev(seg) {
      const idx = t.segments.findIndex(s => String(s.id) === String(seg.id));
      const prev = t.segments[idx - 1];
      return idx > 0 && !!seg.break_before && prev && prev.speaker === seg.speaker;
    }
    function mergeIntoPrev(seg) {
      pushUndo();
      seg.break_before = false;   // drop the boundary; ensureTurnBoundaries won't re-add it (same speaker)
      renderBody();
      focusSegStart(seg.id);
      saveSegments('Turns merged');
    }

    // Floating language chip shown on hover / active.
    const chip = el('button', { class: 'seg-chip', style: 'display:none' });
    let chipSpan = null, hideTimer = null;
    function positionChip(span) {
      // Anchor to the segment's FIRST line box (a wrapped segment's bounding rect
      // would span both lines and mis-place the chip).
      const r = span.getClientRects()[0] || span.getBoundingClientRect();
      const w = container.getBoundingClientRect();
      chip.style.top = `${r.top - w.top}px`;
      chip.style.left = `${r.left - w.left}px`;
    }
    function showChip(seg, span) {
      clearTimeout(hideTimer);
      chipSpan = span;
      const lc = langColor(seg.lang);
      chip.textContent = `${lc.short} ▾`;
      chip.style.background = lc.bg;
      chip.style.color = lc.fg;
      chip.style.borderColor = lc.border;
      chip.style.display = 'inline-flex';
      positionChip(span);
      chip.onclick = (e) => { e.stopPropagation(); const r = chip.getBoundingClientRect(); openSegMenu(seg, r.left, r.bottom + 2); };
    }
    function hideChipSoon() {
      hideTimer = setTimeout(() => { if (chipSpan !== document.activeElement) { chip.style.display = 'none'; chipSpan = null; } }, 200);
    }
    chip.addEventListener('mouseenter', () => clearTimeout(hideTimer));
    chip.addEventListener('mouseleave', hideChipSoon);

    const body = el('div', { class: 'transcript-body' });
    for (const turn of turnsOf()) {
      const c = colorOf(turn.speaker);
      const last = turn.segments[turn.segments.length - 1];
      // Play the turn as one continuous span (no seeking between segments — the
      // inter-segment "gaps" are mostly continuous speech the diarizer split, so
      // playing straight through sounds natural). We just track position to stop at
      // the end and highlight the segment currently playing.
      const segSpans = [];
      const play = el('button', {
        class: 'seg-play', title: 'Play turn', 'data-turn-id': turn.segments[0].id,
        onclick: () => playRange(audio, play, turn.segments[0].start, last.end, {
          onTick: (ct) => highlightPlaying(segSpans, ct),
          onStop: () => highlightPlaying(segSpans, -1),
        }),
      }, '▶');

      const head = el('div', { class: 'turn-head reading-head' }, [
        play, speakerControl(turn),
        el('span', { class: 'turn-time' }, `${fmtClock(turn.segments[0].start)}–${fmtClock(last.end)}`),
      ]);

      const para = el('p', { class: 'reading-text' });
      for (const seg of turn.segments) {
        const inaudible = seg.note === 'overlapping_speech';
        const langClass = seg.lang ? ` lang-${seg.lang}` : '';
        const span = el('span', {
          class: 'seg-edit' + langClass + (inaudible ? ' inaudible' : ''),
          'data-seg-id': seg.id,
          contenteditable: inaudible ? 'false' : 'true',
          spellcheck: 'false',
        }, inaudible ? '[inaudible]' : (seg.text || ''));
        segSpans.push({ seg, span });
        if (!inaudible) {
          span.addEventListener('blur', () => {
            if (splitting) return;
            const newText = span.textContent.trim();
            const target = t.segments.find(s => String(s.id) === String(seg.id));
            if (target && newText !== (target.text || '')) { pushUndo(); target.text = newText; saveSegments(); refreshFind(); }
            hideChipSoon();
          });
          span.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); splitAt(seg, span); }
            else if (e.key === 'Backspace' && caretAtSpanStart(span) && canMergeIntoPrev(seg)) {
              e.preventDefault(); mergeIntoPrev(seg);
            }
          });
          span.addEventListener('contextmenu', (e) => { e.preventDefault(); openSegMenu(seg, e.clientX, e.clientY); });
          span.addEventListener('mouseenter', () => showChip(seg, span));
          span.addEventListener('mouseleave', hideChipSoon);
          span.addEventListener('focus', () => showChip(seg, span));
          // Click while idle moves the audio playhead to this segment (then press play).
          span.addEventListener('click', () => { if (!stopActive && audio.paused) audio.currentTime = seg.start; });
        }
        para.appendChild(span);
        para.appendChild(document.createTextNode(' '));
      }
      body.appendChild(el('div', { class: 'turn reading-turn', style: `border-left:3px solid ${c.border}` }, [head, para]));
    }
    container.appendChild(body);
    container.appendChild(chip);
    container.appendChild(el('div', { class: 'player-bar' }, audio));
  }

  function renderBody() {
    ensureTurnBoundaries();
    closeSegMenu();
    clear(bodyWrap);
    renderReading(bodyWrap);
    refreshFind();   // re-highlight matches against the rebuilt spans
  }

  // Expose undo/redo for the module-level keyboard listener.
  viewControls = { undo, redo };
  renderBody();
}

// ── Per-segment / per-turn playback ─────────────────────────────────────────

let activeBtn = null;
let stopActive = null;

// Play [start, end] continuously, preserving the real pauses in the recording. A rAF
// loop watches currentTime to stop at the end and to drive optional onTick/onStop.
// Re-invoking with the same button toggles playback off.
function playRange(audio, btn, start, end, opts = {}) {
  const wasActive = btn && btn === activeBtn;
  if (stopActive) stopActive();
  if (wasActive) return;

  let raf = 0;
  function tick() {
    if (audio.currentTime >= end) { stop(); return; }
    if (opts.onTick) opts.onTick(audio.currentTime);
    raf = requestAnimationFrame(tick);
  }
  function stop() {
    cancelAnimationFrame(raf);
    audio.pause();
    if (btn) btn.textContent = '▶';
    if (opts.onStop) opts.onStop();
    activeBtn = null; stopActive = null;
  }
  activeBtn = btn || null; stopActive = stop;
  if (btn) btn.textContent = '⏸';
  audio.currentTime = start;
  audio.play();
  raf = requestAnimationFrame(tick);
}

// Stop any active playback. Called by the router when leaving the transcript view so
// the rAF loop and audio don't keep running after the view is torn down.
export function stopPlayback() {
  if (stopActive) stopActive();
}

// Highlight the segment span whose range contains the current playback time
// (pass ct = -1 to clear).
function highlightPlaying(segSpans, ct) {
  for (const { seg, span } of segSpans) {
    span.classList.toggle('seg-playing', ct >= seg.start && ct < seg.end);
  }
}

// ── Context menu lifecycle ──────────────────────────────────────────────────

function closeSegMenu() {
  document.querySelectorAll('.seg-menu').forEach(m => m.remove());
}
document.addEventListener('click', closeSegMenu);
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeSegMenu(); });

// Toolbar dropdown menus (copy options, export).
function closeToolbarMenus() {
  document.querySelectorAll('.tb-menu').forEach(m => m.remove());
}
function positionMenu(menu, anchor) {
  document.body.appendChild(menu);
  const r = anchor.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(r.left, innerWidth - menu.offsetWidth - 8))}px`;
  menu.style.top = `${r.bottom + 4}px`;
}
document.addEventListener('click', closeToolbarMenus);
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeToolbarMenus(); });

function fmtClock(s) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

// ── Keyboard shortcuts (transcript view only) ───────────────────────────────
// Set by the active renderTranscript; the listener no-ops on other views.
let viewControls = null;
document.addEventListener('keydown', (e) => {
  if (!location.hash.startsWith('#/t/') || !viewControls) return;
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
    const ae = document.activeElement;
    // Keep the browser's native undo in the find/replace text fields; everywhere else
    // (including the contenteditable segments) use our segment-level undo.
    if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA')) return;
    e.preventDefault();
    if (e.shiftKey) viewControls.redo(); else viewControls.undo();
  }
});
