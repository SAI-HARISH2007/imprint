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
  algorithm: string;
  record: Rec | null;
  earlier: Rec | null;
  registry: { address: string; chain_id: number; url: string };
};

export type MarkResult = {
  watermark_id: string;
  fingerprint: string;
  width: number;
  height: number;
  strength: number;
  self_test: { png: boolean; jpeg70: boolean };
  claim: string;
  claim_expires_in: number;
};

export type ClaimResult = {
  watermark_id: string;
  fingerprint: string;
  image_png_base64: string;
  record: Rec | null;
};

export type Config = {
  chain_id: number;
  registry: string;
  registry_url: string;
  explorer: string;
  fingerprint: { algorithm: string; version: number; bits: number; hex_length: number };
  claim_ttl_seconds: number;
  thresholds: { match: number; near: number; duplicate: number };
};

export type RegisterResult = {
  tx_hash: string;
  block: number;
  timestamp: number;
  gas_used: number;
  gas_limit: number;
  seconds: number;
  signer: string | null;
  explorer_url: string;
  record: Rec | null;
  receipt: Receipt | null;
  image_png_base64?: string;
};

export type Receipt = {
  imprint_receipt: number;
  chain_id: number;
  registry: string;
  watermark_id: string;
  fingerprint: string;
  signer: string;
  timestamp: number;
  block: number;
  tx_hash: string;
  passkey: { qx: string; qy: string } | null;
  relayer_signature?: { address: string; signature: string };
};

export type ReceiptCheck = { name: string; ok: boolean; detail: string };
export type ReceiptResult = { valid: boolean; checks: ReceiptCheck[]; record: Rec | null };

export type StressRow = {
  key: string;
  label: string;
  group: "sharing" | "edit" | "attack";
  verdict: VerdictKey | "error";
  distance: number | null;
  watermark_present: boolean;
  file_hash_matches: boolean;
  thumb: string;
  error?: string;
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
  records: (limit = 8, signer?: string) =>
    fetch(`${API}/records?limit=${limit}${signer ? `&signer=${encodeURIComponent(signer)}` : ""}`).then((r) =>
      handle<{ count: number; records: Rec[] }>(r),
    ),
  record: (id: string) => fetch(`${API}/record/${encodeURIComponent(id)}`).then((r) => handle<Rec>(r)),
  signer: (qx: string, qy: string) =>
    fetch(`${API}/signer?qx=${encodeURIComponent(qx)}&qy=${encodeURIComponent(qy)}`).then((r) =>
      handle<{ signer: string }>(r),
    ),
  receiptVerify: (receipt: unknown) =>
    fetch(`${API}/receipt/verify`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ receipt }),
    }).then((r) => handle<ReceiptResult>(r)),
  mark: (file: Blob, name: string) =>
    fetch(`${API}/mark`, { method: "POST", body: form(file, name) }).then((r) => handle<MarkResult>(r)),
  claim: (token: string) =>
    fetch(`${API}/claim?token=${encodeURIComponent(token)}`).then((r) => handle<ClaimResult>(r)),
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
      handle<{ results: StressRow[]; baseline: { mark_found: boolean; registered: boolean } }>(r),
    ),
};

export function b64ToBlob(b64: string, type = "image/png"): Blob {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type });
}
