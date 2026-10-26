import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fromHtml } from "hast-util-from-html";
import { createMermaidRenderer } from "mermaid-isomorphic";
import { visit } from "unist-util-visit";
import { REPO_ROOT } from "../spec-meta.mjs";

const FONT = "Atkinson Hyperlegible Next";
const MONO = "Atkinson Hyperlegible Mono";

function fontCss() {
  const face = (family, file) => {
    const data = readFileSync(join(REPO_ROOT, "design", "fonts", file)).toString("base64");
    return `@font-face{font-family:"${family}";font-weight:200 800;src:url(data:font/woff2;base64,${data}) format("woff2");}`;
  };
  const css = face(FONT, "atkinson-hyperlegible-next-latin-wght-normal.woff2") + face(MONO, "atkinson-hyperlegible-mono-latin-wght-normal.woff2");
  return `data:text/css;base64,${Buffer.from(css).toString("base64")}`;
}

function theme({ text, text2, bg, surface, border, accent }) {
  return {
    theme: "base",
    fontFamily: `"${FONT}", sans-serif`,
    htmlLabels: false,
    flowchart: { htmlLabels: false, curve: "linear", padding: 12, nodeSpacing: 40, rankSpacing: 48, useMaxWidth: false },
    sequence: { useMaxWidth: false, mirrorActors: false, actorMargin: 24, wrap: true, width: 120, messageMargin: 28, boxMargin: 6, noteMargin: 6 },
    state: { useMaxWidth: false },
    themeVariables: {
      fontFamily: `"${FONT}", sans-serif`,
      fontSize: "14px",
      background: "transparent",
      mainBkg: bg,
      primaryColor: bg,
      primaryTextColor: text,
      primaryBorderColor: text2,
      secondaryColor: surface,
      tertiaryColor: surface,
      lineColor: text2,
      textColor: text,
      clusterBkg: surface,
      clusterBorder: border,
      titleColor: text,
      edgeLabelBackground: bg,
      nodeBorder: text2,
      actorBkg: bg,
      actorBorder: text2,
      actorTextColor: text,
      actorLineColor: border,
      signalColor: text2,
      signalTextColor: text,
      labelBoxBkgColor: surface,
      labelBoxBorderColor: border,
      labelTextColor: text,
      loopTextColor: text,
      noteBkgColor: surface,
      noteBorderColor: border,
      noteTextColor: text,
      activationBkgColor: surface,
      activationBorderColor: text2,
      stateBkg: bg,
      stateBorder: text2,
      transitionColor: text2,
      transitionLabelColor: text,
      altBackground: surface,
      linkColor: accent,
    },
  };
}

const LIGHT = theme({ text: "#15181c", text2: "#4f5661", bg: "#fcfcfd", surface: "#f4f5f7", border: "#dadde2", accent: "#1d5fb4" });
const DARK = theme({ text: "#e7eaee", text2: "#a0a7b1", bg: "#0d0f12", surface: "#15181d", border: "#2a2f36", accent: "#7db2f0" });

let renderer = null;
let css = null;
let redraws = null;

export function mermaidHash(source) {
  return createHash("sha256").update(source.trim()).digest("hex").slice(0, 16);
}

export function redrawManifest(root = REPO_ROOT) {
  const path = join(root, "docs", "diagrams", "diagrams.json");
  return existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : [];
}

function scopedSvg(svg, prefix) {
  return svg
    .replace(/<\?xml[^>]*>/, "")
    .trim()
    .replace(/\sid="([^"]+)"/g, ` id="${prefix}-$1"`)
    .replace(/url\(#([^)]+)\)/g, `url(#${prefix}-$1)`)
    .replace(/href="#([^"]+)"/g, `href="#${prefix}-$1"`)
    .replace(/aria-labelledby="([^"]+)"/g, (_, ids) => `aria-labelledby="${ids.split(/\s+/).map((id) => `${prefix}-${id}`).join(" ")}"`);
}

export function redrawFor(source, root = REPO_ROOT) {
  redraws ??= redrawManifest(root);
  const entry = redraws.find((item) => item.mermaid === mermaidHash(source));
  if (!entry) return null;
  const file = (theme) => join(root, "docs", "diagrams", `${entry.name}-${theme}.svg`);
  if (!existsSync(file("light")) || !existsSync(file("dark"))) return null;
  return { ...entry, light: readFileSync(file("light"), "utf8"), dark: readFileSync(file("dark"), "utf8") };
}

function textOf(node) {
  if (node.type === "text") return node.value;
  return (node.children ?? []).map(textOf).join("");
}

function fixedSize(svg, width, height) {
  return svg.replace(/<svg([^>]*?)\swidth="[^"]*"/, "<svg$1").replace(/<svg([^>]*?)\sstyle="[^"]*"/, "<svg$1").replace("<svg", `<svg width="${Math.ceil(width)}" height="${Math.ceil(height)}"`);
}

export function rehypeDiagrams() {
  return async (tree) => {
    const blocks = [];
    visit(tree, "element", (node, index, parent) => {
      if (node.tagName !== "pre" || !parent || index === undefined) return;
      const code = node.children.find((child) => child.type === "element" && child.tagName === "code");
      const classes = code?.properties?.className ?? [];
      if (!(Array.isArray(classes) ? classes : [classes]).includes("language-mermaid")) return;
      blocks.push({ parent, index, source: textOf(code) });
    });
    if (!blocks.length) return;
    for (const block of blocks.reverse()) {
      const redraw = redrawFor(block.source);
      if (redraw) {
        const html =
          `<figure class="diagram house" role="group" aria-label="${redraw.title.replace(/"/g, "&quot;")}">` +
          `<div class="diagram-scroll">` +
          `<div class="diagram-light">${scopedSvg(redraw.light, `${redraw.name}-l`)}</div>` +
          `<div class="diagram-dark">${scopedSvg(redraw.dark, `${redraw.name}-d`)}</div>` +
          `</div></figure>`;
        block.parent.children.splice(block.index, 1, ...fromHtml(html, { fragment: true }).children);
        continue;
      }
      renderer ??= createMermaidRenderer();
      css ??= fontCss();
      const hash = createHash("sha256").update(block.source).digest("hex").slice(0, 8);
      const [light] = await renderer([block.source], { mermaidConfig: LIGHT, css, prefix: `d${hash}l` });
      const [dark] = await renderer([block.source], { mermaidConfig: DARK, css, prefix: `d${hash}d` });
      if (light.status !== "fulfilled" || dark.status !== "fulfilled") continue;
      const title = light.value.title ?? light.value.description ?? "Diagram";
      const html =
        `<figure class="diagram" role="group" aria-label="${title.replace(/"/g, "&quot;")}">` +
        `<div class="diagram-scroll">` +
        `<div class="diagram-light">${fixedSize(light.value.svg, light.value.width, light.value.height)}</div>` +
        `<div class="diagram-dark">${fixedSize(dark.value.svg, dark.value.width, dark.value.height)}</div>` +
        `</div></figure>`;
      block.parent.children.splice(block.index, 1, ...fromHtml(html, { fragment: true }).children);
    }
  };
}
