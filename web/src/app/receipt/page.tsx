"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { api, type ReceiptResult } from "@/lib/api";
import { RecordFacts, btnGhost, btnPrimary } from "@/components/ui";

export default function ReceiptPage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<ReceiptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const file = useRef<HTMLInputElement>(null);

  async function verify(raw: string) {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      const receipt = parsed && typeof parsed.receipt === "object" ? parsed.receipt : parsed;
      setResult(await api.receiptVerify(receipt));
    } catch (e) {
      setError(
        e instanceof SyntaxError
          ? "That is not valid JSON."
          : e instanceof Error
            ? e.message
            : "Could not check that receipt.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header>
        <h1 className="display text-5xl">Verify a receipt</h1>
        <p className="mt-3 max-w-xl text-ink2">
          A registration receipt is a small JSON file Imprint gives you when you register. Every field in it is checked
          against the live registry on Monad, so editing the file breaks the checks. The registry, not the file, stays
          the source of truth.
        </p>
      </header>

      <section className="rounded-2xl border border-line bg-card p-6">
        <div className="flex flex-wrap items-center gap-3">
          <input
            ref={file}
            type="file"
            accept="application/json,.json"
            className="sr-only"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) {
                const raw = await f.text();
                setText(raw);
                await verify(raw);
              }
            }}
          />
          <button className={btnPrimary} onClick={() => file.current?.click()}>
            Choose a receipt file
          </button>
          <span className="text-xs text-ink2">or paste it below</span>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder='{"imprint_receipt":1,...}'
          spellCheck={false}
          className="mono mt-4 h-40 w-full resize-y rounded-xl border border-line bg-paper2 p-3 text-xs text-ink outline-none focus:border-accent"
        />
        <button className={`${btnGhost} mt-3`} disabled={busy || !text.trim()} onClick={() => verify(text)}>
          {busy ? "Checking…" : "Check this receipt"}
        </button>
      </section>

      {error && <p className="rise rounded-xl bg-badbg p-4 text-sm text-bad">{error}</p>}

      {result && (
        <section className="rise space-y-4">
          <div
            className={`rounded-2xl border border-line p-6 ${result.valid ? "bg-okbg" : "bg-badbg"}`}
          >
            <h2 className={`display text-3xl ${result.valid ? "text-ok" : "text-bad"}`}>
              {result.valid ? "✓ Receipt verified" : "✗ Receipt did not verify"}
            </h2>
            <p className="mt-1 text-sm text-ink">
              {result.valid
                ? "Every field matches the registry on Monad."
                : "At least one check failed. The receipt has been edited, or it is not for this registry."}
            </p>
          </div>
          <ul className="overflow-hidden rounded-2xl border border-line bg-card">
            {result.checks.map((c) => (
              <li key={c.name} className="flex items-center gap-3 border-b border-line px-5 py-3 text-sm last:border-0">
                <span className={c.ok ? "text-ok" : "text-bad"} aria-hidden>
                  {c.ok ? "✓" : "✗"}
                </span>
                <span className="mono shrink-0 text-xs text-ink2">{c.name}</span>
                <span className="text-ink2">{c.detail}</span>
              </li>
            ))}
          </ul>
          {result.record && (
            <div className="rounded-2xl border border-line bg-card p-6">
              <RecordFacts r={result.record} />
              <Link
                href={`/r/${result.record.watermark_id}`}
                className={`${btnGhost} mt-4`}
              >
                Open the record
              </Link>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
