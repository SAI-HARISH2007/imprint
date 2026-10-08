/**
 * Keep the marked image in this browser, so it can be downloaded again later.
 * Imprint's server never stores images, so this is the only copy besides the one you download.
 * IndexedDB has room for large photos, unlike localStorage.
 */
const DB = "imprint";
const TABLE = "marked";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(TABLE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function keepMarked(id: string, blob: Blob, name: string): Promise<void> {
  try {
    const db = await open();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(TABLE, "readwrite");
      tx.objectStore(TABLE).put({ blob, name }, id.toLowerCase());
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    /* private mode or blocked storage: the download button is still there */
  }
}

export async function loadKept(id: string): Promise<{ blob: Blob; name: string } | null> {
  try {
    const db = await open();
    return await new Promise((resolve, reject) => {
      const req = db.transaction(TABLE).objectStore(TABLE).get(id.toLowerCase());
      req.onsuccess = () => resolve((req.result as { blob: Blob; name: string }) ?? null);
      req.onerror = () => reject(req.error);
    });
  } catch {
    return null;
  }
}
