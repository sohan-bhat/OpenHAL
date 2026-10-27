#!/usr/bin/env node
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const TEXT = new Set([".html", ".js", ".mjs", ".css"]);
const SKIP = new Set(["pagefind", "og", "captures", "brand"]);

function files(dir, root = dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return SKIP.has(relative(root, full)) ? [] : files(full, root);
    return TEXT.has(extname(name)) ? [full] : [];
  });
}

/**
 * Every character beyond printable ASCII that a build can put on screen, from its pages, scripts and
 * styles, as sorted hexadecimal code points. Control characters are left out.
 */
export function siteCodepoints(dist) {
  const found = new Set();
  for (const file of files(dist)) {
    for (const char of readFileSync(file, "utf8")) {
      const code = char.codePointAt(0);
      if (code > 0x7e && !(code >= 0x7f && code <= 0x9f)) found.add(code);
    }
  }
  return [...found].sort((a, b) => a - b).map((code) => code.toString(16).toUpperCase().padStart(4, "0"));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const [dist = "dist", out = "src/fonts/glyphs.json"] = process.argv.slice(2);
  const codepoints = siteCodepoints(dist);
  writeFileSync(out, `${JSON.stringify({ codepoints }, null, 2)}\n`);
  console.log(`${codepoints.length} characters beyond ASCII in ${dist}, written to ${out}`);
}
