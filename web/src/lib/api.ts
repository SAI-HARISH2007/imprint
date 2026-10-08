export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Rec = {
  watermark_id: string;
  fingerprint: string;
  signer: string;
  timestamp: number;
  time: string;
  block: number;
  tx_hash: string | null;
  tx_url: string | null;
};

export type VerdictKey = "verified" | "altered" | "likely_match" | "disputed" | "not_found";

export type VerifyResult = {
  verdict: VerdictKey;
  message: string;
  distance: number | null;
  watermark_present: boolean;
  watermark_id: string | null;
  fingerprint: string;
  record: Rec | null;
  earlier: Rec | null;
  registry: { address: string; chain_id: number; url: string };
};

export type MarkResult = {
  watermark_id: string;
  fingerprint: string;
  width: number;
  height: number;
  image_png_base64: string;
};

export type Config = {
  chain_id: number;
  registry: string;
  registry_url: string;
  explorer: string;
  thresholds: { match: number; near: number; duplicate: number };
};

export type RegisterResult = {
  tx_hash: string;
  block: number;
  timestamp: number;
  gas_used: number;
  seconds: number;
  signer: string | null;
  explorer_url: string;
  record: Rec | null;
};

export type StressRow = {
  key: string;
  label: string;
  group: "sharing" | "edit" | "attack";
  verdict: VerdictKey;
  distance: number | null;
  watermark_present: boolean;
  file_hash_matches: boolean;
  thumb: string;
};

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    const msg =
      typeof detail === "string"
        ? detail
        : typeof detail === "object" && detail && "message" in detail
          ? String((detail as { message: unknown }).message)
          : `Request failed (${status})`;
    super(msg);
    this.status = status;
    this.detail = detail;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

function form(file: Blob, name: string, extra?: Record<string, Blob>) {
  const f = new FormData();
  f.append("file", file, name);
  for (const [k, v] of Object.entries(extra ?? {})) f.append(k, v, k);
  return f;
}

export const api = {
  config: () => fetch(`${API}/config`).then((r) => handle<Config>(r)),
  records: (limit = 8) =>
    fetch(`${API}/records?limit=${limit}`).then((r) => handle<{ count: number; records: Rec[] }>(r)),
  record: (id: string) => fetch(`${API}/record/${id}`).then((r) => handle<Rec>(r)),
  mark: (file: Blob, name: string) =>
    fetch(`${API}/mark`, { method: "POST", body: form(file, name) }).then((r) => handle<MarkResult>(r)),
  challenge: (watermark_id: string, fingerprint: string) =>
    fetch(`${API}/challenge?watermark_id=${watermark_id}&fingerprint=0x${fingerprint}`).then((r) =>
      handle<{ challenge: string }>(r),
    ),
  register: (body: unknown) =>
    fetch(`${API}/register`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }).then((r) => handle<RegisterResult>(r)),
  verify: (file: Blob, name: string) =>
    fetch(`${API}/verify`, { method: "POST", body: form(file, name) }).then((r) => handle<VerifyResult>(r)),
  stress: (file: Blob, name: string, other?: Blob) =>
    fetch(`${API}/stress`, { method: "POST", body: form(file, name, other ? { other } : undefined) }).then((r) =>
      handle<{ results: StressRow[] }>(r),
    ),
};

export function b64ToBlob(b64: string, type = "image/png"): Blob {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type });
}
