#!/usr/bin/env node
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import * as pagefind from "pagefind";

const [dist = "dist", rawBase = ""] = process.argv.slice(2);
const base = rawBase ? `/${rawBase.replace(/^\/+|\/+$/g, "")}` : "";
const BUNDLE = "/pagefind/pagefind.js";

function pages(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return name === "pagefind" ? [] : pages(full);
    return name.endsWith(".html") ? [full] : [];
  });
}

function urlOf(file) {
  const path = relative(dist, file).split(sep).join("/");
  return `/${path.replace(/(^|\/)index\.html$/, "$1")}`;
}

function fail(message) {
  console.error(message);
  process.exit(1);
}

const files = pages(dist);
const indexed = files.filter((file) => readFileSync(file, "utf8").includes("data-pagefind-body"));
if (indexed.length === 0) fail(`No page in ${dist} is marked for search. Run astro build first.`);

const wanted = `data-src="${base}${BUNDLE}"`;
const wrong = files.filter((file) => {
  const html = readFileSync(file, "utf8");
  return html.includes('id="site-search"') && !html.includes(wanted);
});
if (wrong.length) fail(`${wrong.length} pages load the search index from somewhere other than ${base}${BUNDLE}, such as ${urlOf(wrong[0])}.`);

const { index, errors: created } = await pagefind.createIndex({ forceLanguage: "en" });
if (!index) fail(`Pagefind could not start. ${created.join(" ")}`);
for (const file of indexed) {
  const { errors } = await index.addHTMLFile({ url: urlOf(file), content: readFileSync(file, "utf8") });
  if (errors.length) fail(`${urlOf(file)} ${errors.join(" ")}`);
}
const { errors: written } = await index.writeFiles({ outputPath: join(dist, "pagefind") });
await pagefind.close();
if (written.length) fail(written.join(" "));
if (!existsSync(join(dist, "pagefind", "pagefind.js"))) fail("Pagefind wrote no pagefind.js.");
console.log(`Indexed ${indexed.length} of ${files.length} pages for search at ${base}${BUNDLE}`);
