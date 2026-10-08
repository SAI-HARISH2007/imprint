/** Hand the image you just registered to the stress test page, within this tab. */
const KEY = "imprint.lastMarked";

export function saveMarked(b64: string, name: string) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ b64, name }));
  } catch {
    /* image too large for session storage: the stress page falls back to upload */
  }
}

export function loadMarked(): { b64: string; name: string } | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
