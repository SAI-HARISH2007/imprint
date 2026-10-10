"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, api, b64ToBlob, type MarkResult, type RegisterResult, type Rec } from "@/lib/api";
import { createPasskey, getStoredPasskey, passkeySupported, signChallenge, type StoredPasskey } from "@/lib/passkey";
import { saveMarked } from "@/lib/session";
import { keepMarked } from "@/lib/store";
import { MarkDiff } from "@/components/markdiff";
import { btnAccent, btnGhost, btnPrimary, Dropzone, RecordFacts, Spinner } from "@/components/ui";
import { short } from "@/lib/format";

type Phase = "idle" | "marking" | "signing" | "confirming" | "done" | "error";

const STEPS: { key: Phase; label: string }[] = [
  { key: "marking", label: "Hiding the ID in your image" },
  { key: "signing", label: "Waiting for your passkey" },
  { key: "confirming", label: "Confirming on Monad" },
];

export default function RegisterPage() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [earlier, setEarlier] = useState<Rec | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [marked, setMarked] = useState<MarkResult | null>(null);
  const [markedImage, setMarkedImage] = useState<string | null>(null);
  const [result, setResult] = useState<RegisterResult | null>(null);
  const [passkey, setPasskey] = useState<StoredPasskey | null>(null);
  const [unsupported, setUnsupported] = useState<string | null>(null);

  useEffect(() => {
    // Read browser-only state after mount so server and client markup match.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPasskey(getStoredPasskey());
    setUnsupported(passkeySupported());
  }, []);

  function reset() {
    setPhase("idle");
    setError(null);
    setEarlier(null);
    setFile(null);
    setPreview(null);
    setMarked(null);
    setMarkedImage(null);
    setResult(null);
  }

  async function run(f: File) {
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setError(null);
    setEarlier(null);
    try {
      setPhase("marking");
      const m = await api.mark(f, f.name);
      setMarked(m);

      setPhase("signing");
      let pk = getStoredPasskey();
      if (!pk) pk = await createPasskey();
      setPasskey(pk);
      const { challenge } = await api.challenge(m.watermark_id, m.fingerprint);
      const auth = await signChallenge(pk, challenge);

      setPhase("confirming");
      const res = await api.register({
        watermark_id: m.watermark_id,
        fingerprint: "0x" + m.fingerprint,
        auth,
        qx: pk.qx,
        qy: pk.qy,
        claim: m.claim,
      });
      setResult(res);
      const outName = f.name.replace(/\.[^.]+$/, "") + "-imprint.png";
      if (res.image_png_base64) {
        setMarkedImage(res.image_png_base64);
        saveMarked(res.image_png_base64, outName);
        await keepMarked(m.watermark_id, b64ToBlob(res.image_png_base64), outName);
      }
      setPhase("done");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const d = e.detail as { earlier?: Rec };
        setEarlier(d.earlier ?? null);
      }
      setError(
        e instanceof DOMException && e.name === "NotAllowedError"
          ? "The passkey prompt was cancelled or timed out. Nothing was registered."
          : e instanceof Error
            ? e.message
            : "Something went wrong.",
      );
      setPhase("error");
    }
  }

  async function checkStatus() {
    if (!marked) return;
    setError(null);
    try {
      const rec = await api.record(marked.watermark_id);
      setResult({
        tx_hash: rec.tx_hash ?? "",
        block: rec.block,
        timestamp: rec.timestamp,
        gas_used: 0,
        gas_limit: 0,
        seconds: 0,
        signer: rec.signer,
        explorer_url: rec.tx_url ?? "",
        record: rec,
        receipt: null,
      });
      const outName = file ? file.name.replace(/\.[^.]+$/, "") + "-imprint.png" : "imprint.png";
      try {
        // The image was withheld until the ID landed; now it is on chain, redeem the claim.
        const c = await api.claim(marked.claim);
        setMarkedImage(c.image_png_base64);
        saveMarked(c.image_png_base64, outName);
        await keepMarked(marked.watermark_id, b64ToBlob(c.image_png_base64), outName);
      } catch {
        // The claim expired, or was already redeemed. The record is still registered.
      }
      setPhase("done");
    } catch {
      setError("Still not on Monad. The registration did not go through; try again.");
    }
  }

  function downloadReceipt() {
    if (!result?.receipt) return;
    const blob = new Blob([JSON.stringify(result.receipt, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `imprint-receipt-${marked?.watermark_id.slice(2, 10) ?? "record"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const downloadHref = markedImage ? `data:image/png;base64,${markedImage}` : undefined;
  const outName = file ? file.name.replace(/\.[^.]+$/, "") + "-imprint.png" : "imprint.png";
  const busy = phase === "marking" || phase === "signing" || phase === "confirming";
  const canCheckStatus = phase === "error" && !!marked && !!file;

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header>
        <h1 className="display text-5xl">Register an image</h1>
        <p className="mt-3 max-w-xl text-ink2">
          Imprint hides a short ID in the picture and records it on Monad, signed with a passkey. You&rsquo;ll download
          a copy that looks the same as the original.
        </p>
      </header>

      {unsupported && <p className="rounded-xl bg-warnbg p-4 text-sm text-warn">{unsupported}</p>}

      {(phase === "idle" || phase === "error") && (
        <Dropzone onFile={run} disabled={!!unsupported}>
          <p className="text-xs text-ink2">
            {passkey ? (
              <>
                Signing as passkey <span className="mono">{short(passkey.qx, 6, 4)}</span> on this device.
              </>
            ) : (
              "The first time, your device will ask you to create a passkey."
            )}
          </p>
        </Dropzone>
      )}

      {phase === "error" && (
        <div className="rise rounded-2xl border border-line bg-badbg p-5 text-sm">
          <p className="font-medium text-bad">{error}</p>
          {earlier && (
            <div className="mt-4 rounded-xl bg-card p-4">
              <RecordFacts r={earlier} label="The earlier registration" />
              <Link href={`/r/${earlier.watermark_id}`} className="mt-2 inline-block underline underline-offset-2">
                Open that record ↗
              </Link>
            </div>
          )}
          <div className="mt-4 flex flex-wrap gap-3">
            {canCheckStatus && (
              <button className={btnPrimary} onClick={checkStatus}>
                Check whether it landed
              </button>
            )}
            <button className={`${btnGhost} ${canCheckStatus ? "" : "mt-0"}`} onClick={reset}>
              Try another image
            </button>
          </div>
        </div>
      )}

      {busy && (
        <section className="rise space-y-6 rounded-2xl border border-line bg-card p-6">
          {preview && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={preview} alt="Your image" className="max-h-64 w-auto rounded-lg" />
          )}
          <ol className="space-y-3">
            {STEPS.map((s, i) => {
              const at = STEPS.findIndex((x) => x.key === phase);
              const state = i < at ? "done" : i === at ? "now" : "todo";
              return (
                <li key={s.key} className={`flex items-center gap-3 text-sm ${state === "todo" ? "text-ink3" : ""}`}>
                  <span
                    className={`flex h-6 w-6 items-center justify-center rounded-full text-xs ${
                      state === "done" ? "bg-okbg text-ok" : state === "now" ? "bg-accent text-accentink" : "bg-paper2"
                    }`}
                  >
                    {state === "done" ? "✓" : i + 1}
                  </span>
                  {state === "now" ? <Spinner label={s.label} /> : s.label}
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {phase === "done" && marked && result && (
        <section className="rise space-y-6">
          <div className="overflow-hidden rounded-2xl border border-line bg-card">
            <div className="flex items-start gap-4 bg-okbg p-6">
              <span className="display text-5xl leading-none text-ok" aria-hidden>
                ✓
              </span>
              <div>
                <h2 className="display text-3xl text-ok">Registered on Monad</h2>
                <p className="mt-1 text-sm">
                  Confirmed in {result.seconds}s, in block {result.block.toLocaleString()}. Download the marked image
                  below and share that one.
                </p>
              </div>
            </div>
            <div className="grid gap-6 p-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
              {markedImage ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`data:image/png;base64,${markedImage}`}
                  alt="Your marked image"
                  className="max-h-72 w-auto rounded-lg"
                />
              ) : (
                <p className="self-center text-sm text-ink2">
                  The marked image is no longer available in this browser session. Register the same file again to
                  recover a marked copy.
                </p>
              )}
              {result.record && <RecordFacts r={result.record} />}
            </div>
            <div className="flex flex-wrap gap-3 border-t border-line p-6">
              {downloadHref && (
                <a className={btnPrimary} href={downloadHref} download={outName}>
                  Download marked image
                </a>
              )}
              <Link className={btnAccent} href="/stress">
                Run the stress test on it
              </Link>
              <Link className={btnGhost} href={`/r/${result.record?.watermark_id ?? marked.watermark_id}`}>
                Open the record
              </Link>
              {result.receipt && (
                <button className={btnGhost} onClick={downloadReceipt}>
                  Download receipt (JSON)
                </button>
              )}
              <button className={btnGhost} onClick={reset}>
                Register another
              </button>
            </div>
          </div>
          {file && <MarkDiff original={file} markedB64={marked.image_png_base64} />}
          {!(marked.self_test.png && marked.self_test.jpeg70) && (
            <p className="rounded-xl bg-warnbg p-4 text-sm text-warn">
              This image is hard to mark: the hidden ID did not read back reliably after a test copy. It is registered,
              but copies will mostly be matched by how they look, not by the hidden ID.
            </p>
          )}
          <p className="text-xs text-ink2">
            Share and test the <span className="text-ink">downloaded marked image</span>, not your original file: only
            the marked one carries the hidden ID. Imprint did not keep your image. Only the ID, a fingerprint of how it looks, the signer, and the time are
            on Monad.
          </p>
        </section>
      )}
    </div>
  );
}
