/* Sections of the Evidence page that read the held-out and batch results. Pure rendering. */

type PerTransform = Record<
  string,
  { decode_rate: number; verdicts: Record<string, number>; median_dist: number; max_dist: number }
>;

export type HeldoutSet = {
  n_images: number;
  per_transform: PerTransform;
  normal_sharing_mean_decode: number;
  sharing_wrongly_altered: number;
  sharing_checks: number;
  edits_wrongly_verified: number;
  edit_checks: number;
  unrelated_pairs: number;
  unrelated_min_dist: number;
  false_likely_match_pairs: number;
  false_duplicate_pairs: number;
};

export type Heldout = {
  thresholds: { match: number; near: number; duplicate: number };
  sets: Record<string, HeldoutSet>;
};

export type Batch = {
  contract: string;
  chain_id: number;
  part_a: {
    n: number;
    total_s: number;
    spent_mon: number;
    register_s_median: number;
    register_s_p90: number;
    chain_s_median: number;
    mark_s_median: number;
    gas_median: number;
    gwei_median: number;
    cost_mon_median: number;
  };
  part_b: {
    m: number;
    landed: number;
    sent_s: number;
    confirmed_s: number;
    blocks: number;
    first_block: number;
    last_block: number;
    spent_mon: number;
  };
};

const pct = (x: number) => `${Math.round(x * 100)}%`;

const LABEL: Record<string, string> = {
  identity: "No change",
  png_to_jpeg_q95: "PNG to JPEG q95",
  jpeg_q90: "JPEG q90",
  jpeg_q70: "JPEG q70",
  jpeg_q50: "JPEG q50",
  jpeg_q30: "JPEG q30",
  jpeg_q20: "JPEG q20",
  resize_75: "Resize to 75%",
  resize_50: "Resize to 50%",
  resize_25: "Resize to 25%",
  messenger: "Messenger-style (cap 1600px, q70)",
  screenshot_like: "Screenshot-like rescale",
  crop_5: "Crop 5%",
  crop_15: "Crop 15%",
  crop_30: "Crop 30%",
  brightness_p15: "Brightness +15%",
  brightness_m15: "Brightness -15%",
  contrast_p15: "Contrast +15%",
  blur_light: "Light blur",
  edit_paste_10pct: "Foreign content pasted over 10%",
  edit_paste_25pct: "Foreign content pasted over 25%",
};

const VERDICT_SHORT: Record<string, string> = {
  verified: "verified",
  altered: "altered",
  likely_match: "likely",
  not_found: "not found",
  disputed: "disputed",
};

function verdictCell(v: Record<string, number>, n: number) {
  const parts = Object.entries(v)
    .sort((a, b) => b[1] - a[1])
    .map(([k, c]) => `${VERDICT_SHORT[k] ?? k} ${c}/${n}`);
  return parts.join(", ");
}

export function HeldoutSection({ data }: { data: Heldout }) {
  const sets = Object.entries(data.sets);
  return (
    <section className="space-y-6">
      <div className="max-w-3xl">
        <h2 className="display text-3xl">Held-out evaluation</h2>
        <p className="mt-2 text-sm text-ink2">
          The thresholds (match {data.thresholds.match}, likely {data.thresholds.near}, duplicate{" "}
          {data.thresholds.duplicate} bits) were fixed on the calibration set above, then applied unchanged to images
          they had never seen: fresh photos at mixed sizes and orientations{sets.some(([k]) => k === "ai") ? ", plus AI-generated images" : ""}.
          Each row shows the verdict the product would actually give. One of the 40 photos later turned out to be the
          same stock photo as a calibration image (the source maps seeds to a finite pool), so 39 were truly unseen.
        </p>
      </div>
      {sets.map(([name, s]) => (
        <div key={name}>
          <h3 className="text-xs font-medium uppercase tracking-wider text-ink3">
            {name === "ai" ? "AI-generated images" : "Photos"} · {s.n_images} images
          </h3>
          <div className="mt-3 grid gap-3 text-sm sm:grid-cols-4">
            <div className="rounded-xl border border-line bg-card p-4">
              <div className="text-xs text-ink2">Ordinary sharing, mark read</div>
              <div className="display mt-1 text-3xl">{pct(s.normal_sharing_mean_decode)}</div>
            </div>
            <div className="rounded-xl border border-line bg-card p-4">
              <div className="text-xs text-ink2">Sharing copies wrongly called altered</div>
              <div className={`display mt-1 text-3xl ${s.sharing_wrongly_altered ? "text-warn" : ""}`}>
                {s.sharing_wrongly_altered}/{s.sharing_checks}
              </div>
            </div>
            <div className="rounded-xl border border-line bg-card p-4">
              <div className="text-xs text-ink2">Edits wrongly called verified</div>
              <div className={`display mt-1 text-3xl ${s.edits_wrongly_verified ? "text-warn" : ""}`}>
                {s.edits_wrongly_verified}/{s.edit_checks}
              </div>
            </div>
            <div className="rounded-xl border border-line bg-card p-4">
              <div className="text-xs text-ink2">Unrelated pairs called likely match</div>
              <div className={`display mt-1 text-3xl ${s.false_likely_match_pairs ? "text-warn" : ""}`}>
                {s.false_likely_match_pairs}/{s.unrelated_pairs}
              </div>
            </div>
          </div>
          <div className="mt-3 overflow-x-auto rounded-2xl border border-line bg-card">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wider text-ink3">
                <tr className="border-b border-line">
                  <th className="px-4 py-3 font-medium">Transform</th>
                  <th className="px-4 py-3 font-medium">Mark read</th>
                  <th className="px-4 py-3 font-medium">Verdicts</th>
                  <th className="px-4 py-3 font-medium">Median / max distance</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(s.per_transform).map(([k, v]) => (
                  <tr key={k} className="border-b border-line last:border-0">
                    <td className="px-4 py-3">{LABEL[k] ?? k}</td>
                    <td className={`px-4 py-3 ${v.decode_rate < 0.9 ? "text-warn" : ""}`}>{pct(v.decode_rate)}</td>
                    <td className="px-4 py-3 text-ink2">{verdictCell(v.verdicts, s.n_images)}</td>
                    <td className="mono px-4 py-3">
                      {v.median_dist} / {v.max_dist}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}

export function BatchSection({ data }: { data: Batch }) {
  const a = data.part_a;
  const b = data.part_b;
  return (
    <section>
      <div className="max-w-3xl">
        <h2 className="display text-3xl">Cost and speed on Monad</h2>
        <p className="mt-2 text-sm text-ink2">
          Measured on Monad testnet (chain {data.chain_id}) against the deployed registry, not estimated. Part A goes
          through the full product path: mark the image, sign with a passkey, relay, wait for the receipt. Part B
          sends a burst at once from one key to see how fast many registrations land.
        </p>
      </div>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <div className="rounded-xl border border-line bg-card p-4">
          <div className="text-xs text-ink2">Cost per registration (median of {a.n})</div>
          <div className="display mt-1 text-3xl">{a.cost_mon_median.toFixed(4)} MON</div>
          <div className="mt-1 text-xs text-ink2">
            {Math.round(a.gas_median).toLocaleString()} gas at {Math.round(a.gwei_median)} gwei
          </div>
        </div>
        <div className="rounded-xl border border-line bg-card p-4">
          <div className="text-xs text-ink2">Send to receipt (median, p90)</div>
          <div className="display mt-1 text-3xl">{a.chain_s_median.toFixed(1)} s</div>
          <div className="mt-1 text-xs text-ink2">
            whole register call {a.register_s_median.toFixed(1)} s median, {a.register_s_p90.toFixed(1)} s p90
          </div>
        </div>
        <div className="rounded-xl border border-line bg-card p-4">
          <div className="text-xs text-ink2">Burst of {b.m} registrations</div>
          <div className="display mt-1 text-3xl">{b.confirmed_s.toFixed(1)} s</div>
          <div className="mt-1 text-xs text-ink2">
            {b.landed}/{b.m} landed across {b.blocks} blocks ({b.first_block.toLocaleString()} to{" "}
            {b.last_block.toLocaleString()})
          </div>
        </div>
      </div>
      <p className="mt-3 max-w-3xl text-xs text-ink2">
        The register call above includes several RPC round-trips of our own; after trimming them, two later
        registrations took 2.9 s and 2.5 s end to end (chain 1.4 s and 1.2 s). Monad charges for the gas limit, not gas
        used, so the relayer estimates tightly. Hiding the mark in the image
        took {a.mark_s_median.toFixed(1)} s median on a CPU; that is our server, not the chain. Part A spent{" "}
        {a.spent_mon.toFixed(3)} MON for {a.n} registrations and part B {b.spent_mon.toFixed(3)} MON for {b.m}.
      </p>
    </section>
  );
}
