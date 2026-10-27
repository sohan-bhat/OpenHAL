import { escapeHtml } from "../highlight.mjs";
import { arrowSvg } from "../trace-html.mjs";

export type Tone = "ok" | "pending" | "blocked";

export type TraceLine =
  | { kind: "note"; text: string }
  | { kind: "request"; method: string; text: string }
  | { kind: "result"; text: string; tone: Tone }
  | { kind: "error"; code: number; name: string; reason: string };

const line = (direction: "out" | "in", word: string, head: string, rest = "") =>
  `<li>${arrowSvg(direction)} <span class="visually-hidden">${word}</span> <div class="line">${head}${rest}</div></li>`;

const noteHtml = (text: string) =>
  `<li class="note"><span class="note-mark" aria-hidden="true">#</span> <span class="note-text"><span class="visually-hidden">Comment </span>${escapeHtml(text)}</span></li>`;

function lineHtml(entry: TraceLine): string {
  if (entry.kind === "note") return noteHtml(entry.text);
  if (entry.kind === "request") return line("out", "Request", `<span class="head"><span class="method">${escapeHtml(entry.method)}</span> <span class="payload summary">${escapeHtml(entry.text)}</span></span>`);
  if (entry.kind === "result") return line("in", "Response", `<span class="head"><span class="outcome-result ${entry.tone}">result</span> <span class="payload summary">${escapeHtml(entry.text)}</span></span>`);
  return line("in", "Response", `<span class="head error-head"><span class="outcome-error">error ${entry.code} ${escapeHtml(entry.name)}</span></span>`, ` <span class="reason">${escapeHtml(entry.reason)}</span>`);
}

/** A step's messages in the message trace's markup, each result in the color of its outcome. */
export const traceLinesHtml = (lines: TraceLine[]): string => lines.map(lineHtml).join("");
