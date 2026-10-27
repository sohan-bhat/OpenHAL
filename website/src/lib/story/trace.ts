import { escapeHtml } from "../highlight.mjs";
import { arrowSvg } from "../trace-html.mjs";

export type Tone = "ok" | "pending" | "blocked";

export interface AuditRow {
  seq: number;
  event: string;
  who: string;
  target: string;
  status: string;
  tone: Tone | "plain";
}

export type TraceLine =
  | { kind: "note"; text: string; keep?: boolean }
  | { kind: "request"; method: string; text: string }
  | { kind: "result"; text: string; tone: Tone }
  | { kind: "error"; code: number; name: string; reason: string }
  | { kind: "audit"; caption: string; rows: AuditRow[] };

const COLUMNS = ["seq", "event", "who", "target", "status"] as const;

const line = (direction: "out" | "in", word: string, head: string, rest = "") =>
  `<li>${arrowSvg(direction)} <span class="visually-hidden">${word}</span> <div class="line">${head}${rest}</div></li>`;

function auditHtml(caption: string, rows: AuditRow[]): string {
  const head = COLUMNS.map((column) => `<th scope="col" class="audit-${column}">${column}</th>`).join("");
  const body = rows
    .map((row) => `<tr>${COLUMNS.map((column) => `<td class="audit-${column}${column === "status" ? ` ${row.tone}` : ""}">${escapeHtml(String(row[column]))}</td>`).join("")}</tr>`)
    .join("");
  return `<li class="audit"><table class="audit-log"><caption class="visually-hidden">Audit log, newest first, as ${escapeHtml(caption)} prints it</caption><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></li>`;
}

const noteHtml = (text: string, keep = false) =>
  `<li class="note${keep ? " keep" : ""}"><span class="note-mark" aria-hidden="true">#</span> <span class="note-text"><span class="visually-hidden">Comment </span>${escapeHtml(text)}</span></li>`;

function lineHtml(entry: TraceLine): string {
  if (entry.kind === "note") return noteHtml(entry.text, entry.keep);
  if (entry.kind === "request") return line("out", "Request", `<span class="head"><span class="method">${escapeHtml(entry.method)}</span> <span class="payload summary">${escapeHtml(entry.text)}</span></span>`);
  if (entry.kind === "result") return line("in", "Response", `<span class="head"><span class="outcome-result ${entry.tone}">result</span> <span class="payload summary">${escapeHtml(entry.text)}</span></span>`);
  if (entry.kind === "error") return line("in", "Response", `<span class="head error-head"><span class="outcome-error">error ${entry.code} ${escapeHtml(entry.name)}</span></span>`, ` <span class="reason">${escapeHtml(entry.reason)}</span>`);
  return auditHtml(entry.caption, entry.rows);
}

/** A step's messages in the message trace's markup, each result in the color of its outcome. */
export const traceLinesHtml = (lines: TraceLine[]): string => lines.map(lineHtml).join("");
