"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Rec } from "@/lib/api";
import { ago, short } from "@/lib/format";
import { btnGhost, btnPrimary } from "@/components/ui";

const STEPS = [
  {
    n: "1",
    title: "Register",
    body: "Approve with a passkey, a fingerprint or face unlock. No wallet, no seed phrase. Imprint hides a short ID in the image and records it on Monad.",
  },
  {
    n: "2",
    title: "Share anywhere",
    body: "Post it, message it, screenshot it. Compression and resizing destroy a file's hash, but not the hidden ID or how the picture looks.",
  },
  {
    n: "3",
    title: "Check a copy",
    body: "Drop any copy in. Imprint reads the ID, looks up the record, and tells you whether the copy matches, has been altered, or isn't registered.",
  },
];

export default function Home() {
  const [recent, setRecent] = useState<{ count: number; records: Rec[] } | null>(null);
  const [failed, setFailed] = useState(false);

  function load() {
    api
      .records(5)
      .then((r) => {
        setRecent(r);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-20">
      <section className="pt-8 sm:pt-14">
        <p className="mono text-xs uppercase tracking-widest text-ink3">Image registry on Monad</p>
        <h1 className="display mt-4 max-w-3xl text-5xl leading-[1.05] sm:text-7xl">
          Prove you registered it, even after it&rsquo;s been compressed.
        </h1>
        <p className="mt-6 max-w-xl text-lg text-ink2">
          Register an image with a passkey. Share it anywhere. Anyone can check a copy against a public record, and a
          changed copy is told apart from a merely re-encoded one.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link href="/register" className={btnPrimary}>
            Register an image
          </Link>
          <Link href="/verify" className={btnGhost}>
            Check an image
          </Link>
          <Link href="/stress" className={btnGhost}>
            See the stress test
          </Link>
        </div>
      </section>

      <section>
        <h2 className="display text-3xl">How it works</h2>
        <ol className="mt-6 grid gap-4 md:grid-cols-3">
          {STEPS.map((s) => (
            <li key={s.n} className="rounded-2xl border border-line bg-card p-6">
              <span className="mono text-xs text-ink3">0{s.n}</span>
              <h3 className="display mt-2 text-2xl">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink2">{s.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="grid gap-10 md:grid-cols-2">
        <div>
          <h2 className="display text-3xl">What it proves, and what it doesn&rsquo;t</h2>
          <ul className="mt-5 space-y-3 text-sm leading-relaxed text-ink2">
            <li>
              <span className="text-ink">Proves:</span> a particular passkey registered this image at a particular time,
              and whether a copy still looks like what was registered.
            </li>
            <li>
              <span className="text-ink">Doesn&rsquo;t prove:</span> that the signer made the image, that the image is
              real, or that it was never edited somewhere else. Registering someone else&rsquo;s image first is possible,
              so Imprint flags near-identical images already on record.
            </li>
            <li>
              <span className="text-ink">&ldquo;Not found&rdquo;</span> means no record, not that the image is fake.
            </li>
          </ul>
          <Link href="/evidence" className="mt-5 inline-block text-sm underline underline-offset-2">
            See the measured results and the failures ↗
          </Link>
        </div>

        <div>
          <h2 className="display text-3xl">On Monad right now</h2>
          <div className="mt-5 rounded-2xl border border-line bg-card">
            <div className="flex items-baseline justify-between border-b border-line px-5 py-4">
              <span className="text-sm text-ink2">Registrations</span>
              <span className="display text-3xl">{recent ? recent.count : failed ? "—" : "…"}</span>
            </div>
            <ul>
              {failed && (
                <li className="flex items-center justify-between gap-3 px-5 py-4 text-sm text-ink2">
                  <span>Couldn&rsquo;t reach the registry.</span>
                  <button className="underline underline-offset-2" onClick={load}>
                    Retry
                  </button>
                </li>
              )}
              {recent?.records.map((r) => (
                <li key={r.watermark_id} className="flex items-center justify-between gap-3 border-b border-line px-5 py-3 last:border-0">
                  <Link href={`/r/${r.watermark_id}`} className="mono text-sm underline-offset-2 hover:underline">
                    {short(r.watermark_id, 8, 6)}
                  </Link>
                  <span className="text-xs text-ink2">{ago(r.timestamp)}</span>
                </li>
              ))}
              {recent && recent.records.length === 0 && (
                <li className="px-5 py-4 text-sm text-ink2">No registrations yet. Be the first.</li>
              )}
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}
