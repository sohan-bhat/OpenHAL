import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { palette } from "../src/lib/palette.mjs";

const root = fileURLToPath(new URL("../../", import.meta.url));
const TOKENS = ["bg", "surface", "border", "text", "text-2", "neutral", "highlight", "accent", "accent-fill", "accent-fill-hover", "on-accent", "scrollbar-thumb", "ok", "confirm", "blocked", "unverified"];
const SAME = ["accent-fill", "accent-fill-hover", "on-accent"];
const D2 = { surface: "surface", line: "scrollbar-thumb", text: "text", text2: "text-2", blocked: "blocked", "blocked-fill": "blocked-fill", ok: "ok", border: "border" };
const PY = { line: "scrollbar-thumb", blocked: "blocked", label: "text-2", border: "border" };

function block(css, opener, theme) {
  const start = css.indexOf(opener);
  if (start < 0) throw new Error(`design/tokens.css has no ${opener}`);
  const open = css.indexOf("{", start + opener.length - 1);
  let depth = 0;
  let end = open;
  for (; end < css.length; end++) {
    if (css[end] === "{") depth++;
    if (css[end] === "}" && --depth === 0) break;
  }
  let body = css.slice(open + 1, end);
  const indent = body.match(/\n(\s+)--/)?.[1] ?? "  ";
  const names = theme === "light" ? TOKENS : TOKENS.filter((name) => !SAME.includes(name));
  let last = -1;
  for (const name of names) {
    const line = new RegExp(`(\\n\\s*--${name}:\\s*)[^;]+;`);
    const value = palette[theme][name];
    if (line.test(body)) {
      body = body.replace(line, `$1${value};`);
      last = Math.max(last, body.search(line) + body.match(line)[0].length);
    } else {
      const at = last >= 0 ? last : body.search(/\n\s*--[\w-]+:[^;]+;/) + body.match(/\n\s*--[\w-]+:[^;]+;/)[0].length;
      const added = `\n${indent}--${name}: ${value};`;
      body = body.slice(0, at) + added + body.slice(at);
      last = at + added.length;
    }
  }
  return css.slice(0, open + 1) + body + css.slice(end);
}

/** design/tokens.css with every palette value in its light, dark and forced dark blocks. */
export function tokensCss(css) {
  let out = block(css, ":root {", "light");
  out = block(out, ':root:not([data-theme="light"]) {', "dark");
  out = block(out, ':root[data-theme="dark"] {', "dark");
  return out;
}

/** A D2 theme file's variables for one theme. */
export function d2Theme(theme) {
  return Object.entries(D2)
    .map(([name, token]) => `${name}: "${palette[theme][token].toUpperCase()}"`)
    .join("\n") + "\n";
}

/** scripts/diagrams.py with its THEMES colors from the palette. */
export function diagramsPy(source) {
  const dict = (theme) => `{${Object.entries(PY).map(([name, token]) => `"${name}": "${palette[theme][token].toUpperCase()}"`).join(", ")}}`;
  return source.replace(/THEMES = \{\n    "light": \{[^}]*\},\n    "dark": \{[^}]*\},\n\}/, `THEMES = {\n    "light": ${dict("light")},\n    "dark": ${dict("dark")},\n}`);
}

const BRAND = { surface: "surface", border: "border", text: "text", text2: "text-2", ok: "ok", blocked: "blocked" };

/** scripts/readme/build.py with the colors of its wordmark, mark and favicon from the palette. */
export function brandPy(source) {
  const theme = (name) =>
    `    "${name}": {\n${Object.entries(BRAND)
      .map(([key, token]) => `        "${key}": "${palette[name][token].toUpperCase()}",`)
      .join("\n")}\n    },`;
  return source.replace(/THEMES = \{\n    "light": \{[^}]*\},\n    "dark": \{[^}]*\},\n\}/, `THEMES = {\n${theme("light")}\n${theme("dark")}\n}`);
}

export const FILES = {
  "design/tokens.css": tokensCss,
  "docs/diagrams/theme-light.d2": () => d2Theme("light"),
  "docs/diagrams/theme-dark.d2": () => d2Theme("dark"),
  "scripts/diagrams.py": diagramsPy,
  "scripts/readme/build.py": brandPy,
};

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  for (const [path, make] of Object.entries(FILES)) {
    const file = root + path;
    const before = readFileSync(file, "utf8");
    const after = make(before);
    if (after !== before) {
      writeFileSync(file, after);
      console.log(`wrote ${path}`);
    }
  }
}
