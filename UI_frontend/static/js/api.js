// Thin fetch wrappers around the UI_frontend backend REST API.

async function json(resp) {
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { detail = (await resp.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return resp.json();
}

const jsonReq = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

function qs(params) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== undefined && v !== null && v !== '') p.set(k, v);
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

export const api = {
  // Folders
  listFolders:  ()            => fetch('/api/folders').then(json),
  createFolder: (name)        => fetch('/api/folders', jsonReq('POST', { name })).then(json),
  updateFolder: (id, body)    => fetch(`/api/folders/${id}`, jsonReq('PATCH', body)).then(json),
  deleteFolder: (id)          => fetch(`/api/folders/${id}`, { method: 'DELETE' }).then(json),

  // Transcriptions
  listTranscriptions: (params) => fetch(`/api/transcriptions${qs(params)}`).then(json),
  getTranscription:   (id)     => fetch(`/api/transcriptions/${id}`).then(json),
  updateTranscription:(id, b)  => fetch(`/api/transcriptions/${id}`, jsonReq('PATCH', b)).then(json),
  deleteTranscription:(id)     => fetch(`/api/transcriptions/${id}`, { method: 'DELETE' }).then(json),

  // Upload + transcribe (multipart). `form` is a FormData.
  createTranscription: (form)  => fetch('/api/transcriptions', { method: 'POST', body: form }).then(json),

  audioUrl: (id) => `/api/transcriptions/${id}/audio`,
};
