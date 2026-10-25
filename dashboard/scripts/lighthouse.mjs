import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { chromium } from "@playwright/test";

const [bin, stateFile, views = "#/devices/plant-waterer", forms = "mobile,desktop", out = ".lighthouse"] = process.argv.slice(2);
if (!bin || !stateFile) {
  console.error("Usage: node scripts/lighthouse.mjs LIGHTHOUSE_BIN STATE_JSON [views] [mobile,desktop] [out]");
  process.exit(2);
}
const state = JSON.parse(readFileSync(stateFile, "utf8"));
if (new URL(state.url).port === "4000") throw new Error("Port 4000 is reserved. Choose another port.");
mkdirSync(out, { recursive: true });
const chrome = chromium.executablePath();
const headers = JSON.stringify({ Cookie: `openhal_session=${state.humanToken}` });

for (const view of views.split(",")) {
  for (const form of forms.split(",")) {
    const name = view.replace(/^#\/?/, "").replaceAll("/", "-") || "home";
    const file = `${out}/inspector-${name}-${form}.json`;
    const args = [
      `${state.url}/${view}`,
      "--quiet",
      "--output=json",
      `--output-path=${file}`,
      "--only-categories=performance,accessibility,best-practices,seo",
      "--chrome-flags=--headless=new --no-sandbox",
      `--extra-headers=${headers}`,
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
    console.log(`${view} ${form} ${JSON.stringify(scores)}${misses.length ? ` misses ${misses.join("; ")}` : ""}`);
  }
}
