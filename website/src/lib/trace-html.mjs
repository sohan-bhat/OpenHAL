import { escapeHtml, highlightHtml } from "./highlight.mjs";

export function inlineJson(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return value.length ? `[ ${value.map(inlineJson).join(", ")} ]` : "[]";
  const entries = Object.entries(value);
  if (!entries.length) return "{}";
  return `{ ${entries.map(([key, item]) => `${JSON.stringify(key)}: ${inlineJson(item)}`).join(", ")} }`;
}

export function payloadHtml(value) {
  return highlightHtml(inlineJson(value), "json");
}

export function arrowSvg(direction, dashed = false) {
  const line = direction === "out" ? `<line x1="1" y1="5" x2="11" y2="5"` : `<line x1="7" y1="5" x2="17" y2="5"`;
  const head = direction === "out" ? `<polygon points="18,5 11,1.5 11,8.5"/>` : `<polygon points="0,5 7,1.5 7,8.5"/>`;
  const dash = dashed ? ` stroke-dasharray="2.5 2"` : "";
  return `<svg class="trace-arrow" viewBox="0 0 18 10" width="18" height="10" aria-hidden="true" focusable="false" fill="currentColor">${line} stroke="currentColor" stroke-width="1.5"${dash}/>${head}</svg>`;
}

export function directionWord(entry) {
  if (entry.kind === "request") return "Request";
  if (entry.kind === "notification") return "Notification";
  return "Response";
}

function keepUnits(html) {
  return html.replace(/(\d) (?=(%|s|h|min|ms|V|A|W|degC|degF)\b|%)/g, "$1\u00a0");
}

export function reasonLines(reason) {
  const cut = reason.indexOf(" (");
  return cut > 0 && reason.endsWith(")") ? [reason.slice(0, cut), reason.slice(cut + 1)] : [reason];
}

function lineHtml(entry) {
  if (entry.kind === "error") {
    const reason = reasonLines(entry.reason)
      .map((part) => `<span class="reason">${keepUnits(escapeHtml(part))}</span>`)
      .join(" ");
    return `<span class="head error-head"><span class="outcome-error">error ${entry.code} ${escapeHtml(entry.name)}</span></span> ${reason}`;
  }
  const head = entry.kind === "result" ? `<span class="outcome-result">result</span>` : `<span class="method">${escapeHtml(entry.method)}</span>`;
  const payload =
    typeof entry.text === "string"
      ? `<span class="payload summary">${keepUnits(escapeHtml(entry.text))}</span>`
      : `<span class="payload">${payloadHtml(entry.kind === "result" ? entry.result : entry.params)}</span>`;
  return `<span class="head">${head} ${payload}</span>`;
}

export function traceItemsHtml(entries) {
  return entries
    .map((entry) => {
      if (entry.kind === "note") return noteHtml(entry.text);
      const arrow = arrowSvg(entry.kind === "request" ? "out" : "in", entry.kind === "notification");
      return `<li>${arrow} <span class="visually-hidden">${directionWord(entry)}</span> <div class="line">${lineHtml(entry)}</div></li>`;
    })
    .join("");
}

export function noteHtml(text) {
  return `<li class="note"><span class="note-mark" aria-hidden="true">#</span> <span class="note-text"><span class="visually-hidden">Comment </span>${escapeHtml(text)}</span></li>`;
}

export function traceHtml(entries, { label = "Message trace" } = {}) {
  return `<figure class="trace-figure"><div class="trace" role="region" aria-label="${escapeHtml(label)}" tabindex="0"><ol>${traceItemsHtml(entries)}</ol></div></figure>`;
}
