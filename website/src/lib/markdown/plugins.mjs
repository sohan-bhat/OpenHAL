import { existsSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import GithubSlugger from "github-slugger";
import { SKIP, visit } from "unist-util-visit";
import { indentOf, languageOf, splitLines, tokenize } from "../highlight.mjs";
import { REPO_ROOT, glossaryHref, numberPages, readVersions, specDir, specFiles, termAnchor, versionOfFolder } from "../spec-meta.mjs";
import { fromHtml } from "hast-util-from-html";
import { scenarioTraceHtml } from "../scenario-data.mjs";
import { linkFor } from "./routes.mjs";

export { REPO_ROOT };

function textOf(node) {
  if (node.type === "text" || node.type === "inlineCode") return node.value;
  return (node.children ?? []).map(textOf).join("");
}

function hastText(node) {
  if (node.type === "text") return node.value;
  return (node.children ?? []).map(hastText).join("");
}

export function remarkTitle() {
  return (tree, file) => {
    const index = tree.children.findIndex((node) => node.type === "heading" && node.depth === 1);
    if (index === -1) return;
    const title = textOf(tree.children[index]);
    tree.children.splice(index, 1);
    file.data.astro ??= {};
    file.data.astro.frontmatter ??= {};
    file.data.astro.frontmatter.title ??= title;
  };
}

export function remarkRepoLinks() {
  return (tree, file) => {
    const source = file.path ? resolve(file.path) : null;
    visit(tree, "link", (node, index, parent) => {
      const url = node.url;
      if (url.startsWith("glossary:")) {
        const href = glossaryHref(url.slice(9));
        if (href) node.url = href;
        else if (parent && index !== undefined) {
          parent.children.splice(index, 1, ...node.children);
          return [SKIP, index];
        }
        return undefined;
      }
      if (!source || /^[a-z]+:/i.test(url) || url.startsWith("#") || url.startsWith("/")) return undefined;
      const [path, hash] = url.split("#");
      const repoPath = relative(REPO_ROOT, resolve(dirname(source), path)).split("\\").join("/");
      const route = linkFor(repoPath);
      if (route) {
        node.url = hash && !route.includes("#") ? `${route}#${hash}` : route;
      } else if (parent && index !== undefined) {
        parent.children.splice(index, 1, { type: "inlineCode", value: textOf(node) || repoPath });
      }
      return undefined;
    });
  };
}

function el(tagName, properties, children) {
  return { type: "element", tagName, properties, children };
}

function classList(node) {
  const value = node.properties?.className;
  return Array.isArray(value) ? value.map(String) : value ? String(value).split(" ") : [];
}

const ARROWS = { "→": "out", "←": "in" };

function arrowElement(direction) {
  const line = direction === "out" ? { x1: 1, y1: 5, x2: 11, y2: 5 } : { x1: 7, y1: 5, x2: 17, y2: 5 };
  const head = direction === "out" ? "18,5 11,1.5 11,8.5" : "0,5 7,1.5 7,8.5";
  return el(
    "svg",
    { className: ["trace-arrow"], viewBox: "0 0 18 10", role: "img", ariaLabel: direction === "out" ? "Request" : "Response", fill: "currentColor" },
    [el("line", { ...line, stroke: "currentColor", strokeWidth: 1.5 }, []), el("polygon", { points: head }, [])],
  );
}

function tokenNode([cls, value]) {
  return cls ? el("span", { className: [`syn-${cls}`] }, [{ type: "text", value }]) : { type: "text", value };
}

function lineNode(children, indent, last) {
  return el("span", { className: ["line"], ...(indent ? { style: `--indent: ${indent}` } : {}) }, last ? children : [...children, { type: "text", value: "\n" }]);
}

function codeLines(text, language) {
  const lines = splitLines(tokenize(text, language));
  return lines.map((tokens, index) => lineNode(tokens.map(tokenNode), indentOf(tokens), index === lines.length - 1));
}

function isTrace(text, language) {
  const first = text.split("\n").find((line) => line.trim());
  return language === "json" && first !== undefined && first[0] in ARROWS;
}

function traceLines(text) {
  const lines = text.split("\n");
  return lines.map((line, index) => {
    const direction = ARROWS[line[0]];
    const tokens = tokenize(direction ? line.slice(1).replace(/^ /, "") : line, "json");
    const children = [...(direction ? [arrowElement(direction)] : []), ...tokens.map(tokenNode)];
    return lineNode(children, direction ? 2 : indentOf(tokens), index === lines.length - 1);
  });
}

export function codeFigure(text, lang, tested) {
  const language = languageOf(lang);
  const trace = isTrace(text, language);
  const spans = trace ? traceLines(text) : codeLines(text, language);
  return el("figure", { className: ["code-block", ...(trace ? ["trace-code"] : [])], dataLanguage: language, ...(tested ? { dataTested: "true" } : {}) }, [
    el("pre", { tabIndex: 0 }, [el("code", { className: [`language-${language}`] }, spans)]),
  ]);
}

export function rehypeCodeBlocks() {
  return (tree) => {
    visit(tree, "element", (node, index, parent) => {
      if (node.tagName !== "pre" || !parent || index === undefined) return undefined;
      const code = node.children.find((child) => child.type === "element" && child.tagName === "code");
      if (!code) return undefined;
      const language = classList(code).find((name) => name.startsWith("language-"))?.slice(9) ?? "text";
      if (language === "mermaid") return undefined;
      const meta = String(code.data?.meta ?? "");
      const tested = /(^|\s)tested(\s|$)/.test(meta);
      if (language === "scenario") {
        parent.children.splice(index, 1, ...fromHtml(scenarioTraceHtml(), { fragment: true }).children);
        return SKIP;
      }
      const include = /(?:^|\s)include=(\S+)/.exec(meta)?.[1];
      if (include) {
        const path = join(REPO_ROOT, include);
        if (!existsSync(path)) throw new Error(`A code block includes ${include}, which doesn't exist.`);
        parent.children[index] = codeFigure(readFileSync(path, "utf8").replace(/\n$/, ""), language, tested);
        return SKIP;
      }
      parent.children[index] = codeFigure(hastText(code).replace(/\n$/, ""), language, tested);
      return SKIP;
    });
  };
}

let registryCache = null;

export function errorRegistry(root = REPO_ROOT) {
  if (registryCache) return registryCache;
  const { latest } = readVersions(root);
  const names = new Map();
  const blocked = new Set();
  if (latest) {
    const schema = join(specDir(latest, root), "schema.json");
    if (existsSync(schema)) for (const entry of JSON.parse(readFileSync(schema, "utf8")).errors ?? []) names.set(entry.name, entry.code);
    const safety = join(specDir(latest, root), "safety.md");
    if (existsSync(safety)) {
      for (const row of readFileSync(safety, "utf8").matchAll(/^\|\s*\d+\s*\|(.*)\|\s*$/gm)) {
        const last = row[1].split("|").pop() ?? "";
        for (const name of last.split(",").map((part) => part.trim())) if (names.has(name)) blocked.add(name);
      }
    }
  }
  registryCache = { names, blocked, codes: new Set(names.values()) };
  return registryCache;
}

function registryNameNode(name, registry) {
  const tone = name === "CONFIRMATION_REQUIRED" ? ["status", "confirm"] : registry.blocked.has(name) ? ["status", "blocked"] : [];
  return el("span", { className: [...tone, "registry-name"] }, [{ type: "text", value: name }]);
}

function markRegistryCell(cell, header) {
  const registry = errorRegistry();
  const text = hastText(cell).trim();
  if (!text) return;
  if (/^Code$/i.test(header) && /^-\d+$/.test(text) && registry.codes.has(Number(text))) {
    cell.children = [el("span", { className: ["registry-code"] }, [{ type: "text", value: text }])];
    return;
  }
  const parts = text.split(/,\s*/);
  if (!parts.every((part) => registry.names.has(part))) return;
  cell.children = parts.flatMap((part, index) => [...(index ? [{ type: "text", value: ", " }] : []), registryNameNode(part, registry)]);
}

export function rehypeTables() {
  return (tree) => {
    visit(tree, "element", (node, index, parent) => {
      if (node.tagName !== "table" || !parent || index === undefined) return undefined;
      const headers = [];
      visit(node, "element", (cell) => {
        if (cell.tagName === "th") headers.push(hastText(cell).trim());
      });
      visit(node, "element", (row) => {
        if (row.tagName !== "tr") return;
        let column = 0;
        for (const cell of row.children) {
          if (cell.type !== "element" || cell.tagName !== "td") continue;
          if (column === 0 && headers[0] === "Term") row.properties = { ...row.properties, id: termAnchor(hastText(cell)) };
          cell.properties = { ...cell.properties, dataLabel: headers[column] ?? "" };
          markRegistryCell(cell, headers[column] ?? "");
          cell.children = [el("span", { className: ["cell"] }, cell.children)];
          column += 1;
        }
      });
      parent.children[index] = el("div", { className: headers.length === 2 ? ["table-wrap", "pair"] : ["table-wrap"] }, [node]);
      return SKIP;
    });
  };
}

export function rehypeHeadingLinks() {
  return (tree) => {
    const slugger = new GithubSlugger();
    visit(tree, "element", (node) => {
      if (!/^h[1-6]$/.test(node.tagName)) return;
      node.properties ??= {};
      if (typeof node.properties.id !== "string") node.properties.id = slugger.slug(hastText(node));
      if (/^h[2-4]$/.test(node.tagName)) node.children = [el("a", { className: ["heading-link"], href: `#${node.properties.id}` }, node.children)];
    });
  };
}

const UNIT = /(\d) (%|°C|°F|degC|degF|K|V|mV|A|mA|W|kW|kWh|Wh|s|ms|min|h|Hz|rpm|mm|deg|rad)(?![\w])/g;
const BCP14 = /\b(MUST NOT|SHALL NOT|SHOULD NOT|NOT RECOMMENDED|MUST|SHALL|SHOULD|RECOMMENDED|REQUIRED|MAY|OPTIONAL)\b/g;

export function rehypeTypography() {
  return (tree) => {
    const walk = (node) => {
      if (node.type === "element" && ["code", "pre", "script", "style"].includes(node.tagName)) return;
      if (!node.children) return;
      const next = [];
      for (const child of node.children) {
        if (child.type !== "text") {
          walk(child);
          next.push(child);
          continue;
        }
        const value = child.value.replace(UNIT, "$1\u00a0$2");
        let last = 0;
        for (const match of value.matchAll(BCP14)) {
          if (match.index > last) next.push({ type: "text", value: value.slice(last, match.index) });
          next.push(el("span", { className: ["bcp14"] }, [{ type: "text", value: match[0] }]));
          last = match.index + match[0].length;
        }
        if (last < value.length) next.push({ type: "text", value: value.slice(last) });
      }
      node.children = next;
    };
    walk(tree);
  };
}

function repoPathOf(file) {
  return file.path ? relative(REPO_ROOT, resolve(file.path)).split("\\").join("/") : "";
}

export function specSectionNumber(repoPath, root = REPO_ROOT) {
  const match = /^spec\/([^/]+)\/(.+\.md)$/.exec(repoPath);
  const version = match && versionOfFolder(match[1]);
  if (!version) return null;
  return numberPages(specFiles(version, root)).get(match[2])?.number ?? null;
}

export function rehypeSpecSections() {
  return (tree, file) => {
    const number = specSectionNumber(repoPathOf(file));
    if (!number) return;
    let h2 = 0;
    let h3 = 0;
    for (const node of tree.children) {
      if (node.type !== "element" || !/^h[23]$/.test(node.tagName)) continue;
      if (node.tagName === "h2") {
        h2 += 1;
        h3 = 0;
      } else {
        h3 += 1;
      }
      const label = node.tagName === "h2" ? `${number}.${h2}` : `${number}.${h2}.${h3}`;
      node.children = [el("span", { className: ["secno"] }, [{ type: "text", value: label }]), { type: "text", value: " " }, ...node.children];
    }
  };
}

let glossaryCache = null;

const termSource = (term) => term.replace(/ /g, "\\s+");

export function glossaryTerms(root = REPO_ROOT) {
  if (glossaryCache) return glossaryCache;
  const path = join(root, "spec", "GLOSSARY.md");
  const terms = existsSync(path)
    ? [...readFileSync(path, "utf8").matchAll(/^\|\s*([A-Z][A-Za-z ]+?)\s*\|/gm)].map((row) => row[1]).filter((term) => term !== "Term")
    : [];
  const linked = terms.map((term) => ({ term, href: glossaryHref(term, root), exact: new RegExp(`^${termSource(term)}$`) })).filter((item) => item.href);
  linked.sort((a, b) => b.term.length - a.term.length);
  const pattern = linked.length ? new RegExp(`\\b(${linked.map((item) => termSource(item.term)).join("|")})(?:s|'s)?\\b`, "g") : null;
  glossaryCache = { linked, pattern };
  return glossaryCache;
}

const NO_TERMS = new Set(["a", "code", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "th", "svg", "script", "style", "figure"]);

export function rehypeGlossaryLinks() {
  return (tree, file) => {
    const path = repoPathOf(file);
    if (!path.startsWith("spec/") || /GLOSSARY\.md$/i.test(path)) return;
    const { linked, pattern } = glossaryTerms();
    if (!pattern) return;
    const done = new Set();
    visit(tree, "element", (node) => {
      if (node.tagName !== "a") return;
      const href = String(node.properties?.href ?? "");
      for (const item of linked) if (href === item.href) done.add(item.term);
    });
    const skip = (node) =>
      node.type === "element" &&
      (NO_TERMS.has(node.tagName) || node.properties?.dataLabel === "Term" || classList(node).some((name) => name === "trace" || name === "registry-name"));
    const walk = (node) => {
      if (skip(node) || !node.children) return;
      const next = [];
      for (const child of node.children) {
        if (child.type !== "text") {
          walk(child);
          next.push(child);
          continue;
        }
        let last = 0;
        for (const match of child.value.matchAll(pattern)) {
          const item = linked.find((entry) => entry.exact.test(match[1]));
          if (!item || done.has(item.term)) continue;
          done.add(item.term);
          if (match.index > last) next.push({ type: "text", value: child.value.slice(last, match.index) });
          next.push(el("a", { href: item.href, className: ["term"] }, [{ type: "text", value: match[0] }]));
          last = match.index + match[0].length;
        }
        if (last === 0) next.push(child);
        else if (last < child.value.length) next.push({ type: "text", value: child.value.slice(last) });
      }
      node.children = next;
    };
    walk(tree);
  };
}
