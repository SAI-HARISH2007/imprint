/** Example images, registered on Monad testnet beforehand, so a visitor can try Check without registering. */
export const DEMO_CHECKS = [
  { file: "/demo/demo-1-marked.png", label: "The registered original", name: "registered-original.png" },
  { file: "/demo/demo-1-shared.jpg", label: "A shared copy (halved, compressed)", name: "shared-copy.jpg" },
  { file: "/demo/demo-1-edited.png", label: "An edited copy", name: "edited-copy.png" },
  { file: "/demo/demo-2-unregistered.jpg", label: "An image never registered", name: "unregistered.jpg" },
];

export const DEMO_STRESS = { file: "/demo/demo-1-marked.png", name: "demo-registered.png" };

export async function fetchDemo(file: string, name: string): Promise<File> {
  const res = await fetch(file);
  if (!res.ok) throw new Error(`Could not load the example image (${res.status}).`);
  const blob = await res.blob();
  return new File([blob], name, { type: blob.type || "image/png" });
}
