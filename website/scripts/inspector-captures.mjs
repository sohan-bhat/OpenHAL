import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { readVersions } from "../src/lib/spec-meta.mjs";

const repo = fileURLToPath(new URL("../../", import.meta.url));
const site = fileURLToPath(new URL("../", import.meta.url));
const DEFAULT_PORT = 7420;
const port = Number(process.env.INSPECTOR_PORT ?? DEFAULT_PORT);
const python = process.env.OPENHAL_PYTHON ?? join(repo, ".venv", "bin", "python");
const statePath = join(process.env.TMPDIR ?? tmpdir(), `openhal-inspector-${port}.json`);
const out = join(site, "public", "captures");
const manifest = join(site, "src", "data", "inspector-captures.json");
const BUDGET = 600 * 1024;
const WIDTH = 1440;
const HEIGHT = 900;
const PROTOCOL_VERSION = readVersions(repo).latest;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function free(wanted) {
  return new Promise((resolve) => {
    const probe = createServer();
    probe.once("error", () => resolve(false));
    probe.listen(wanted, "127.0.0.1", () => probe.close(() => resolve(true)));
  });
}

async function checkPort() {
  if (port === 4000) throw new Error("Port 4000 is reserved. Choose another port.");
  if (await free(port)) return;
  const fix = port === DEFAULT_PORT ? "Stop the hub that listens there, then run this again." : "Choose a free INSPECTOR_PORT.";
  throw new Error(`Port ${port} is busy. The captures show the hub at 127.0.0.1:${DEFAULT_PORT}, its default address. ${fix}`);
}

async function waitFor(check, what, tries = 200, gap = 100) {
  for (let attempt = 0; attempt < tries; attempt++) {
    if (await check()) return;
    await sleep(gap);
  }
  throw new Error(`Timed out waiting for ${what}.`);
}

function rpc(token, name) {
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
      const hello = await call("hal/initialize", { protocolVersion: PROTOCOL_VERSION, clientInfo: { name, version: "1.0.0" }, token });
      if (hello.error) throw new Error(hello.error.message);
      socket.send(JSON.stringify({ jsonrpc: "2.0", method: "hal/initialized" }));
    },
    call,
    close: () => socket.close(),
  };
}

async function reading(state, device, channel) {
  const response = await fetch(`${state.url}/v1/devices/${device}`, { headers: { Authorization: `Bearer ${state.humanToken}` } });
  const view = await response.json();
  return view.read?.[channel]?.value;
}

async function show(state, frame) {
  const response = await fetch(`${state.url}/_harness/printer-cam/show/${frame}`, { method: "POST" });
  if (!response.ok) throw new Error(`The simulated camera could not show ${frame}.`);
}

function expectAnswer(answer, check, what) {
  if (!check(answer)) throw new Error(`${what} The hub answered ${JSON.stringify(answer).slice(0, 300)}`);
}

async function scenario(state) {
  await fetch(`${state.url}/_harness/printer/print`, { method: "POST" });
  await show(state, "first-layer");
  await waitFor(async () => (await reading(state, "printer", "state")) === "printing", "the printer to report printing");
  const agent = rpc(state.printToken, "print-watcher");
  await agent.start();
  const look = { device: "printer-cam", channel: "frame" };
  expectAnswer(await agent.call("hal/read", look), (answer) => answer.result?.value?.bytes === 19409, "The first frame was not the first-layer drawing.");
  await agent.call("hal/read", { device: "printer", channel: "bed_target" });
  await sleep(1100);
  const warmer = { device: "printer", channel: "bed_target", value: 70, unit: "degC" };
  expectAnswer(await agent.call("hal/write", warmer), (answer) => answer.result?.status === "done", "The bed did not warm to 70 degC.");
  const hotter = { device: "printer", channel: "extruder_target", value: 300, unit: "degC" };
  expectAnswer(await agent.call("hal/write", hotter), (answer) => answer.error?.data?.name === "LIMIT_EXCEEDED", "The 300 degC nozzle was not refused with LIMIT_EXCEEDED.");
  await show(state, "come-loose");
  expectAnswer(await agent.call("hal/read", look), (answer) => answer.result?.value?.bytes === 23567, "The second frame was not the come-loose drawing.");
  expectAnswer(await agent.call("hal/action", { device: "printer", action: "pause" }), (answer) => answer.result?.status === "done", "The print did not pause.");
  expectAnswer(await agent.call("hal/action", { device: "printer", action: "cancel" }), (answer) => answer.result?.status === "pending", "The cancel did not wait for a person.");
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

async function box(locator, pad = 12) {
  const rect = await locator.boundingBox();
  if (!rect) throw new Error("A capture's element is not on screen.");
  const x = Math.max(0, Math.floor(rect.x - pad));
  const y = Math.max(0, Math.floor(rect.y - pad));
  return { x, y, w: Math.min(WIDTH - x, Math.ceil(rect.width + 2 * pad)), h: Math.min(HEIGHT - y, Math.ceil(rect.height + 2 * pad)) };
}

async function capture(browser, state, theme) {
  const context = await browser.newContext({ viewport: { width: WIDTH, height: HEIGHT }, colorScheme: theme, reducedMotion: "reduce" });
  await context.addCookies([{ name: "openhal_session", value: state.humanToken, url: state.url, httpOnly: true, sameSite: "Strict" }]);
  const page = await context.newPage();
  const settle = async () => {
    await page.mouse.move(1, 1);
    await page.evaluate(() => document.fonts.ready);
    await sleep(600);
  };
  const shots = {};
  const crops = {};
  await page.goto(`${state.url}/#/devices/printer`);
  await page.getByRole("heading", { name: "Klipper 3D printer", level: 1 }).waitFor();
  await page.locator("dl.hub.wide").getByText(`127.0.0.1:${port}`).waitFor();
  await page.locator("main tr").filter({ hasText: "state" }).getByText("paused").waitFor();
  await settle();
  shots.device = await page.screenshot();
  crops.device = await box(page.locator("article.device"), 16);

  await page.goto(`${state.url}/#/devices/printer-cam`);
  await page.getByRole("main").getByRole("img", { name: /^Demo frame from Printer camera/ }).waitFor();
  await settle();
  shots.camera = await page.screenshot();
  crops.camera = await box(page.locator("main section").filter({ has: page.locator("#frames-title") }), 16);

  await page.goto(`${state.url}/#/confirmations`);
  const cancel = page.getByRole("main").getByRole("listitem").filter({ hasText: "asks to run cancel" }).first();
  await cancel.getByRole("combobox", { name: "Show a camera" }).selectOption("printer-cam/frame");
  await cancel.getByRole("img", { name: /^Demo frame from Printer camera/ }).waitFor();
  await page.locator("#pending-title").evaluate((title) => window.scrollTo(0, window.scrollY + title.getBoundingClientRect().top - 130));
  await settle();
  shots.confirmations = await page.screenshot();
  crops.confirmations = await box(cancel, 12);

  await page.goto(`${state.url}/#/devices/printer`);
  await page.getByRole("heading", { name: "Klipper 3D printer", level: 1 }).waitFor();
  await page.getByRole("button", { name: "Message log", exact: true }).click();
  const request = page.locator('li[data-kind="request"]').filter({ hasText: "printer-cam" }).first();
  await request.waitFor();
  await request.evaluate((row) => {
    const scroller = row.closest(".scroller");
    if (scroller) scroller.scrollTop += row.getBoundingClientRect().top - scroller.getBoundingClientRect().top - 8;
  });
  await settle();
  shots.log = await page.screenshot();
  crops.log = await box(page.locator("section.log"), 0);

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.getByRole("button", { name: /STOP/ }).click();
  await page.getByRole("button", { name: "UNLOCK" }).waitFor();
  await settle();
  shots.stopped = await page.screenshot();
  crops.stopped = await box(page.getByRole("status").filter({ hasText: "error -32014 STOPPED" }), 0);
  await page.getByRole("button", { name: "UNLOCK" }).click();
  await page.getByRole("dialog").getByLabel("Phrase").fill("unlock");
  await page.getByRole("dialog").getByRole("button", { name: "Unlock", exact: true }).click();
  await page.getByRole("button", { name: /STOP/ }).waitFor();
  await context.close();
  return { shots, crops };
}

const SHOTS = [
  {
    file: "inspector-device",
    caption: "The printer",
    alt: "The Inspector's device pane for the simulated Klipper 3D printer, paused, with its temperatures and extruder_target limited to 0 °C to 260 °C",
  },
  {
    file: "inspector-camera",
    caption: "The camera frame",
    alt: "The Inspector's camera pane with the latest demo frame, a line drawing of the print knocked over on the bed, image/jpeg, 640 × 480, 24 KB",
  },
  {
    file: "inspector-confirmations",
    caption: "The pending cancel",
    alt: "The Inspector's pending cancel. Because a cancelled print on the Klipper 3D printer can't be resumed, the agent print-watcher's request to run cancel waits for a person, with the camera's frame beside the Approve and run cancel and Reject buttons",
  },
  {
    file: "inspector-log",
    caption: "The message log",
    alt: "The Inspector's message log with hal/read results shown as image/jpeg 640 by 480 descriptions, the hal/write for a nozzle temperature of 300 °C refused with error -32010 LIMIT_EXCEEDED, and the cancel left pending",
  },
  {
    file: "inspector-stopped",
    caption: "Stopped",
    alt: "The Inspector's stop banner, saying every command is refused with error -32014 STOPPED until a person lifts the stop with UNLOCK",
  },
];

async function main() {
  await checkPort();
  if (port !== DEFAULT_PORT) console.warn(`The captures will show the hub at 127.0.0.1:${port}, not its default address.`);
  rmSync(statePath, { force: true });
  const server = spawn(python, ["dashboard/e2e/print_hub.py", "--only-print", "--port", String(port), "--state", statePath], {
    cwd: repo,
    env: { ...process.env, PYTHONPATH: repo },
    stdio: ["ignore", "ignore", "inherit"],
  });
  try {
    await waitFor(() => existsSync(statePath), "the harness state file", 300);
    const state = JSON.parse(readFileSync(statePath, "utf8"));
    await waitFor(async () => (await fetch(`${state.url}/`).catch(() => null))?.ok, "the Inspector to answer", 300);
    await scenario(state);
    const browser = await chromium.launch();
    const raw = {};
    let crops = null;
    for (const theme of ["light", "dark"]) {
      if (theme === "dark") await scenario(state);
      const taken = await capture(browser, state, theme);
      raw[theme] = taken.shots;
      crops ??= taken.crops;
    }
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
    const shots = SHOTS.map((shot) => ({ ...shot, crop: crops[shot.file.replace("inspector-", "")] }));
    const record = { width: WIDTH, height: HEIGHT, quality: Number(quality.toFixed(1)), bytes: total, shots };
    writeFileSync(manifest, `${JSON.stringify(record, null, 2)}\n`);
    console.log(`Wrote ${files.length} captures, ${Math.round(total / 1024)} KB at quality ${quality.toFixed(1)}.`);
  } finally {
    if (server.pid) process.kill(server.pid);
    rmSync(statePath, { force: true });
  }
}

await main();
