// Open Graph images, one per page, drawn from the design system at build time. Each shows the page
// title on the panel, the header plate with the mark, and the hero's real block on its limit line.

import { PRODUCT_NAME } from "../config/brand";
import { markSvg } from "./brand-mark";
import { heroFirstDecision } from "./hero";
import { fontFaces, renderPng } from "./render-png";

function escape(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export async function ogImage(title: string, kind: string): Promise<Uint8Array> {
  const decision = heroFirstDecision();
  const size = title.length > 60 ? 64 : title.length > 36 ? 76 : 92;
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
${fontFaces()}
*{box-sizing:border-box;margin:0}
body{width:1200px;height:630px;background:#e7e9e6;color:#15181b;font-family:"Atkinson Hyperlegible Next";display:flex;flex-direction:column}
.plate{height:96px;background:#2b3035;color:#e7e9e6;display:flex;align-items:center;gap:18px;padding:0 64px}
.word{font-family:"Sofia Sans Condensed";font-weight:800;font-size:40px;letter-spacing:.04em}
.kind{margin-left:auto;font-family:"Sofia Sans Condensed";font-weight:700;font-size:22px;letter-spacing:.08em;text-transform:uppercase;opacity:.85}
main{flex:1;padding:56px 64px 0;display:flex;flex-direction:column}
h1{font-family:"Sofia Sans Condensed";font-weight:750;font-size:${size}px;line-height:1.05;letter-spacing:-.01em;max-width:1000px}
.track{position:relative;height:96px;margin-top:auto;margin-bottom:28px}
.rail{position:absolute;left:0;right:0;top:58px;height:6px;background:#c1c3c2}
.fill{position:absolute;left:0;width:11%;top:58px;height:6px;background:#505254}
.thumb{position:absolute;left:11%;top:44px;width:16px;height:34px;margin-left:-8px;background:#15181b;border:3px solid #e7e9e6}
.line{position:absolute;left:66%;top:14px;bottom:10px;width:3px;background:#b3261e}
.flag{position:absolute;left:66%;top:0;background:#f2b705;color:#15181b;font-family:"Sofia Sans Condensed";font-weight:700;font-size:20px;letter-spacing:.08em;padding:2px 8px;text-transform:uppercase}
.attempt{position:absolute;left:94%;top:46px;width:30px;height:30px;margin-left:-15px;border:3px solid #b3261e;border-radius:50%}
.reason{font-family:"Martian Mono";font-size:20px;color:#b3261e;margin-bottom:40px}
</style></head><body>
<div class="plate">${markSvg({ size: 52 })}<span class="word">${PRODUCT_NAME}</span><span class="kind">${escape(kind)}</span></div>
<main><h1>${escape(title)}</h1>
<div class="track"><div class="rail"></div><div class="fill"></div><div class="line"></div><div class="flag">Max 100 %</div><div class="thumb"></div><div class="attempt"></div></div>
<p class="reason">${escape(decision.message)}</p></main>
</body></html>`;
  return renderPng(html, 1200, 630);
}
