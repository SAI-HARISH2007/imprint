"use client";

import { useRef, useState, type ReactNode } from "react";
import type { Rec, VerdictKey, VerifyResult } from "@/lib/api";
import { VERDICTS, short, when } from "@/lib/format";

const MAX_BYTES = 30 * 1024 * 1024;

export const btn =
  "inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";
export const btnPrimary = `${btn} bg-ink text-paper hover:opacity-90`;
export const btnAccent = `${btn} bg-accent text-accentink hover:opacity-90`;
export const btnGhost = `${btn} border border-line text-ink hover:bg-paper2`;

export function Chip({ verdict, label }: { verdict: VerdictKey; label?: string }) {
  const v = VERDICTS[verdict];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${v.bg} ${v.fg}`}>
      <span aria-hidden>{v.mark}</span>
      {label ?? v.short}
    </span>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink2" role="status">
      <span className="pulse-dot inline-block h-2 w-2 rounded-full bg-accent" />
      {label}
    </span>
  );
}

export function Dropzone({
  onFile,
  disabled,
  hint = "Drop an image here, or click to choose one",
  children,
}: {
  onFile: (f: File) => void;
  disabled?: boolean;
  hint?: string;
  children?: ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  function pick(f: File) {
    if (disabled) return;
    if (f.type && !f.type.startsWith("image/")) {
      setLocalError("That file is not an image. Use PNG, JPEG or WebP.");
      return;
    }
    if (f.size > MAX_BYTES) {
      setLocalError(`That image is ${(f.size / 1e6).toFixed(1)} MB; the limit is 30 MB.`);
      return;
    }
    setLocalError(null);
    onFile(f);
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) pick(f);
      }}
      className={`rounded-2xl border border-dashed p-8 text-center transition-colors ${
        over ? "border-accent bg-paper2" : "border-line bg-card"
      } ${disabled ? "opacity-60" : ""}`}
    >
      <input
        ref={input}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="sr-only"
        disabled={disabled}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) pick(f);
          e.target.value = "";
        }}
      />
      <button type="button" disabled={disabled} onClick={() => input.current?.click()} className="w-full">
        <span className="display block text-2xl">{hint}</span>
        <span className="mt-1 block text-sm text-ink2">PNG, JPEG or WebP, up to 30 MB</span>
      </button>
      {localError && <p className="mt-3 text-sm text-bad">{localError}</p>}
      {children && <div className="mt-5">{children}</div>}
    </div>
  );
}

export function Fact({ k, children, mono }: { k: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 border-t border-line py-3 first:border-t-0 sm:flex-row sm:gap-6">
      <dt className="w-44 shrink-0 text-sm text-ink2">{k}</dt>
      <dd className={`min-w-0 break-words text-sm ${mono ? "mono" : ""}`}>{children}</dd>
    </div>
  );
}

export function RecordFacts({ r, label = "Registration" }: { r: Rec; label?: string }) {
  return (
    <div>
      <h3 className="mb-1 text-xs font-medium uppercase tracking-wider text-ink3">{label}</h3>
      <dl>
        <Fact k="Signer (passkey ID)" mono>
          {r.signer}
        </Fact>
        <Fact k="Registered at">{when(r.time)}</Fact>
        <Fact k="Monad block" mono>
          {r.block.toLocaleString()}
        </Fact>
        <Fact k="Watermark ID" mono>
          {short(r.watermark_id, 10, 8)}
        </Fact>
        <Fact k="Transaction">
          {r.tx_url ? (
            <a className="mono underline underline-offset-2" href={r.tx_url} target="_blank" rel="noreferrer">
              {short(r.tx_hash, 10, 8)} ↗
            </a>
          ) : (
            <a className="underline underline-offset-2" href={`/r/${r.watermark_id}`}>
              on Monad · open the record ↗
            </a>
          )}
        </Fact>
      </dl>
    </div>
  );
}

export function VerdictCard({ res }: { res: VerifyResult }) {
  const v = VERDICTS[res.verdict];
  return (
    <section className="rise overflow-hidden rounded-2xl border border-line bg-card">
      <div className={`flex items-start gap-4 p-6 ${v.bg}`}>
        <span className={`display text-5xl leading-none ${v.fg}`} aria-hidden>
          {v.mark}
        </span>
        <div>
          <h2 className={`display text-3xl leading-tight ${v.fg}`}>{v.title}</h2>
          <p className="mt-1 max-w-xl text-sm text-ink">{res.message}</p>
        </div>
      </div>
      <div className="grid gap-8 p-6 md:grid-cols-2">
        <div>
          <h3 className="mb-1 text-xs font-medium uppercase tracking-wider text-ink3">What we read from the image</h3>
          <dl>
            <Fact k="Hidden mark">
              {res.watermark_present ? (
                <span className="mono">{short(res.watermark_id, 10, 8)}</span>
              ) : (
                <span className="text-ink2">not found</span>
              )}
            </Fact>
            <Fact k="Look-alike distance">
              {res.distance === null ? (
                <span className="text-ink2">no registered image is close</span>
              ) : (
                <span>
                  <span className="mono">{res.distance}</span> <span className="text-ink2">of 256 bits differ</span>
                </span>
              )}
            </Fact>
            <Fact k="Fingerprint">
              <span className="mono text-xs">{res.algorithm}</span>
            </Fact>
          </dl>
        </div>
        {res.record ? (
          <RecordFacts r={res.record} />
        ) : (
          <div className="text-sm text-ink2">No registry entry is attached to this result.</div>
        )}
      </div>
      {res.earlier && (
        <div className="border-t border-line bg-badbg/40 p-6">
          <RecordFacts r={res.earlier} label="Registered earlier by someone else" />
        </div>
      )}
      {res.record && (
        <div className="border-t border-line px-6 py-4 text-sm">
          <a className="underline underline-offset-2" href={`/r/${res.record.watermark_id}`}>
            Open this record ↗
          </a>
        </div>
      )}
      <div className="border-t border-line bg-paper2 px-6 py-4 text-xs text-ink2">
        These thresholds are applied by the Imprint server. To check without trusting it, run the standalone{" "}
        <span className="mono">imprint-verify</span> tool, which reads your image and Monad directly (see the README).
      </div>
    </section>
  );
}
