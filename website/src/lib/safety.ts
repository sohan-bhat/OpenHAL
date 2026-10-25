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

const PLAIN: Record<string, string> = {
  "One path": "Every command from every client goes through the same kernel.",
  Deterministic: "Plain code with no model. The same command in the same state gets the same answer.",
  "Limits come from humans": "Agents can narrow limits, never widen them.",
  "Stop works": "One stop puts every device in its safe state. Only a person lifts it.",
  "Fail closed": "Anything unexpected blocks the command.",
  "Everything is recorded": "Every command and decision goes into a tamper-evident log.",
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
