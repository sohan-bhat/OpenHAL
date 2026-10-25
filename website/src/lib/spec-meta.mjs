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

const DATE = /^\d{4}-\d{2}-\d{2}$/;

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
  if (item && typeof item === "object") {
    const version = item.version ?? item.date ?? item.id ?? item.name;
    if (typeof version === "string") return { version, status: String(item.status ?? item.state ?? "") };
  }
  return null;
}

export function parseVersions(json, dirs) {
  const found = new Map();
  let latest = null;
  if (json && typeof json === "object") {
    const list = Array.isArray(json) ? json : (json.versions ?? []);
    for (const item of Array.isArray(list) ? list : Object.keys(list)) {
      const entry = normalizeVersion(item);
      if (entry && DATE.test(entry.version)) found.set(entry.version, entry);
    }
    if (typeof json.latest === "string" && DATE.test(json.latest)) latest = json.latest;
  }
  for (const dir of dirs) if (DATE.test(dir) && !found.has(dir)) found.set(dir, { version: dir, status: "" });
  const versions = [...found.values()].sort((a, b) => b.version.localeCompare(a.version));
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
  parsed.versions = parsed.versions.filter((entry) => existsSync(join(specDir, entry.version)));
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

export function slugOf(path) {
  const parts = path.replace(/\.md$/, "").split("/").map((part) => part.toLowerCase().replace(/^\d+[-_.]?/, ""));
  const last = parts[parts.length - 1];
  if (["index", "readme", "overview"].includes(last) && parts.length > 1) parts.pop();
  if (parts.length === 1 && ["index", "readme"].includes(parts[0])) return "";
  return parts.join("/");
}

export function specFiles(version, root = REPO_ROOT) {
  const base = join(root, "spec", version);
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

export function glossaryHref(term) {
  const { latest } = readVersions();
  if (!latest) return null;
  const file = specFiles(latest).find((path) => /glossary/i.test(path));
  if (!file) return null;
  const anchor = term.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `/spec/${latest}/${slugOf(file)}/#${anchor}`;
}
