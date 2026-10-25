import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { chromium } from "playwright";

const [bin, paths = "/", form = "mobile"] = process.argv.slice(2);
const base = process.env.OPENHAL_PREVIEW_URL ?? "http://127.0.0.1:4322";
const out = ".lighthouse";
mkdirSync(out, { recursive: true });
const chrome = chromium.executablePath();

for (const path of paths.split(",")) {
  const name = path.replace(/^\/|\/$/g, "").replaceAll("/", "-") || "home";
  const file = `${out}/${name}-${form}.json`;
  const args = [
    `${base}${path}`,
    "--quiet",
    "--output=json",
    `--output-path=${file}`,
    "--only-categories=performance,accessibility,best-practices,seo",
    `--chrome-flags=--headless=new --no-sandbox`,
  ];
  if (form === "desktop") args.push("--preset=desktop");
  execFileSync(bin, args, { env: { ...process.env, CHROME_PATH: chrome }, stdio: ["ignore", "ignore", "inherit"] });
  const report = JSON.parse(readFileSync(file, "utf8"));
  const scores = Object.fromEntries(Object.entries(report.categories).map(([key, value]) => [key, Math.round(value.score * 100)]));
  console.log(`${path} ${form} ${JSON.stringify(scores)}`);
}
