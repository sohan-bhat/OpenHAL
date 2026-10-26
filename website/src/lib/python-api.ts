import { escapeHtml } from "./highlight.mjs";

export interface MethodPlace {
  group: string;
  route: string | null;
  human: boolean;
}

export interface MethodGuide {
  groups: string[];
  places: Map<string, MethodPlace>;
}

const OPEN = "([{";
const CLOSE = ")]}";

function splitTopLevel(text: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let start = 0;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (OPEN.includes(char)) depth += 1;
    else if (CLOSE.includes(char)) depth -= 1;
    else if (char === "," && depth === 0) {
      parts.push(text.slice(start, index).trim());
      start = index + 1;
    }
  }
  const last = text.slice(start).trim();
  if (last) parts.push(last);
  return parts;
}

export function formatSignature(signature: string, width = 56): string {
  if (signature.length <= width) return signature;
  const open = signature.indexOf("(");
  if (open === -1) return signature;
  let depth = 0;
  let close = -1;
  for (let index = open; index < signature.length; index += 1) {
    if (OPEN.includes(signature[index])) depth += 1;
    else if (CLOSE.includes(signature[index])) {
      depth -= 1;
      if (depth === 0) {
        close = index;
        break;
      }
    }
  }
  if (close === -1) return signature;
  const params = splitTopLevel(signature.slice(open + 1, close));
  if (params.length < 2) return signature;
  return `${signature.slice(0, open + 1)}\n${params.map((param) => `    ${param},`).join("\n")}\n${signature.slice(close)}`;
}

export function inlineCode(text: string): string {
  return escapeHtml(text).replace(/`([^`]+)`/g, "<code>$1</code>");
}

export function paragraphs(text: string): string[] {
  return text.split(/\n\s*\n/).filter((part) => part.trim() && !/^\s{4}/m.test(part));
}

const NAME = /`(?:[A-Za-z]+\.)?([a-z_][a-z0-9_]*)\(/;

export function methodGuide(markdown: string, fallback = "Connection"): MethodGuide {
  const groups: string[] = [];
  const places = new Map<string, MethodPlace>();
  const start = markdown.indexOf("\n## Methods");
  if (start === -1) return { groups, places };
  const end = markdown.indexOf("\n## ", start + 4);
  let group = "";
  for (const line of markdown.slice(start, end === -1 ? undefined : end).split("\n")) {
    const heading = /^### (.+)$/.exec(line);
    if (heading) {
      group = heading[1].trim();
      continue;
    }
    if (!group) continue;
    const row = /^\|(.+?)\|(.+)\|\s*$/.exec(line);
    if (row) {
      const name = NAME.exec(row[1])?.[1];
      if (!name || places.has(name)) continue;
      if (!groups.includes(group)) groups.push(group);
      places.set(name, { group, route: row[2].trim(), human: /\(human\b/.test(row[2]) });
      continue;
    }
    for (const match of line.matchAll(/`(?:client|hub|Client|AsyncClient)\.([a-z_][a-z0-9_]*)\(/g)) {
      if (places.has(match[1])) continue;
      if (!groups.includes(group)) groups.push(group);
      places.set(match[1], { group, route: null, human: false });
    }
  }
  return { groups: [fallback, ...groups], places };
}

export function placeOf(guide: MethodGuide, name: string, fallback = "Connection"): MethodPlace {
  return guide.places.get(name) ?? { group: fallback, route: null, human: false };
}
