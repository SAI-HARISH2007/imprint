"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, api, b64ToBlob, type MarkResult, type RegisterResult, type Rec } from "@/lib/api";
import { createPasskey, getStoredPasskey, passkeySupported, signChallenge, type StoredPasskey } from "@/lib/passkey";
import { saveMarked } from "@/lib/session";
import { keepMarked } from "@/lib/store";
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
  const [result, setResult] = useState<RegisterResult | null>(null);
  const [passkey, setPasskey] = useState<StoredPasskey | null>(null);
  const [unsupported, setUnsupported] = useState<string | null>(null);

  useEffect(() => {
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
      });
      setResult(res);
      const outName = f.name.replace(/\.[^.]+$/, "") + "-imprint.png";
      saveMarked(m.image_png_base64, outName);
      await keepMarked(m.watermark_id, b64ToBlob(m.image_png_base64), outName);
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

  const downloadHref = marked ? URL.createObjectURL(b64ToBlob(marked.image_png_base64)) : undefined;
  const outName = file ? file.name.replace(/\.[^.]+$/, "") + "-imprint.png" : "imprint.png";
  const busy = phase === "marking" || phase === "signing" || phase === "confirming";

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
          <button className={`${btnGhost} mt-4`} onClick={reset}>
            Try another image
          </button>
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
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`data:image/png;base64,${marked.image_png_base64}`}
                alt="Your marked image"
                className="max-h-72 w-auto rounded-lg"
              />
              {result.record && <RecordFacts r={result.record} />}
            </div>
            <div className="flex flex-wrap gap-3 border-t border-line p-6">
              <a className={btnPrimary} href={downloadHref} download={outName}>
                Download marked image
              </a>
              <Link className={btnAccent} href="/stress">
                Run the stress test on it
              </Link>
              <Link className={btnGhost} href={`/r/${result.record?.watermark_id ?? marked.watermark_id}`}>
                Open the record
              </Link>
              <button className={btnGhost} onClick={reset}>
                Register another
              </button>
            </div>
          </div>
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
