#!/usr/bin/env node
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { extname, join } from "node:path";

const [dist = "dist", rawBase = "/OpenHAL", host = "https://sohan-bhat.github.io"] = process.argv.slice(2);
const base = `/${rawBase.replace(/^\/+|\/+$/g, "")}`;
const escaped = base.slice(1).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const TEXT = new Set([".html", ".css", ".js", ".mjs", ".xml", ".txt", ".webmanifest", ".json", ".svg"]);
const ATTRIBUTES = "href|src|action|poster|component-url|renderer-url|before-hydration-url|data-src|data-href";

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? files(full) : TEXT.has(extname(name)) ? [full] : [];
  });
}

function prefix(path) {
  return path.startsWith(`${base}/`) || path === base ? path : `${base}${path}`;
}

export function rebase(text) {
  const notBase = `(?!${escaped}(?:[/"'?#]|$))`;
  return text
    .replace(new RegExp(`\\b(${ATTRIBUTES})=(["'])/(?!/)${notBase}`, "g"), `$1=$2${base}/`)
    .replace(/\b((?:image)?srcset)=(["'])([^"']*)\2/g, (_, name, quote, value) => {
      const items = value.split(",").map((item) => {
        const [url, ...rest] = item.trim().split(/\s+/);
        return [url.startsWith("/") && !url.startsWith("//") ? prefix(url) : url, ...rest].join(" ");
      });
      return `${name}=${quote}${items.join(", ")}${quote}`;
    })
    .replace(new RegExp(`url\\((["']?)/(?!/)${notBase}`, "g"), `url($1${base}/`)
    .replace(new RegExp(`(["'\`])/_astro/`, "g"), `$1${base}/_astro/`)
    .replace(new RegExp(`"(src|start_url|scope|href_matches)":\\s*"/(?!/)${notBase}`, "g"), `"$1": "${base}/`)
    .replace(new RegExp(`${host.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}/${notBase}`, "g"), `${host}${base}/`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  let changed = 0;
  for (const file of files(dist)) {
    const before = readFileSync(file, "utf8");
    const after = rebase(before);
    if (after !== before) {
      writeFileSync(file, after);
      changed += 1;
    }
  }
  console.log(`Rebased ${changed} files in ${dist} onto ${host}${base}/`);
}
