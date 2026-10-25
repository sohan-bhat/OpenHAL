// The safety model's guarantees and checks, read from docs/SAFETY.md at build time so the landing
// page can't drift from the document the kernel is reviewed against.

import safety from "../../../docs/SAFETY.md?raw";

export interface Guarantee {
  title: string;
  text: string;
}

export interface Check {
  number: string;
  check: string;
  blocksWhen: string;
  codes: string[];
}

function section(heading: string): string {
  const start = safety.indexOf(`\n## ${heading}\n`);
  if (start === -1) throw new Error(`docs/SAFETY.md has no section "${heading}".`);
  const rest = safety.slice(start + heading.length + 5);
  const end = rest.search(/\n## /);
  return end === -1 ? rest : rest.slice(0, end);
}

function plain(text: string): string {
  return text.replace(/\*\*/g, "").replace(/`/g, "").trim();
}

function firstSentence(text: string): string {
  const match = /^(.*?[.])(\s|$)/s.exec(text);
  return (match ? match[1] : text).trim();
}

// The landing page says each guarantee in plain words. Titles come from docs/SAFETY.md, so a new
// guarantee shows up with its own first sentence until it gets a plain version here.
const PLAIN: Record<string, string> = {
  "One path": "Every write and every action goes through the same kernel, whether it came from an agent, a script, a routine or the dashboard.",
  Deterministic: "The kernel is plain code with no model in it. The same command in the same state always gets the same answer.",
  "Limits come from humans": "An agent can narrow its own limits but never widen them. A device with limits nobody confirmed is read-only.",
  "Stop works": "One stop puts every device in its safe state. Writes stay locked until a person lifts the stop.",
  "Fail closed": "If anything unexpected happens inside the kernel, the command is blocked. A value the hub can't trust counts as unsafe.",
  "Everything is recorded": "Every read, write, block, approval and stop goes into an append-only log that can be checked for tampering.",
};

export function guarantees(): Guarantee[] {
  const out: Guarantee[] = [];
  for (const match of section("Guarantees").matchAll(/^\d+\. \*\*(.+?)\*\* (.+)$/gm)) {
    const title = match[1].replace(/\.$/, "");
    out.push({ title, text: PLAIN[title] ?? firstSentence(plain(match[2])) });
  }
  return out;
}

export function checks(): Check[] {
  const out: Check[] = [];
  for (const line of section("The checks, in order").split("\n")) {
    const cells = line.split("|").map((cell) => cell.trim());
    if (cells.length < 6 || !/^\d+$/.test(cells[1])) continue;
    out.push({
      number: cells[1],
      check: cells[2],
      blocksWhen: plain(cells[3]),
      codes: [...cells[4].matchAll(/`([a-z_]+)`/g)].map((match) => match[1]),
    });
  }
  return out;
}

export function notGuaranteed(): string[] {
  return [...section("What OpenHAL does not guarantee").matchAll(/^- (.+)$/gm)].map((match) => plain(match[1]));
}
