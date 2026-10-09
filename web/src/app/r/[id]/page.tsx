"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ApiError, api, type Rec } from "@/lib/api";
import { RecordFacts, btnGhost, btnPrimary } from "@/components/ui";
import { loadKept } from "@/lib/store";
import { API } from "@/lib/api";

const REGISTRY = "0xf4a792ddb0c83Bdf1Ed2E1220B197760d821396c";
const RPC = "https://testnet-rpc.monad.xyz";

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
          <div className="mt-6 rounded-xl border border-line bg-paper2 p-4">
            <h3 className="text-xs font-medium uppercase tracking-wider text-ink3">Verify without Imprint</h3>
            <p className="mt-1 text-sm text-ink2">
              The record lives on Monad, not on our server. Read it yourself from the contract&rsquo;s{" "}
              <a
                className="underline underline-offset-2"
                href={`https://testnet.monadvision.com/address/${REGISTRY}?tab=Contract`}
                target="_blank"
                rel="noreferrer"
              >
                verified source on the explorer ↗
              </a>{" "}
              (call <span className="mono">recordOf</span> with the ID above), or from any terminal:
            </p>
            <pre className="mono mt-3 overflow-x-auto rounded-lg bg-paper p-3 text-xs text-ink">
{`cast call ${REGISTRY} "recordOf(bytes32)(address,uint64,uint64,bytes32)" ${id} --rpc-url ${RPC}`}
            </pre>
            <p className="mt-2 text-xs text-ink2">
              Returns signer, timestamp, block and fingerprint. The API&rsquo;s own answer for comparison:{" "}
              <a className="mono underline underline-offset-2" href={`${API}/record/${id}`} target="_blank" rel="noreferrer">
                /record/{id.slice(0, 10)}… ↗
              </a>
            </p>
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
