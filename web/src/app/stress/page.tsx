"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, b64ToBlob, type StressRow } from "@/lib/api";
import { DEMO_STRESS, fetchDemo } from "@/lib/demo";
import { loadMarked } from "@/lib/session";
import { Chip, Dropzone, Spinner, btnAccent, btnGhost } from "@/components/ui";

const GROUPS: { key: StressRow["group"]; title: string; blurb: string }[] = [
  {
    key: "sharing",
    title: "Ordinary sharing",
    blurb: "What platforms do to every image. These should all verify.",
  },
  {
    key: "edit",
    title: "Edits",
    blurb: "The content changes. These should be flagged, or lose the match.",
  },
  {
    key: "attack",
    title: "Attempts to cheat",
    blurb: "Removing the mark, copying it onto another picture, or presenting a different image.",
  },
];

export default function StressPage() {
  const [source, setSource] = useState<{ file: File; url: string } | null>(null);
  const [rows, setRows] = useState<StressRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasLast, setHasLast] = useState(false);

  useEffect(() => setHasLast(!!loadMarked()), []);

  async function run(file: File) {
    setSource({ file, url: URL.createObjectURL(file) });
    setBusy(true);
    setError(null);
    setRows(null);
    try {
      // a real, unrelated photo for the "different image" and "copied mark" rows
      const donor = await fetch("/demo/demo-2-unregistered.jpg").then((r) => (r.ok ? r.blob() : undefined)).catch(() => undefined);
      setRows((await api.stress(file, file.name, donor)).results);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function useLast() {
    const m = loadMarked();
    if (m) await run(new File([b64ToBlob(m.b64)], m.name, { type: "image/png" }));
  }

  const count = (g: StressRow["group"], v: StressRow["verdict"]) =>
    rows?.filter((r) => r.group === g && r.verdict === v).length ?? 0;
  const total = (g: StressRow["group"]) => rows?.filter((r) => r.group === g).length ?? 0;

  return (
    <div className="space-y-8">
      <header className="max-w-3xl">
        <h1 className="display text-5xl">Stress test</h1>
        <p className="mt-3 text-ink2">
          Take a registered image, damage it in fifteen ways, and check each result against the registry on Monad. Each
          row is a real run. The file hash column shows why a plain file hash can&rsquo;t do this job.
        </p>
      </header>

      {!rows && !busy && (
        <div className="max-w-3xl">
          <Dropzone onFile={run} hint="Drop an image you registered with Imprint">
            <div className="flex flex-wrap justify-center gap-2">
              {hasLast && (
                <button type="button" className={`${btnAccent} !px-4 !py-2 !text-xs`} onClick={useLast}>
                  Use the image I just registered
                </button>
              )}
              <button
                type="button"
                className={`${btnGhost} !px-4 !py-2 !text-xs`}
                onClick={async () => run(await fetchDemo(DEMO_STRESS.file, DEMO_STRESS.name))}
              >
                Use the demo image
              </button>
              <Link href="/register" className={`${btnGhost} !px-4 !py-2 !text-xs`}>
                Register one first
              </Link>
            </div>
          </Dropzone>
        </div>
      )}

      {busy && (
        <div className="rise flex max-w-3xl items-center gap-4 rounded-2xl border border-line bg-card p-5">
          {source && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={source.url} alt="" className="h-16 w-auto rounded" />
          )}
          <Spinner label="Damaging the image fifteen ways and checking each one on Monad. About 20 seconds." />
        </div>
      )}

      {error && <p className="rise max-w-3xl rounded-xl bg-badbg p-4 text-sm text-bad">{error}</p>}

      {rows && source && (
        <div className="rise space-y-10">
          <div className="flex flex-wrap items-center gap-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={source.url} alt="" className="h-20 w-auto rounded-lg border border-line" />
            <div className="flex flex-wrap gap-6 text-sm">
              <span>
                <span className="display text-3xl text-ok">
                  {count("sharing", "verified")}/{total("sharing")}
                </span>{" "}
                <span className="text-ink2">sharing copies verified</span>
              </span>
              <span>
                <span className="display text-3xl text-warn">
                  {count("edit", "altered") + count("edit", "likely_match")}/{total("edit")}
                </span>{" "}
                <span className="text-ink2">edits flagged</span>
              </span>
              <span>
                <span className="display text-3xl">
                  {rows.filter((r) => r.file_hash_matches).length}/{rows.length}
                </span>{" "}
                <span className="text-ink2">would match by file hash</span>
              </span>
            </div>
            <button className={`${btnGhost} ml-auto`} onClick={() => setRows(null)}>
              Test another image
            </button>
          </div>

          {GROUPS.map((g) => (
            <section key={g.key}>
              <h2 className="display text-3xl">{g.title}</h2>
              <p className="mt-1 text-sm text-ink2">{g.blurb}</p>
              <div className="mt-4 overflow-x-auto rounded-2xl border border-line bg-card">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wider text-ink3">
                    <tr className="border-b border-line">
                      <th className="px-4 py-3 font-medium">Damaged copy</th>
                      <th className="px-4 py-3 font-medium">Result</th>
                      <th className="px-4 py-3 font-medium">Differs by</th>
                      <th className="px-4 py-3 font-medium">Hidden mark</th>
                      <th className="px-4 py-3 font-medium">Same file hash</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows
                      .filter((r) => r.group === g.key)
                      .map((r) => (
                        <tr key={r.key} className="border-b border-line last:border-0">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-3">
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img src={r.thumb} alt="" className="h-10 w-14 rounded object-cover" />
                              {r.label}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <Chip verdict={r.verdict} />
                          </td>
                          <td className="mono px-4 py-3">
                            {r.distance === null ? <span className="text-ink3">–</span> : `${r.distance} / 256`}
                          </td>
                          <td className="px-4 py-3">{r.watermark_present ? "found" : <span className="text-ink3">lost</span>}</td>
                          <td className="px-4 py-3 text-ink3">{r.file_hash_matches ? "yes" : "no"}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}

          <p className="max-w-3xl text-xs leading-relaxed text-ink2">
            This is one image and one run. The measured results across many images, including the cases where the mark
            did not survive, are on the{" "}
            <Link href="/evidence" className="underline underline-offset-2">
              Evidence page
            </Link>
            . A copied or removed mark is not a security guarantee: the decoder is open source, and removing the mark
            lands on &ldquo;likely match&rdquo; at best.
          </p>
        </div>
      )}
    </div>
  );
}
