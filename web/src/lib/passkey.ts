/**
 * Passkeys (WebAuthn, P-256). The browser never exposes the private key. It signs a challenge
 * and we send the pieces the Monad registry needs to check that signature on-chain.
 */

const STORE = "imprint.passkey.v1";
const N = BigInt("0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551");

export type StoredPasskey = { id: string; qx: string; qy: string };

export type Assertion = {
  r: string;
  s: string;
  challengeIndex: number;
  typeIndex: number;
  authenticatorData: string;
  clientDataJSON: string;
};

const toHex = (u: Uint8Array) => "0x" + Array.from(u, (b) => b.toString(16).padStart(2, "0")).join("");
const fromHex = (h: string) => {
  const s = h.replace(/^0x/, "");
  return Uint8Array.from(s.match(/.{2}/g) ?? [], (b) => parseInt(b, 16));
};
const b64url = (u: Uint8Array) =>
  btoa(String.fromCharCode(...u)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const fromB64url = (s: string) => {
  const p = s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4);
  return Uint8Array.from(atob(p), (c) => c.charCodeAt(0));
};

export function passkeySupported(): string | null {
  if (typeof window === "undefined") return null;
  if (!window.isSecureContext) return "Passkeys need a secure connection (https or localhost).";
  if (!("credentials" in navigator) || typeof PublicKeyCredential === "undefined")
    return "This browser does not support passkeys.";
  return null;
}

export function getStoredPasskey(): StoredPasskey | null {
  try {
    const raw = localStorage.getItem(STORE);
    return raw ? (JSON.parse(raw) as StoredPasskey) : null;
  } catch {
    return null;
  }
}

export function forgetPasskey() {
  try {
    localStorage.removeItem(STORE);
  } catch {
    /* ignore */
  }
}

export async function createPasskey(): Promise<StoredPasskey> {
  const cred = (await navigator.credentials.create({
    publicKey: {
      challenge: crypto.getRandomValues(new Uint8Array(32)),
      rp: { name: "Imprint", id: location.hostname },
      user: {
        id: crypto.getRandomValues(new Uint8Array(16)),
        name: "imprint-creator",
        displayName: "Imprint creator",
      },
      pubKeyCredParams: [{ type: "public-key", alg: -7 }], // ES256 = P-256
      authenticatorSelection: { userVerification: "required", residentKey: "preferred" },
      attestation: "none",
      timeout: 60_000,
    },
  })) as PublicKeyCredential | null;
  if (!cred) throw new Error("Passkey creation was cancelled.");

  const resp = cred.response as AuthenticatorAttestationResponse;
  const spki = new Uint8Array(resp.getPublicKey() ?? new ArrayBuffer(0));
  if (spki.length < 64) throw new Error("This passkey did not expose a public key.");
  const xy = spki.slice(spki.length - 64); // SPKI ends with the uncompressed point x||y
  const pk: StoredPasskey = { id: b64url(new Uint8Array(cred.rawId)), qx: toHex(xy.slice(0, 32)), qy: toHex(xy.slice(32)) };
  localStorage.setItem(STORE, JSON.stringify(pk));
  return pk;
}

function derToRS(der: Uint8Array): { r: bigint; s: bigint } {
  // 30 len 02 rlen r 02 slen s
  let i = 2;
  if (der[1] & 0x80) i += der[1] & 0x7f;
  if (der[i] !== 0x02) throw new Error("Unexpected signature format.");
  const rl = der[i + 1];
  const r = der.slice(i + 2, i + 2 + rl);
  i = i + 2 + rl;
  if (der[i] !== 0x02) throw new Error("Unexpected signature format.");
  const sl = der[i + 1];
  const s = der.slice(i + 2, i + 2 + sl);
  const big = (u: Uint8Array) => BigInt(toHex(u.length ? u : new Uint8Array([0])));
  return { r: big(r), s: big(s) };
}

const pad32 = (n: bigint) => "0x" + n.toString(16).padStart(64, "0");

export async function signChallenge(pk: StoredPasskey, challengeHex: string): Promise<Assertion> {
  const got = (await navigator.credentials.get({
    publicKey: {
      challenge: fromHex(challengeHex),
      rpId: location.hostname,
      allowCredentials: [{ type: "public-key", id: fromB64url(pk.id) }],
      userVerification: "required",
      timeout: 60_000,
    },
  })) as PublicKeyCredential | null;
  if (!got) throw new Error("Signing was cancelled.");

  const r = got.response as AuthenticatorAssertionResponse;
  const clientDataJSON = new TextDecoder().decode(r.clientDataJSON);
  let { r: rr, s: ss } = derToRS(new Uint8Array(r.signature));
  if (ss > N / BigInt(2)) ss = N - ss; // the contract rejects the "high s" twin of a signature

  return {
    r: pad32(rr),
    s: pad32(ss),
    challengeIndex: clientDataJSON.indexOf('"challenge":"'),
    typeIndex: clientDataJSON.indexOf('"type":"'),
    authenticatorData: toHex(new Uint8Array(r.authenticatorData)),
    clientDataJSON,
  };
}
