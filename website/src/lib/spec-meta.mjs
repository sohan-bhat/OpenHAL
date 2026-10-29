import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

function findRoot() {
  for (const start of [dirname(fileURLToPath(import.meta.url)), process.cwd()]) {
    let dir = start;
    while (true) {
      if (existsSync(join(dir, "pyproject.toml")) && existsSync(join(dir, "website", "package.json"))) return `${dir}/`;
      const up = dirname(dir);
      if (up === dir) break;
      dir = up;
    }
  }
  return fileURLToPath(new URL("../../../", import.meta.url));
}

export const REPO_ROOT = findRoot();

const NUMBER = /^(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

/** Dated names the draft had before ADR 0017, and the version each one became. The site sends their pages to that version. */
export const DATED_NAMES = { "2026-10-24": "0.1" };

/** True when `text` is a version number such as 0.1, the form spec/versions.json and the wire use. */
export function isVersion(text) {
  return typeof text === "string" && NUMBER.test(text);
}

/** Orders two versions as numbers, major first and then minor, so 0.10 sorts after 0.9. */
export function compareVersions(a, b) {
  const [, majorA, minorA] = NUMBER.exec(a);
  const [, majorB, minorB] = NUMBER.exec(b);
  return Number(majorA) - Number(majorB) || Number(minorA) - Number(minorB);
}

/** The version as people see it, such as v0.1. The spec's folder and its URLs use this form too. */
export function versionLabel(version) {
  return `v${version}`;
}

/** The version a spec folder or URL segment such as v0.1 names, or null. */
export function versionOfFolder(name) {
  const version = typeof name === "string" && name.startsWith("v") ? name.slice(1) : "";
  return isVersion(version) ? version : null;
}

/** Where a version's pages live on the site, such as /spec/v0.1/. */
export function specBase(version) {
  return `/spec/${versionLabel(version)}/`;
}

export const SECTION_ORDER = [
  ["introduction", "index", "overview", "readme"],
  ["architecture"],
  ["base-protocol", "basic", "protocol", "lifecycle", "transports", "transport", "messages", "message"],
  ["device-files", "device-file", "devicefile", "device"],
  ["safety", "kernel", "errors", "error-codes", "error"],
  ["drivers", "driver", "conformance"],
  ["routines", "routine"],
  ["security"],
  ["schema", "schema-reference"],
  ["glossary"],
  ["changelog"],
];

const SUB_ORDER = ["overview", "index", "lifecycle", "transports", "transport", "messages", "kernel", "requirements", "error-codes", "errors", "interface", "conformance"];

function normalizeVersion(item) {
  if (typeof item === "string") return { version: item, status: "" };
  if (item && typeof item === "object" && typeof item.version === "string") return { version: item.version, status: String(item.status ?? "") };
  return null;
}

/**
 * The versions spec/versions.json lists, plus any spec/v<version>/ folder it leaves out, newest
 * first. Entries that aren't version numbers, such as the old dates, are left out.
 */
export function parseVersions(json, dirs) {
  const found = new Map();
  let latest = null;
  if (json && typeof json === "object") {
    const list = Array.isArray(json) ? json : (json.versions ?? []);
    for (const item of Array.isArray(list) ? list : []) {
      const entry = normalizeVersion(item);
      if (entry && isVersion(entry.version)) found.set(entry.version, entry);
    }
    if (isVersion(json.latest)) latest = json.latest;
  }
  for (const dir of dirs) {
    const version = versionOfFolder(dir);
    if (version && !found.has(version)) found.set(version, { version, status: "" });
  }
  const versions = [...found.values()].sort((a, b) => compareVersions(b.version, a.version));
  if (!latest && versions.length) latest = versions[0].version;
  return { latest, versions: versions.map((entry) => ({ ...entry, latest: entry.version === latest })) };
}

export function readVersions(root = REPO_ROOT) {
  const specDir = join(root, "spec");
  const dirs = existsSync(specDir) ? readdirSync(specDir).filter((name) => statSync(join(specDir, name)).isDirectory()) : [];
  const file = join(specDir, "versions.json");
  let json = null;
  if (existsSync(file)) {
    try {
      json = JSON.parse(readFileSync(file, "utf8"));
    } catch {
      json = null;
    }
  }
  const parsed = parseVersions(json, dirs);
  parsed.versions = parsed.versions.filter((entry) => existsSync(join(specDir, versionLabel(entry.version))));
  if (parsed.latest && !parsed.versions.some((entry) => entry.version === parsed.latest)) {
    parsed.latest = parsed.versions[0]?.version ?? null;
    parsed.versions = parsed.versions.map((entry) => ({ ...entry, latest: entry.version === parsed.latest }));
  }
  return parsed;
}

function rankOf(part) {
  const name = part.toLowerCase().replace(/\.md$/, "").replace(/^\d+[-_.]?/, "");
  const index = SECTION_ORDER.findIndex((words) => words.includes(name));
  return index === -1 ? SECTION_ORDER.length - 2 + 0.5 : index;
}

function subRank(part) {
  const name = part.toLowerCase().replace(/\.md$/, "").replace(/^\d+[-_.]?/, "");
  const index = SUB_ORDER.indexOf(name);
  return index === -1 ? SUB_ORDER.length : index;
}

export function orderPages(paths) {
  return [...paths].sort((a, b) => {
    const pa = a.split("/");
    const pb = b.split("/");
    const top = rankOf(pa[0]) - rankOf(pb[0]);
    if (top) return top;
    if (pa[0] !== pb[0]) return pa[0].localeCompare(pb[0]);
    const indexA = pa.length === 1 || /^(index|overview|readme)\.md$/i.test(pa[pa.length - 1]) ? -1 : subRank(pa[pa.length - 1]);
    const indexB = pb.length === 1 || /^(index|overview|readme)\.md$/i.test(pb[pb.length - 1]) ? -1 : subRank(pb[pb.length - 1]);
    return indexA - indexB || a.localeCompare(b);
  });
}

export function numberPages(paths) {
  const out = new Map();
  let top = 0;
  let sub = 0;
  let current = "";
  for (const path of orderPages(paths)) {
    const parts = path.split("/");
    const head = parts.length > 1 ? parts[0] : path;
    const isIndex = parts.length > 1 && /^(index|overview|readme)\.md$/i.test(parts[parts.length - 1]);
    if (head !== current || parts.length === 1) {
      top += 1;
      sub = 0;
      current = head;
      if (parts.length === 1 || isIndex) {
        out.set(path, { number: `${top}`, depth: 1 });
        continue;
      }
    }
    if (isIndex) {
      out.set(path, { number: `${top}`, depth: 1 });
      continue;
    }
    sub += 1;
    out.set(path, { number: `${top}.${sub}`, depth: 2 });
  }
  return out;
}

export function slugOf(path) {
  const parts = path.replace(/\.md$/, "").split("/").map((part) => part.toLowerCase().replace(/^\d+[-_.]?/, ""));
  const last = parts[parts.length - 1];
  if (["index", "readme", "overview"].includes(last) && parts.length > 1) parts.pop();
  if (parts.length === 1 && ["index", "readme"].includes(parts[0])) return "";
  return parts.join("/");
}

/** The folder that holds a version's pages, such as spec/v0.1. */
export function specDir(version, root = REPO_ROOT) {
  return join(root, "spec", versionLabel(version));
}

export function specFiles(version, root = REPO_ROOT) {
  const base = specDir(version, root);
  if (!existsSync(base)) return [];
  const out = [];
  const walk = (dir) => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      if (statSync(full).isDirectory()) walk(full);
      else if (name.endsWith(".md")) out.push(relative(base, full).split("\\").join("/"));
    }
  };
  walk(base);
  return orderPages(out);
}

export function termAnchor(term) {
  return `term-${term.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`;
}

export function glossaryHref(term, root = REPO_ROOT) {
  const { latest } = readVersions(root);
  if (!latest) return null;
  const files = specFiles(latest, root);
  const anchor = termAnchor(term);
  const defines = (path) => [...readFileSync(path, "utf8").matchAll(/^\|\s*([^|]+?)\s*\|/gm)].some((row) => termAnchor(row[1]) === anchor);
  const glossary = files.find((path) => /glossary/i.test(path));
  if (glossary) return `${specBase(latest)}${slugOf(glossary)}/#${anchor}`;
  const shared = join(root, "spec", "GLOSSARY.md");
  if (existsSync(shared) && defines(shared)) return `/spec/glossary/#${anchor}`;
  const index = files.find((path) => slugOf(path) === "");
  if (!index) return null;
  return defines(join(specDir(latest, root), index)) ? `${specBase(latest)}#${anchor}` : null;
}
