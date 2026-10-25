import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const repo = fileURLToPath(new URL("../../", import.meta.url));
const site = fileURLToPath(new URL("../", import.meta.url));
const port = Number(process.env.INSPECTOR_PORT ?? 7433);
const python = process.env.OPENHAL_PYTHON ?? join(repo, ".venv", "bin", "python");
const statePath = join(process.env.TMPDIR ?? tmpdir(), `openhal-inspector-${port}.json`);
const out = join(site, "public", "captures");
const manifest = join(site, "src", "data", "inspector-captures.json");
const BUDGET = 600 * 1024;
const WIDTH = 1440;
const HEIGHT = 900;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitFor(check, what, tries = 200, gap = 100) {
  for (let attempt = 0; attempt < tries; attempt++) {
    if (await check()) return;
    await sleep(gap);
  }
  throw new Error(`Timed out waiting for ${what}.`);
}

function rpc(token) {
  const socket = new WebSocket(`ws://127.0.0.1:${port}/rpc`);
  const waiting = new Map();
  let next = 1;
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data));
    if (message.id !== undefined && waiting.has(message.id)) {
      waiting.get(message.id)(message);
      waiting.delete(message.id);
    }
  });
  const call = (method, params = {}) =>
    new Promise((resolve) => {
      const id = next++;
      waiting.set(id, resolve);
      socket.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
    });
  const opened = new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", () => reject(new Error("The /rpc WebSocket did not open.")), { once: true });
  });
  return {
    async start() {
      await opened;
      const hello = await call("hal/initialize", { protocolVersion: "2026-10-24", clientInfo: { name: "bench-agent", version: "1.0.0" }, token });
      if (hello.error) throw new Error(hello.error.message);
      socket.send(JSON.stringify({ jsonrpc: "2.0", method: "hal/initialized" }));
    },
    call,
    close: () => socket.close(),
  };
}

async function reading(state, channel) {
  const response = await fetch(`${state.url}/v1/devices/plant-waterer`, { headers: { Authorization: `Bearer ${state.humanToken}` } });
  const view = await response.json();
  return view.read?.[channel]?.value;
}

async function scenario(state) {
  const water = (seconds) => ({ device: "plant-waterer", action: "water", args: { duration: { value: seconds, unit: "s" } } });
  await waitFor(async () => (await reading(state, "soil_moisture")) !== undefined, "the first soil reading");
  const agent = rpc(state.agentToken);
  await agent.start();
  const tooLong = await agent.call("hal/action", water(120));
  if (tooLong.error?.data?.name !== "LIMIT_EXCEEDED") throw new Error("The 120 s watering was not refused with LIMIT_EXCEEDED.");
  await fetch(`${state.url}/_harness/plant-waterer/drain`, { method: "POST" });
  await waitFor(async () => (await reading(state, "tank")) === "empty", "an empty tank");
  const empty = await agent.call("hal/action", water(20));
  if (empty.error?.data?.name !== "INTERLOCK_BLOCKED") throw new Error("The empty tank did not block the pump.");
  await fetch(`${state.url}/_harness/plant-waterer/refill`, { method: "POST" });
  await waitFor(async () => (await reading(state, "tank")) === "ok", "a refilled tank");
  const watered = await agent.call("hal/action", water(20));
  if (watered.result?.status !== "done") throw new Error("The 20 s watering did not run.");
  agent.close();
}

async function webp(page, png, quality) {
  return page.evaluate(
    async ({ data, quality }) => {
      const image = new Image();
      image.src = `data:image/png;base64,${data}`;
      await image.decode();
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      canvas.getContext("2d").drawImage(image, 0, 0);
      return canvas.toDataURL("image/webp", quality).split(",")[1];
    },
    { data: png.toString("base64"), quality },
  );
}

async function capture(browser, state, theme) {
  const context = await browser.newContext({ viewport: { width: WIDTH, height: HEIGHT }, colorScheme: theme, reducedMotion: "reduce" });
  await context.addCookies([{ name: "openhal_session", value: state.humanToken, url: state.url, httpOnly: true, sameSite: "Strict" }]);
  const page = await context.newPage();
  const settle = async () => {
    await page.evaluate(() => document.fonts.ready);
    await sleep(600);
  };
  const shots = {};
  await page.goto(`${state.url}/#/devices/plant-waterer`);
  await page.getByRole("heading", { name: "Arduino plant waterer", level: 1 }).waitFor();
  await settle();
  shots.device = await page.screenshot();
  await page.getByRole("button", { name: "Message log", exact: true }).click();
  const request = page.locator('li[data-kind="request"]').filter({ hasText: "plant-waterer" }).first();
  await request.waitFor();
  await request.evaluate((row) => {
    const scroller = row.closest(".scroller");
    if (scroller) scroller.scrollTop += row.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 8;
  });
  await settle();
  shots.log = await page.screenshot();
  await page.goto(`${state.url}/#/devices/plant-waterer`);
  await page.getByRole("button", { name: /STOP/ }).click();
  await page.getByRole("button", { name: "UNLOCK" }).waitFor();
  await settle();
  shots.stopped = await page.screenshot();
  await page.getByRole("button", { name: "UNLOCK" }).click();
  await page.getByRole("dialog").getByLabel("Phrase").fill("unlock");
  await page.getByRole("dialog").getByRole("button", { name: "Unlock", exact: true }).click();
  await page.getByRole("button", { name: /STOP/ }).waitFor();
  await context.close();
  return shots;
}

async function main() {
  rmSync(statePath, { force: true });
  const server = spawn(python, ["-m", "tests.inspector.serve", "--port", String(port), "--state", statePath], { cwd: repo, stdio: ["ignore", "ignore", "inherit"] });
  try {
    await waitFor(() => existsSync(statePath), "the harness state file", 300);
    const state = JSON.parse(readFileSync(statePath, "utf8"));
    await waitFor(async () => (await fetch(`${state.url}/`).catch(() => null))?.ok, "the Inspector to answer", 300);
    await scenario(state);
    const browser = await chromium.launch();
    const raw = {};
    for (const theme of ["light", "dark"]) raw[theme] = await capture(browser, state, theme);
    const page = await browser.newPage();
    mkdirSync(out, { recursive: true });
    let quality = 0.8;
    let files = [];
    while (true) {
      files = [];
      for (const theme of ["light", "dark"]) {
        for (const [name, png] of Object.entries(raw[theme])) {
          files.push({ path: join(out, `inspector-${name}-${theme}.webp`), data: Buffer.from(await webp(page, png, quality), "base64") });
        }
      }
      const total = files.reduce((sum, file) => sum + file.data.length, 0);
      if (total <= BUDGET || quality <= 0.3) break;
      quality -= 0.1;
    }
    for (const file of files) writeFileSync(file.path, file.data);
    await browser.close();
    const total = files.reduce((sum, file) => sum + file.data.length, 0);
    writeFileSync(manifest, `${JSON.stringify({ width: WIDTH, height: HEIGHT, quality: Number(quality.toFixed(1)), bytes: total }, null, 2)}\n`);
    console.log(`Wrote ${files.length} captures, ${Math.round(total / 1024)} KB at quality ${quality.toFixed(1)}.`);
  } finally {
    if (server.pid) process.kill(server.pid);
    rmSync(statePath, { force: true });
  }
}

await main();
