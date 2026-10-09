import ev from "@/lib/evidence.json";
import heldout from "@/lib/heldout.json";
import batch from "@/lib/batch.json";
import markStats from "@/lib/mark_stats.json";
import { BatchSection, HeldoutSection, type Batch, type Heldout } from "./sections";

const pct = (x: number) => `${Math.round(x * 100)}%`;
const GROUP_TITLE: Record<string, string> = {
  sharing: "Ordinary sharing",
  edit: "Crops and edits",
};

export default function EvidencePage() {
  return (
    <div className="mx-auto max-w-4xl space-y-12">
      <header className="max-w-3xl">
        <h1 className="display text-5xl">Evidence</h1>
        <p className="mt-3 text-ink2">
          What we measured, how, and where it fails. Every number below comes from the scripts in the repository
          (<span className="mono">phase1/</span> and <span className="mono">service/</span>). We are showing the
          failures on purpose.
        </p>
      </header>

      <section className="rounded-2xl border border-line bg-card p-6">
        <h2 className="display text-3xl">Read this first</h2>
        <ul className="mt-4 space-y-2 text-sm leading-relaxed text-ink2">
          <li>
            The test set is {ev.n_images} photos from one source, resized and recompressed in code. It is not real
            WhatsApp or Telegram traffic and it has no AI-generated images yet.
          </li>
          <li>
            The thresholds were chosen after looking at this set (the calibration set). They were then applied unchanged
            to 40 fresh photos the thresholds had never seen; that held-out result is further down, and it is the one to
            trust.
          </li>
          <li>
            24 images per row supports a per-row rate of roughly 88% or better at 95% confidence even when every image
            passes, not 100%.
          </li>
        </ul>
      </section>

      <section className="rounded-2xl border border-line bg-card p-6">
        <h2 className="display text-3xl">What the mark looks like</h2>
        <p className="mt-2 max-w-3xl text-sm text-ink2">
          The registered demo image, its original, and the exact difference between them amplified {markStats.gain}×
          (grey is no change). The mark changes each colour channel by {markStats.rms} of 255 on average, at most{" "}
          {markStats.max}; PSNR {markStats.psnr_db} dB. The Register page shows the same picture for your own image.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {[
            ["/demo/demo-1-original.jpg", "Original"],
            ["/demo/demo-1-marked.png", "Marked (registered)"],
            ["/demo/demo-1-mark-x30.png", `Difference × ${markStats.gain}`],
          ].map(([src, label]) => (
            <figure key={src}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={src} alt={label} className="w-full rounded-lg border border-line" />
              <figcaption className="mt-1 text-xs text-ink2">{label}</figcaption>
            </figure>
          ))}
        </div>
      </section>

      {(["sharing", "edit"] as const).map((g) => (
        <section key={g}>
          <h2 className="display text-3xl">{GROUP_TITLE[g]}</h2>
          <div className="mt-4 overflow-x-auto rounded-2xl border border-line bg-card">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-ink3">
                <tr className="border-b border-line">
                  <th className="px-4 py-3 font-medium">Transform</th>
                  <th className="px-4 py-3 font-medium">Hidden mark read</th>
                  <th className="px-4 py-3 font-medium">Median look-alike distance</th>
                  <th className="px-4 py-3 font-medium">Largest</th>
                </tr>
              </thead>
              <tbody>
                {ev.rows
                  .filter((r) => r.group === g)
                  .map((r) => (
                    <tr key={r.key} className="border-b border-line last:border-0">
                      <td className="px-4 py-3">{r.label}</td>
                      <td className={`px-4 py-3 ${r.decode < 0.9 ? "text-warn" : ""}`}>{pct(r.decode)}</td>
                      <td className="mono px-4 py-3">{r.medianDist}</td>
                      <td className="mono px-4 py-3">{r.maxDist}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <section className="grid gap-8 md:grid-cols-2">
        <div>
          <h2 className="display text-3xl">Other transforms</h2>
          <div className="mt-4 rounded-2xl border border-line bg-card">
            {ev.hard.map((h) => (
              <div key={h.label} className="flex justify-between border-b border-line px-5 py-3 text-sm last:border-0">
                <span>{h.label}</span>
                <span className={h.decode < 0.9 ? "text-warn" : ""}>{pct(h.decode)}</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-ink2">Rotation breaks the mark. We list it as a failure.</p>
        </div>

        <div>
          <h2 className="display text-3xl">Combined damage</h2>
          <div className="mt-4 rounded-2xl border border-line bg-card">
            {Object.entries(ev.combos24).map(([k, v]) => (
              <div key={k} className="flex justify-between border-b border-line px-5 py-3 text-sm last:border-0">
                <span className="mono text-xs">{k.replace(/_/g, " ")}</span>
                <span className={String(v).split("/")[0] !== String(v).split("/")[1] ? "text-warn" : ""}>{String(v)} images</span>
              </div>
            ))}
            {Object.entries(ev.combos12.small_1024).map(([k, v]) => (
              <div key={"s" + k} className="flex justify-between border-b border-line px-5 py-3 text-sm last:border-0">
                <span className="mono text-xs">{k.replace(/_/g, " ")} (1024px)</span>
                <span className={String(v).split("/")[0] !== String(v).split("/")[1] ? "text-warn" : ""}>{String(v)} images</span>
              </div>
            ))}
            {Object.entries(ev.combos12.large_3000).map(([k, v]) => (
              <div key={"l" + k} className="flex justify-between border-b border-line px-5 py-3 text-sm last:border-0">
                <span className="mono text-xs">{k.replace(/_/g, " ")} (3000px)</span>
                <span className={String(v).split("/")[0] !== String(v).split("/")[1] ? "text-warn" : ""}>{String(v)} images</span>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-ink2">
            Harsh combinations fail on a minority of images, and small images fail more than large ones. When the mark
            is lost, the fingerprint can still give a &ldquo;likely match&rdquo;.
          </p>
        </div>
      </section>

      <section className="rounded-2xl border border-line bg-card p-6">
        <h2 className="display text-3xl">Separating the cases</h2>
        <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-ink2">Unrelated images differ by (of 256 bits)</dt>
            <dd className="mono mt-1">
              min {ev.unrelated.min}, median {ev.unrelated.median}
            </dd>
          </div>
          <div>
            <dt className="text-ink2">Unmarked originals that read as marked</dt>
            <dd className="mono mt-1">{ev.falseRead} of the originals</dd>
          </div>
          <div>
            <dt className="text-ink2">Content pasted over 10% differs by</dt>
            <dd className="mono mt-1">
              min {ev.edit10.min}, median {ev.edit10.median}
            </dd>
          </div>
          <div>
            <dt className="text-ink2">Content pasted over 25% differs by</dt>
            <dd className="mono mt-1">
              min {ev.edit25.min}, median {ev.edit25.median}
            </dd>
          </div>
        </dl>
        <p className="mt-4 text-xs text-ink2">
          Ordinary sharing stays within about 12 bits. Edits start near 30. The match threshold sits between them.
        </p>
      </section>

      <section className="rounded-2xl border border-line bg-card p-6">
        <h2 className="display text-3xl">Attacks we tried</h2>
        <ul className="mt-4 space-y-3 text-sm leading-relaxed text-ink2">
          <li>
            <span className="text-ink">Registering someone else&rsquo;s image first.</span> Re-marking an already
            registered image replaced its hidden ID in {ev.doubleMark.second_payload_wins} of {ev.n_images} images, so
            the mark alone cannot stop this. The look-alike fingerprint can: the re-marked copy stayed within{" "}
            {ev.remarkedDist.max} bits of the original. Imprint refuses to register such an image, and the checker marks
            a later look-alike as disputed.
          </li>
          <li>
            <span className="text-ink">Copying the mark onto another picture.</span> We estimated the mark from one
            image and added it to another, 10 attempts. The ID did not decode in any of them. This is one simple attack,
            not a proof.
          </li>
          <li>
            <span className="text-ink">Removing the mark.</span> The library that creates the mark also ships a remover
            and its decoder is open source, so a determined person can strip it. The fingerprint then gives a
            &ldquo;likely match&rdquo; at best.
          </li>
        </ul>
      </section>

      <HeldoutSection data={heldout as Heldout} />

      <BatchSection data={batch as Batch} />

      <section className="rounded-2xl border border-line bg-card p-6">
        <h2 className="display text-3xl">Still to do</h2>
        <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-ink2">
          <li>Real WhatsApp and Telegram transfers, and real phone screenshots.</li>
          <li>AI-generated images in the held-out set.</li>
          <li>A larger held-out set; 40 images is modest.</li>
        </ul>
      </section>
    </div>
  );
}
