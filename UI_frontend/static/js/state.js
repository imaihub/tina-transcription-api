// Shared client state: the "active folder" new transcriptions default to.
// Persisted in localStorage so it survives reloads; falls back to the default
// (first) folder when unset or pointing at a deleted folder.

const KEY = 'tina.activeFolderId';

export function getActiveFolderId() {
  const v = localStorage.getItem(KEY);
  return v ? Number(v) : null;
}

export function setActiveFolderId(id) {
  if (id == null) localStorage.removeItem(KEY);
  else localStorage.setItem(KEY, String(id));
}

// Resolve the active folder against the current folder list, falling back to the
// default (first) folder. Returns the folder object, or null if there are none.
export function resolveActiveFolder(folders) {
  if (!folders || !folders.length) return null;
  const id = getActiveFolderId();
  return folders.find(f => f.id === id) || folders[0];
}
