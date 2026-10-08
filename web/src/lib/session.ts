/**
 * Hand the image you just registered to the stress test page.
 * Kept in memory (survives in-app navigation, no size limit) and also in sessionStorage as a backup
 * for page reloads. A large photo can overflow sessionStorage, so memory is the one we rely on.
 */
const KEY = "imprint.lastMarked";
let memory: { b64: string; name: string } | null = null;

export function saveMarked(b64: string, name: string) {
  memory = { b64, name };
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ b64, name }));
  } catch {
    /* too large for session storage: memory still has it */
  }
}

export function loadMarked(): { b64: string; name: string } | null {
  if (memory) return memory;
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
