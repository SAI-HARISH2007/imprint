"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ApiError, api, type Rec } from "@/lib/api";
import { RecordFacts, btnGhost, btnPrimary } from "@/components/ui";
import { loadKept } from "@/lib/store";

export default function RecordPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [rec, setRec] = useState<Rec | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [kept, setKept] = useState<{ url: string; name: string } | null>(null);

  useEffect(() => {
    let live = true;
    let objectUrl: string | null = null;
    // reset only when the id changes; this runs on the client after mount
    /* eslint-disable react-hooks/set-state-in-effect */
    setRec(null);
    setErr(null);
    setKept(null);
    /* eslint-enable react-hooks/set-state-in-effect */
    api
      .record(id)
      .then((r) => live && setRec(r))
      .catch((e) => {
        if (!live) return;
        if (e instanceof ApiError && e.status === 404) setErr("No registration with this ID on this registry.");
        else if (e instanceof ApiError && e.status === 422) setErr("That does not look like a watermark ID.");
        else setErr(e instanceof Error ? e.message : "Could not load this record.");
      });
    loadKept(id).then((k) => {
      if (k && live) {
        objectUrl = URL.createObjectURL(k.blob);
        setKept({ url: objectUrl, name: k.name });
      }
    });
    return () => {
      live = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [id]);

  const notFound = err?.startsWith("No registration") || err?.startsWith("That does not look");

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <p className="mono text-xs uppercase tracking-widest text-ink3">Registration record</p>
        <h1 className="display mt-2 break-all text-3xl sm:text-4xl">{id}</h1>
      </header>
      {err && (
        <p className={`rounded-xl p-4 text-sm ${notFound ? "bg-nonebg" : "bg-badbg text-bad"}`}>{err}</p>
      )}
      {rec && (
        <section className="rise rounded-2xl border border-line bg-card p-6">
          <RecordFacts r={rec} />
          <div className="mt-6 border-t border-line pt-4">
            <h3 className="mb-1 text-xs font-medium uppercase tracking-wider text-ink3">Image fingerprint (256 bits)</h3>
            <p className="mono break-all text-xs text-ink2">{rec.fingerprint}</p>
          </div>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link href="/verify" className={btnPrimary}>
              Check an image against the registry
            </Link>
            {kept && (
              <a href={kept.url} download={kept.name} className={btnGhost}>
                Download your marked copy (saved in this browser)
              </a>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
