#!/usr/bin/env node
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import * as pagefind from "pagefind";

const BUNDLE = "/pagefind/pagefind.js";

function pages(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) return name === "pagefind" ? [] : pages(full);
    return name.endsWith(".html") ? [full] : [];
  });
}

function fail(message) {
  console.error(message);
  process.exit(1);
}

/**
 * The page as the index reads it. Code blocks, YAML, message traces and the text inside form
 * fields, such as the Playground's device file editor, are left out, so a result's excerpt is
 * always prose. The page itself is served unchanged.
 */
export function forIndex(html) {
  return html
    .replace(/<(pre|textarea)(?=[\s>])/g, '<$1 data-pagefind-ignore="all"')
    .replace(/<(figure|div)(?=\s[^>]*?\bclass="(?:[^"]*\s)?(?:code-block|trace-figure|trace)(?:\s[^"]*)?")/g, '<$1 data-pagefind-ignore="all"');
}

async function main(dist, rawBase) {
  const base = rawBase ? `/${rawBase.replace(/^\/+|\/+$/g, "")}` : "";
  const urlOf = (file) => `/${relative(dist, file).split(sep).join("/").replace(/(^|\/)index\.html$/, "$1")}`;
  const files = pages(dist);
  const indexed = files.filter((file) => readFileSync(file, "utf8").includes("data-pagefind-body"));
  if (indexed.length === 0) fail(`No page in ${dist} is marked for search. Run astro build first.`);

  const scripts = existsSync(join(dist, "_astro")) ? readdirSync(join(dist, "_astro")).filter((name) => name.endsWith(".js")).map((name) => join(dist, "_astro", name)) : [];
  const loaders = scripts.flatMap((file) => [...readFileSync(file, "utf8").matchAll(/[`"]((?:\/[\w.-]+)*)\/pagefind\//g)].map((match) => ({ file, prefix: match[1] })));
  if (loaders.length === 0) fail(`No script in ${dist} loads the search index. Run astro build first.`);
  const wrong = loaders.filter((loader) => loader.prefix !== base);
  if (wrong.length) fail(`${wrong.length} scripts load the search index from somewhere other than ${base}/pagefind/, such as ${relative(dist, wrong[0].file)}.`);

  const { index, errors: created } = await pagefind.createIndex({ forceLanguage: "en" });
  if (!index) fail(`Pagefind could not start. ${created.join(" ")}`);
  for (const file of indexed) {
    const { errors } = await index.addHTMLFile({ url: urlOf(file), content: forIndex(readFileSync(file, "utf8")) });
    if (errors.length) fail(`${urlOf(file)} ${errors.join(" ")}`);
  }
  const { errors: written } = await index.writeFiles({ outputPath: join(dist, "pagefind") });
  await pagefind.close();
  if (written.length) fail(written.join(" "));
  if (!existsSync(join(dist, "pagefind", "pagefind.js"))) fail("Pagefind wrote no pagefind.js.");
  console.log(`Indexed ${indexed.length} of ${files.length} pages for search at ${base}${BUNDLE}`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const [dist = "dist", rawBase = ""] = process.argv.slice(2);
  await main(dist, rawBase);
}
