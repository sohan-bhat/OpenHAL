import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const repo = fileURLToPath(new URL("../../../", import.meta.url));
const website = join(repo, "website");
const BANNED = [
  "seamless", "supercharge", "elevate", "effortless", "empower", "revolutionary", "next-generation", "cutting-edge",
  "game-changer", "magic", "harness", "unleash", "journey", "welcome to", "the future of", "say goodbye", "blazing fast",
  "enterprise-grade", "works with everything",
];

function walk(dir: string, suffixes: string[]): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return walk(path, suffixes);
    return suffixes.some((suffix) => path.endsWith(suffix)) ? [path] : [];
  });
}

function proseLines(text: string): Array<[number, string]> {
  const out: Array<[number, string]> = [];
  let fence = false;
  let front = text.startsWith("---\n");
  text.split("\n").forEach((line, index) => {
    if (front) {
      if (index > 0 && line === "---") front = false;
      return;
    }
    if (line.startsWith("```")) {
      fence = !fence;
      return;
    }
    if (fence || /^\s*(#|\||<)/.test(line) || !line.trim()) return;
    const prose = line
      .replace(/`[^`]*`/g, "CODE")
      .replace(/\]\([^)]*\)/g, "]")
      .replace(/https?:\/\/\S+/g, "URL");
    out.push([index + 1, prose]);
  });
  return out;
}

const FILE_WORDS = /^\s+(?:(?:a|an|the|its|your|their|one|this|that|each)\s+)?(?:[\w'-]+\s+){0,2}?(?:config|configs|configuration|file|files|sketch|sketches|driver|drivers|routine|routines|test|tests|plan|code|doc|docs|page|pages|yaml)\b/i;

function jargonWrite(prose: string): boolean {
  for (const match of prose.matchAll(/\bwrit(e|es|ing|ten)\b/gi)) {
    if (!FILE_WORDS.test(prose.slice(match.index + match[0].length))) return true;
  }
  return false;
}

const markdown = [
  ...walk(join(repo, "docs", "guide"), [".md"]).filter((path) => !path.endsWith("driver-writer.md")),
  ...walk(join(website, "src", "content"), [".md"]),
];
const markup = walk(join(website, "src"), [".astro", ".svelte", ".ts", ".mjs", ".json"]);

describe("the write rule", () => {
  it("flags write for a command and allows it for a file", () => {
    expect(jargonWrite("Its writes and actions are marked suggested.")).toBe(true);
    expect(jargonWrite("Every write goes through the kernel.")).toBe(true);
    expect(jargonWrite("Write a client's config for you.")).toBe(false);
    expect(jargonWrite("It writes a client config only with a flag.")).toBe(false);
  });
});

describe("Markdown copy follows the rules", () => {
  for (const path of markdown) {
    it(relative(repo, path), () => {
      const problems: string[] = [];
      const text = readFileSync(path, "utf8");
      if (/[–—]/.test(text)) problems.push("contains an em or en dash");
      for (const [line, prose] of proseLines(text)) {
        if (/[;!]/.test(prose)) problems.push(`line ${line} has a semicolon or exclamation mark`);
        if (/:\s/.test(prose) && !/^\s*[-*] \*\*/.test(prose)) problems.push(`line ${line} has a colon in running prose`);
        for (const word of BANNED) if (prose.toLowerCase().includes(word)) problems.push(`line ${line} uses "${word}"`);
        if (/\bunlock/i.test(prose)) problems.push(`line ${line} says unlock outside code`);
        if (jargonWrite(prose)) problems.push(`line ${line} says write. Say command or change`);
        if (/\blayers?\b/i.test(prose)) problems.push(`line ${line} says layer`);
      }
      expect(problems).toEqual([]);
    });
  }
});

describe("Site source has no em or en dashes or banned words", () => {
  for (const path of markup) {
    it(relative(repo, path), () => {
      const text = readFileSync(path, "utf8");
      expect(/[–—]/.test(text), "em or en dash").toBe(false);
      for (const word of BANNED) expect(text.toLowerCase().includes(word), word).toBe(false);
    });
  }
});
