// Bootstrap + hash-based view router.

import { renderSidebar, refreshSidebar } from './sidebar.js';
import { renderFolders } from './folders.js';
import { renderNewTranscript } from './upload.js';
import { renderTranscript } from './transcript.js';

const detail = document.getElementById('detail');

function route() {
  const parts = (location.hash || '#/folders').slice(2).split('/'); // 'folders' | 't/5' | 'new'
  const [view, param] = parts;

  if (view === 'new') renderNewTranscript(detail);
  else if (view === 't' && param) renderTranscript(detail, Number(param));
  else renderFolders(detail);

  // Keep the sidebar's active highlight in sync with the route.
  refreshSidebar();
}

window.addEventListener('hashchange', route);

renderSidebar();
route();
