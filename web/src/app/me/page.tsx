"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Rec } from "@/lib/api";
import { ago, short } from "@/lib/format";
import { getStoredPasskey, type StoredPasskey } from "@/lib/passkey";
import { btnGhost, btnPrimary } from "@/components/ui";

export default function MyWorkPage() {
  const [pk, setPk] = useState<StoredPasskey | null>(null);
  const [signer, setSigner] = useState<string | null>(null);
  const [rows, setRows] = useState<Rec[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const p = getStoredPasskey();
    // Read browser-only state after mount so server and client markup match.
    /* eslint-disable react-hooks/set-state-in-effect */
    setPk(p);
    setChecked(true);
    /* eslint-enable react-hooks/set-state-in-effect */
    if (!p) return;
    let live = true;
    api
      .signer(p.qx, p.qy)
      .then(({ signer }) => {
        if (!live) return null;
        setSigner(signer);
        return api.records(50, signer);
      })
      .then((r) => {
        if (live && r) setRows(r.records);
      })
      .catch((e) => {
        if (live) setErr(e instanceof Error ? e.message : "Could not reach the registry.");
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <header>
        <h1 className="display text-5xl">My registrations</h1>
        <p className="mt-3 max-w-xl text-ink2">
          Every record on Monad signed by the passkey saved in this browser. This list comes from the public registry,
          so it is the same whether you are on this device or another.
        </p>
      </header>

      {checked && !pk && (
        <div className="rounded-2xl border border-line bg-card p-6">
          <p className="text-sm text-ink2">No passkey is saved in this browser yet.</p>
          <Link href="/register" className={`${btnPrimary} mt-4`}>
            Register an image
          </Link>
        </div>
      )}

      {signer && (
        <p className="text-xs text-ink2">
          Passkey signer <span className="mono text-ink">{signer}</span>
        </p>
      )}

      {err && <p className="rounded-xl bg-badbg p-4 text-sm text-bad">{err}</p>}

      {rows && (
        <div className="overflow-hidden rounded-2xl border border-line bg-card">
          {rows.length === 0 ? (
            <div className="p-6 text-sm text-ink2">
              Nothing registered with this passkey yet.{" "}
              <Link href="/register" className="underline underline-offset-2">
                Register an image
              </Link>
            </div>
          ) : (
            <ul>
              {rows.map((r) => (
                <li
                  key={r.watermark_id}
                  className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4 last:border-0"
                >
                  <div className="min-w-0">
                    <Link href={`/r/${r.watermark_id}`} className="mono text-sm underline-offset-2 hover:underline">
                      {short(r.watermark_id, 12, 10)}
                    </Link>
                    <p className="mt-0.5 text-xs text-ink2">block {r.block.toLocaleString()}</p>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-ink2">
                    <span>{ago(r.timestamp)}</span>
                    {r.tx_url ? (
                      <a className="underline underline-offset-2" href={r.tx_url} target="_blank" rel="noreferrer">
                        transaction ↗
                      </a>
                    ) : (
                      <Link href={`/r/${r.watermark_id}`} className="underline underline-offset-2">
                        record ↗
                      </Link>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {rows && rows.length > 0 && (
        <Link href="/receipt" className={btnGhost}>
          Have a receipt to check?
        </Link>
      )}
    </div>
  );
}
