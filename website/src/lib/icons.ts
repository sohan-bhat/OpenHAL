// The favicon set, every size drawn from the same mark as the header (src/lib/brand-mark.ts).

import { markSvg } from "./brand-mark";
import { renderPng } from "./render-png";

export const ICON_SIZES: Record<string, number> = {
  "favicon-32": 32,
  "apple-touch-icon": 180,
  "icon-192": 192,
  "icon-512": 512,
};

export async function iconPng(size: number): Promise<Uint8Array> {
  const html = `<!doctype html><html><head><style>*{margin:0}body{width:${size}px;height:${size}px}svg{display:block}</style></head><body>${markSvg({ size })}</body></html>`;
  return renderPng(html, size, size, true);
}
