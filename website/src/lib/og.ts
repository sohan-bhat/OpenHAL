import { wordmarkLightSvg } from "./brand-mark";
import { fontFaces, renderPng } from "./render-png";
import { scenarioTrace } from "./scenario";
import { arrowSvg, payloadHtml } from "./trace";

function escape(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export async function ogImage(title: string, kind: string): Promise<Uint8Array> {
  const entries = scenarioTrace();
  const refused = entries.findIndex((entry, index) => entry.kind === "request" && entries[index + 1]?.kind === "error");
  const at = refused >= 0 ? refused : entries.findIndex((entry) => entry.kind === "request");
  const request = entries[at];
  const answer = entries[at + 1];
  const size = title.length > 70 ? 54 : title.length > 40 ? 64 : 76;
  const method = request?.kind === "request" ? escape(request.method) : "";
  const params = request?.kind === "request" ? payloadHtml(request.params) : "";
  const outcome = answer?.kind === "error" ? `error ${answer.code} ${answer.name}` : answer?.kind === "result" ? "result" : "";
  const reason = answer?.kind === "error" ? escape(answer.reason) : answer?.kind === "result" ? payloadHtml(answer.result) : "";
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
${fontFaces()}
*{box-sizing:border-box;margin:0}
body{width:1200px;height:630px;background:#fcfcfd;color:#15181c;font-family:"Atkinson Hyperlegible Next";display:flex;flex-direction:column;padding:56px 64px}
.top{display:flex;align-items:center;gap:14px}
.kind{margin-left:auto;font-size:24px;font-weight:700;color:#4f5661;font-variant-caps:all-small-caps;letter-spacing:.04em}
h1{margin-top:44px;font-size:${size}px;line-height:1.12;font-weight:700;letter-spacing:-0.01em;max-width:1060px}
.trace{margin-top:auto;background:#f4f5f7;border:1px solid #dadde2;border-radius:10px;padding:26px 30px;font-family:"Atkinson Hyperlegible Mono";font-size:22px;line-height:1.6;display:grid;grid-template-columns:30px 1fr;column-gap:14px;row-gap:6px;align-items:baseline}
.trace svg{width:22px;height:12px;color:#15181c;align-self:center}
.method{color:#1d5fb4;font-weight:700;margin-right:22px}
.error{color:#a14034;font-weight:700}.result{color:#3c754f;font-weight:700}
.syn-key,.syn-punct{color:#4f5661}.syn-str{color:#15181c}.syn-num{color:#1d5fb4}
.reason{grid-column:2;color:#15181c;font-size:20px}
</style></head><body>
<div class="top">${wordmarkLightSvg(44)}<span class="kind">${escape(kind)}</span></div>
<h1>${escape(title)}</h1>
<div class="trace">
${arrowSvg("out")}<div><span class="method">${method}</span>${params}</div>
${arrowSvg("in")}<div class="${answer?.kind === "error" ? "error" : "result"}">${outcome}</div>
<div class="reason">${reason}</div>
</div>
</body></html>`;
  return renderPng(html, 1200, 630);
}
