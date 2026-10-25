// Dashboard captures supplied later as PNG and WebM files in website/public/captures/.
// A capture is used only when its file exists, with its real pixel size so nothing shifts.

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export interface Capture {
  src: string;
  width: number;
  height: number;
  video: string | null;
}

const PUBLIC = join(process.cwd(), "public");

function pngSize(path: string): { width: number; height: number } | null {
  const bytes = readFileSync(path);
  if (bytes.length < 24 || bytes.toString("ascii", 1, 4) !== "PNG") return null;
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

/** The capture at a site path such as /captures/hero.png, with a .webm beside it if there is one. */
export function capture(src: string | null | undefined): Capture | null {
  if (!src || !src.startsWith("/captures/") || !src.endsWith(".png")) return null;
  const file = join(PUBLIC, src);
  if (!existsSync(file)) return null;
  const size = pngSize(file);
  if (!size) return null;
  const webm = src.replace(/\.png$/, ".webm");
  return { src, ...size, video: existsSync(join(PUBLIC, webm)) ? webm : null };
}
