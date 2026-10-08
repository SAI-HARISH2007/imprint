"use client";

import { useEffect, useState } from "react";
import { api, type VerifyResult } from "@/lib/api";
import { DEMO_CHECKS, fetchDemo } from "@/lib/demo";
import { Dropzone, Spinner, VerdictCard, btnGhost } from "@/components/ui";

export default function VerifyPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<VerifyResult | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [name, setName] = useState<string>("");

  useEffect(() => () => void (preview && URL.revokeObjectURL(preview)), [preview]);

  async function check(f: File) {
    setBusy(true);
    setError(null);
    setRes(null);
    setName(f.name);
    setPreview(URL.createObjectURL(f));
    try {
      setRes(await api.verify(f, f.name));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header>
        <h1 className="display text-5xl">Check an image</h1>
        <p className="mt-3 max-w-xl text-ink2">
          Drop in any copy, even a compressed, resized or screenshotted one. No account needed. Imprint reads the
          hidden ID, looks it up on Monad, and compares how the picture looks.
        </p>
      </header>

      <Dropzone onFile={check} disabled={busy}>
        <div className="flex flex-wrap justify-center gap-2">
          <span className="w-full text-xs text-ink2">No image handy? Try an example:</span>
          {DEMO_CHECKS.map((d) => (
            <button
              key={d.file}
              type="button"
              disabled={busy}
              className={`${btnGhost} !px-3 !py-1.5 !text-xs`}
              onClick={async () => check(await fetchDemo(d.file, d.name))}
            >
              {d.label}
            </button>
          ))}
        </div>
      </Dropzone>

      {busy && (
        <div className="rise flex items-center gap-4 rounded-2xl border border-line bg-card p-5">
          {preview && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={preview} alt="" className="h-16 w-auto rounded" />
          )}
          <Spinner label={`Reading ${name} and checking Monad…`} />
        </div>
      )}

      {error && <p className="rise rounded-xl bg-badbg p-4 text-sm text-bad">{error}</p>}

      {res && !busy && (
        <div className="space-y-4">
          {preview && (
            <div className="flex items-center gap-4 text-sm text-ink2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={preview} alt="" className="h-20 w-auto rounded-lg border border-line" />
              <span className="mono">{name}</span>
            </div>
          )}
          <VerdictCard res={res} />
        </div>
      )}
    </div>
  );
}
