import { readFileSync } from "node:fs";
import { join } from "node:path";
import { REPO_ROOT } from "../spec-meta.mjs";

const PAINT = "fill|stroke|stop-color|flood-color|color";
const COLOR = new RegExp(
  `(?<=\\s(?:${PAINT})="|(?:^|[\\s{;"])(?:${PAINT}|background(?:-color)?|border-color|--[\\w-]+)\\s*:\\s*)#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?=["};\\s])`,
  "g",
);

const FACES = {
  regular: ["var(--font-text)", 400],
  italic: ["var(--font-text)", 400],
  semibold: ["var(--font-text)", 600],
  bold: ["var(--font-text)", 700],
  mono: ["var(--font-mono)", 400],
  "mono-italic": ["var(--font-mono)", 400],
  "mono-semibold": ["var(--font-mono)", 600],
  "mono-bold": ["var(--font-mono)", 700],
};

let tokens = null;

/**
 * The color tokens of design/tokens.css as a map from "light>dark" to the token's name, so a
 * diagram color that is exactly a token in both themes follows the page's theme by name.
 */
export function themeTokens(root = REPO_ROOT) {
  const css = readFileSync(join(root, "design", "tokens.css"), "utf8");
  const block = (pattern) =>
    Object.fromEntries([...(css.match(pattern)?.[1] ?? "").matchAll(/(--[\w-]+):\s*(#[0-9a-fA-F]{3,6})\s*;/g)].map((match) => [match[1], match[2].toLowerCase()]));
  const light = block(/:root\s*\{([^}]*)\}/);
  const dark = block(/:root\[data-theme="dark"\]\s*\{([^}]*)\}/);
  return new Map(
    Object.keys(dark)
      .filter((name) => light[name])
      .map((name) => [`${light[name]}>${dark[name]}`, name]),
  );
}

function d2Id(svg) {
  return svg.match(/\bd2-(\d+)\b/)?.[1] ?? null;
}

function canonical(svg) {
  const id = d2Id(svg);
  const markers = [...new Set(svg.match(/\bmk-d2-\d+-\d+\b/g) ?? [])];
  let text = svg.replace(/@font-face\s*\{[^}]*\}/g, "");
  markers.forEach((marker, index) => (text = text.replaceAll(marker, `mk-${index}`)));
  return id ? text.replaceAll(`d2-${id}`, "d2-ID") : text;
}

function withoutUnusedRules(css, body) {
  const classes = new Set([...body.matchAll(/\sclass="([^"]*)"/g)].flatMap((match) => match[1].split(/\s+/)));
  return css.replace(/(?<=^|[}\s])(?:\.d2-[\w]+\s+)?\.([\w-]+)(?:\s+[\w.-]+)*\s*\{[^}]*\}/g, (rule, name) => (classes.has(name) ? rule : ""));
}

function pageFonts(css) {
  return css.replace(/font-family:\s*"?d2-[\w]+-font-([\w-]+)"?\s*;?/g, (match, role) => {
    const face = FACES[role];
    return face ? `font-family:${face[0]};font-weight:${face[1]};font-style:normal;font-kerning:none;` : match;
  });
}

function d2Name(token) {
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(token) || token.length % 4) return false;
  return /^[\x20-\x7e]+$/.test(Buffer.from(token, "base64").toString("latin1"));
}

function withoutD2Names(svg) {
  return svg.replace(/\sclass="([^"]*)"/g, (match, value) => {
    const kept = value.split(/\s+/).filter((token) => token && !d2Name(token));
    return kept.length ? ` class="${kept.join(" ")}"` : "";
  });
}

function hoistedStyles(svg, scope) {
  const counts = new Map();
  for (const match of svg.matchAll(/<(?:rect|path|text|line|polygon|circle|ellipse)\b[^>]*?\sstyle="([^"]+)"/g)) counts.set(match[1], (counts.get(match[1]) ?? 0) + 1);
  const shared = [...counts].filter(([, count]) => count >= 3).map(([style], index) => [style, `s${index + 1}`]);
  if (!shared.length) return { svg, css: "" };
  const names = new Map(shared);
  const out = svg.replace(/<(rect|path|text|line|polygon|circle|ellipse)\b([^>]*?)>/g, (tag, name, attributes) => {
    const style = attributes.match(/\sstyle="([^"]+)"/)?.[1];
    const short = style && names.get(style);
    if (!short) return tag;
    let rest = attributes.replace(/\sstyle="[^"]+"/, "");
    rest = /\sclass="/.test(rest) ? rest.replace(/\sclass="([^"]*)"/, (_, value) => ` class="${value} ${short}"`) : `${rest.replace(/\/$/, "")} class="${short}"${rest.endsWith("/") ? "/" : ""}`;
    return `<${name}${rest}>`;
  });
  return { svg: out, css: shared.map(([style, short]) => `${scope} .${short}{${style}}`).join("") };
}

function restyle(input, vars = "") {
  const named = withoutD2Names(input).replace(/\sdata-d2-version="[^"]*"/, "");
  const scope = `.d2-${d2Id(named) ?? "ID"}`;
  const { svg, css: hoisted } = hoistedStyles(named, named.includes("d2-ID") ? ".d2-ID" : scope);
  const body = svg.replace(/<style[\s\S]*?<\/style>/g, "");
  return svg.replace(/(<style[^>]*>(?:<!\[CDATA\[)?)([\s\S]*?)((?:\]\]>)?<\/style>)/, (_, open, css, close) => {
    const kept = pageFonts(withoutUnusedRules(css, body))
      .split("\n")
      .map((line) => line.trim())
      .join("");
    return `${open}${vars}${kept}${hoisted}${close}`;
  });
}

/**
 * A D2 diagram for a page that already has the fonts. Its embedded fonts go and its text uses the
 * page's faces at the weights D2 drew with, without kerning since D2's fonts have none. Style rules
 * for classes nothing in the diagram uses go too, and so do the encoded element names D2 writes as
 * classes, which nothing on the site reads.
 */
export function fontless(svg) {
  return restyle(svg.replace(/@font-face\s*\{[^}]*\}/g, ""));
}

/**
 * One SVG for both themes from a D2 diagram's light and dark files, as fontless() leaves them. Every
 * color that differs between the files becomes a custom property, the design token when the pair is
 * one, otherwise a property the SVG's own style sets for each theme the way design/tokens.css does.
 * Returns null when the files differ in anything but color, so the caller can ship both.
 */
export function themedDiagram(lightSvg, darkSvg, theme = (tokens ??= themeTokens())) {
  const light = canonical(lightSvg);
  const dark = canonical(darkSvg);
  if (light.replace(COLOR, "#") !== dark.replace(COLOR, "#")) return null;
  const darkColors = dark.match(COLOR) ?? [];
  const own = new Map();
  let index = 0;
  const svg = light.replace(COLOR, (color) => {
    const from = color.toLowerCase();
    const to = darkColors[index++].toLowerCase();
    if (from === to) return color;
    const pair = `${from}>${to}`;
    const token = theme.get(pair);
    if (token) return `var(${token})`;
    if (!own.has(pair)) own.set(pair, `--d2-${own.size + 1}`);
    return `var(${own.get(pair)})`;
  });
  const id = d2Id(lightSvg) ?? "0";
  const scope = `.d2-${id}`;
  const list = [...own].map(([pair, name]) => [name, ...pair.split(">")]);
  const set = (side) => list.map((item) => `${item[0]}:${item[side]}`).join(";");
  const vars = list.length
    ? `${scope}{${set(1)}}@media (prefers-color-scheme:dark){:root:not([data-theme="light"]) ${scope}{${set(2)}}}:root[data-theme="dark"] ${scope}{${set(2)}}`
    : "";
  return restyle(svg, vars).replaceAll("d2-ID", `d2-${id}`);
}
