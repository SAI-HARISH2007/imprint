import type { VerdictKey } from "./api";

export const short = (s: string | null | undefined, head = 8, tail = 6) =>
  !s ? "" : s.length <= head + tail + 3 ? s : `${s.slice(0, head)}…${s.slice(-tail)}`;

export function when(iso: string | number): string {
  const d = typeof iso === "number" ? new Date(iso * 1000) : new Date(iso);
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "medium" });
}

export function ago(unix: number): string {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - unix));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export const VERDICTS: Record<
  VerdictKey,
  { title: string; short: string; text: string; bg: string; fg: string; mark: string }
> = {
  verified: {
    title: "Verified match",
    short: "Verified",
    text: "Registered, and this copy is consistent with the registered image.",
    bg: "bg-okbg",
    fg: "text-ok",
    mark: "✓",
  },
  altered: {
    title: "Altered from the registered image",
    short: "Altered",
    text: "This descends from a registered image, but its content has changed (edited or cropped).",
    bg: "bg-warnbg",
    fg: "text-warn",
    mark: "≠",
  },
  likely_match: {
    title: "Likely match",
    short: "Likely match",
    text: "The hidden mark was lost, but this looks like a registered image. Lower confidence.",
    bg: "bg-infobg",
    fg: "text-info",
    mark: "≈",
  },
  disputed: {
    title: "Disputed",
    short: "Disputed",
    text: "Registered, but a near-identical image was registered earlier by a different signer.",
    bg: "bg-badbg",
    fg: "text-bad",
    mark: "!",
  },
  not_found: {
    title: "Not found",
    short: "Not found",
    text: "No registration found. That does not mean the image is fake.",
    bg: "bg-nonebg",
    fg: "text-none",
    mark: "–",
  },
};
