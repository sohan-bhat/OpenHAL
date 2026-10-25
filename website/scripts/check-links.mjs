import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const dist = process.argv[2] ?? "dist";

function pages(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) out.push(...pages(full));
    else if (name.endsWith(".html")) out.push(full);
  }
  return out;
}

function fileFor(path) {
  const clean = decodeURI(path.split("#")[0].split("?")[0]);
  const direct = join(dist, clean);
  if (clean.endsWith("/")) return existsSync(join(direct, "index.html")) ? join(direct, "index.html") : null;
  if (existsSync(direct) && statSync(direct).isFile()) return direct;
  if (existsSync(join(direct, "index.html"))) return join(direct, "index.html");
  return null;
}

const ids = new Map();
function idsOf(file) {
  if (!ids.has(file)) ids.set(file, new Set([...readFileSync(file, "utf8").matchAll(/\sid="([^"]+)"/g)].map((match) => match[1])));
  return ids.get(file);
}

const problems = [];
for (const file of pages(dist)) {
  const html = readFileSync(file, "utf8");
  const route = `/${relative(dist, file).replace(/index\.html$/, "")}`;
  for (const match of html.matchAll(/\shref="([^"]+)"/g)) {
    const href = match[1].replaceAll("&amp;", "&");
    if (/^(https?:|mailto:|data:)/.test(href)) continue;
    const absolute = href.startsWith("#") ? `${route}${href}` : href.startsWith("/") ? href : null;
    if (!absolute) {
      problems.push(`${route} links to a relative path ${href}`);
      continue;
    }
    const target = fileFor(absolute);
    if (!target) {
      problems.push(`${route} links to ${href}, which doesn't exist`);
      continue;
    }
    const hash = absolute.split("#")[1];
    if (hash && target.endsWith(".html") && !idsOf(target).has(decodeURIComponent(hash))) {
      problems.push(`${route} links to ${href}, which has no #${hash}`);
    }
  }
}

if (problems.length) {
  console.log([...new Set(problems)].join("\n"));
  process.exit(1);
}
console.log("Every internal link and anchor resolves.");
