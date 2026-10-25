import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { chromium } from "playwright";

const [bin, paths = "/", forms = "mobile", out = ".lighthouse"] = process.argv.slice(2);
if (!bin) {
  console.error("Usage: node scripts/lighthouse.mjs LIGHTHOUSE_BIN [paths] [mobile,desktop] [out]");
  process.exit(2);
}
const base = process.env.OPENHAL_PREVIEW_URL ?? "http://127.0.0.1:4322";
if (new URL(base).port === "4000") throw new Error("Port 4000 is reserved. Choose another port.");
mkdirSync(out, { recursive: true });
const chrome = chromium.executablePath();

for (const path of paths.split(",")) {
  for (const form of forms.split(",")) {
    const name = path.replace(/^\/|\/$/g, "").replaceAll("/", "-") || "home";
    const file = `${out}/${name}-${form}.json`;
    const args = [
      `${base}${path}`,
      "--quiet",
      "--output=json",
      `--output-path=${file}`,
      "--only-categories=performance,accessibility,best-practices,seo",
      "--chrome-flags=--headless=new --no-sandbox",
    ];
    if (form === "desktop") args.push("--preset=desktop");
    execFileSync(bin, args, { env: { ...process.env, CHROME_PATH: chrome }, stdio: ["ignore", "ignore", "inherit"] });
    const report = JSON.parse(readFileSync(file, "utf8"));
    const scores = Object.fromEntries(Object.entries(report.categories).map(([key, value]) => [key, Math.round(value.score * 100)]));
    const misses = Object.values(report.categories).flatMap((category) =>
      category.auditRefs
        .filter((ref) => ref.weight > 0 && report.audits[ref.id].score !== null && report.audits[ref.id].score < 1)
        .map((ref) => `${ref.id} ${report.audits[ref.id].displayValue ?? report.audits[ref.id].score}`),
    );
    console.log(`${path} ${form} ${JSON.stringify(scores)}${misses.length ? ` misses ${misses.join("; ")}` : ""}`);
  }
}
