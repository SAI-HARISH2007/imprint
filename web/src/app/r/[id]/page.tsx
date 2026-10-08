"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { api, type Rec } from "@/lib/api";
import { RecordFacts, btnPrimary } from "@/components/ui";

export default function RecordPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [rec, setRec] = useState<Rec | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.record(id).then(setRec).catch((e) => setErr(e instanceof Error ? e.message : "Not found"));
  }, [id]);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <p className="mono text-xs uppercase tracking-widest text-ink3">Registration record</p>
        <h1 className="display mt-2 break-all text-3xl sm:text-4xl">{id}</h1>
      </header>
      {err && <p className="rounded-xl bg-nonebg p-4 text-sm">No registration with this ID on this registry.</p>}
      {rec && (
        <section className="rise rounded-2xl border border-line bg-card p-6">
          <RecordFacts r={rec} />
          <div className="mt-6 border-t border-line pt-4">
            <h3 className="mb-1 text-xs font-medium uppercase tracking-wider text-ink3">Image fingerprint (256 bits)</h3>
            <p className="mono break-all text-xs text-ink2">{rec.fingerprint}</p>
          </div>
          <div className="mt-6">
            <Link href="/verify" className={btnPrimary}>
              Check an image against the registry
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}
