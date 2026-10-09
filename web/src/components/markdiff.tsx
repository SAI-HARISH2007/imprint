"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Shows the hidden mark by subtracting the original from the marked image, pixel by pixel,
 * and amplifying the difference. Exact, because both files are in the browser at this point.
 */
export function MarkDiff({ original, markedB64, gain = 30 }: { original: File; markedB64: string; gain?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [stats, setStats] = useState<{ rms: number; psnr: number } | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    const load = (src: string) =>
      new Promise<HTMLImageElement>((res, rej) => {
        const i = new Image();
        i.onload = () => res(i);
        i.onerror = () => rej(new Error("decode"));
        i.src = src;
      });
    const origUrl = URL.createObjectURL(original);
    Promise.all([load(origUrl), load(`data:image/png;base64,${markedB64}`)])
      .then(([a, b]) => {
        if (!live || !canvas.current) return;
        const scale = Math.min(1, 900 / Math.max(b.naturalWidth, b.naturalHeight));
        const w = Math.max(1, Math.round(b.naturalWidth * scale));
        const h = Math.max(1, Math.round(b.naturalHeight * scale));
        const read = (img: HTMLImageElement) => {
          const c = document.createElement("canvas");
          c.width = w;
          c.height = h;
          const ctx = c.getContext("2d", { willReadFrequently: true })!;
          ctx.drawImage(img, 0, 0, w, h);
          return ctx.getImageData(0, 0, w, h).data;
        };
        const pa = read(a);
        const pb = read(b);
        const out = canvas.current.getContext("2d")!;
        canvas.current.width = w;
        canvas.current.height = h;
        const img = out.createImageData(w, h);
        let sq = 0;
        let n = 0;
        for (let i = 0; i < pa.length; i += 4) {
          for (let k = 0; k < 3; k++) {
            const d = pb[i + k] - pa[i + k];
            sq += d * d;
            n++;
            img.data[i + k] = Math.max(0, Math.min(255, 128 + d * gain));
          }
          img.data[i + 3] = 255;
        }
        out.putImageData(img, 0, 0);
        const rms = Math.sqrt(sq / n);
        setStats({ rms, psnr: rms > 0 ? 20 * Math.log10(255 / rms) : 99 });
      })
      .catch(() => live && setFailed(true))
      .finally(() => URL.revokeObjectURL(origUrl));
    return () => {
      live = false;
    };
  }, [original, markedB64, gain]);

  if (failed) return null;
  return (
    <div className="rounded-2xl border border-line bg-card p-5">
      <h3 className="text-xs font-medium uppercase tracking-wider text-ink3">The hidden mark, amplified {gain}×</h3>
      <p className="mt-1 text-sm text-ink2">
        Your marked image minus your original, pixel by pixel. Grey means no change. This is the pattern that
        carries the ID through compression and resizing.
      </p>
      <canvas ref={canvas} className="mt-4 max-h-80 w-auto rounded-lg" />
      {stats && (
        <p className="mt-3 text-xs text-ink2">
          Average change {stats.rms.toFixed(2)} of 255 per channel (PSNR {stats.psnr.toFixed(1)} dB). Below what the
          eye picks up at normal viewing size; the downscaled original and marked copy above look identical.
        </p>
      )}
    </div>
  );
}
