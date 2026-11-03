import { readFileSync } from "node:fs";
import { join } from "node:path";
import { PITCH } from "../config/brand";
import { wordmarkLightSvg } from "./brand-mark";
import { palette } from "./palette.mjs";
import { fontFaces, renderPng } from "./render-png";
import { REPO_ROOT } from "./spec-meta.mjs";

/** GitHub's recommended size for a repository's social preview. */
export const SOCIAL_PREVIEW_SIZE = { width: 1280, height: 640 } as const;

/** Where the preview is saved for the repository settings, next to the wordmark files. */
export const SOCIAL_PREVIEW_FILE = join(REPO_ROOT, "docs", "assets", "social-preview.png");

/** The README's flow diagram in the light theme, with the reduced motion lines GitHub shows for a still frame. */
function flowDiagram(width: number): string {
  const svg = readFileSync(join(REPO_ROOT, "docs", "diagrams", "flow-light.svg"), "utf8").trim();
  const box = /viewBox="([\d.\s-]+)"/.exec(svg)?.[1].trim().split(/\s+/).map(Number) ?? [0, 0, 952, 283];
  const height = Math.round((width * box[3]) / box[2]);
  return svg.replace(/\swidth="[\d.]+"/, ` width="${width}"`).replace(/\sheight="[\d.]+"/, ` height="${height}"`);
}

/**
 * The repository's social preview in the site's light theme. The wordmark and the one-line
 * description sit over the flow diagram, the same files the README and the site use, with no
 * gradients and no glow.
 */
export async function socialPreviewImage(): Promise<Uint8Array> {
  const p = palette.light;
  const { width, height } = SOCIAL_PREVIEW_SIZE;
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
${fontFaces()}
*{box-sizing:border-box;margin:0}
body{width:${width}px;height:${height}px;background:${p.bg};color:${p.text};font-family:"IBM Plex Sans";display:flex;flex-direction:column;padding:64px 80px 40px}
h1{margin-top:32px;font-size:50px;line-height:1.14;font-weight:600;letter-spacing:-0.012em;max-width:920px}
.flow{margin:auto 0 0 -12px;display:flex}
</style></head><body>
<div>${wordmarkLightSvg(60)}</div>
<h1>${PITCH}</h1>
<div class="flow">${flowDiagram(1040)}</div>
</body></html>`;
  return renderPng(html, width, height, false, true);
}
