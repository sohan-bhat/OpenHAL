import { expect, test, type Page } from "@playwright/test";
import { AgentClient, hubState, signIn, tank } from "./hub";

test.beforeEach(async ({ context }) => {
  await signIn(context);
});

const VIEWS = [
  ["Confirmations", "Confirmations"],
  ["Audit log", "Audit log"],
  ["Routines", "Routines"],
  ["Driver writer", "Driver writer"],
  ["Settings", "Settings"],
  ["Devices", "Arduino plant waterer"],
] as const;

async function messages(page: Page) {
  return page.getByRole("region", { name: "Messages" });
}

test("the wordmark and every view link open their view", async ({ page }) => {
  await page.goto("/#/settings");
  await page.getByRole("link", { name: "OpenHAL Inspector, devices" }).click();
  await expect(page.getByRole("heading", { name: "Arduino plant waterer", level: 1 })).toBeVisible();
  for (const [link, heading] of VIEWS) {
    await page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: new RegExp(`^${link}`) }).click();
    await expect(page.getByRole("heading", { name: heading, level: 1 })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Views" }).getByRole("link", { name: new RegExp(`^${link}`) })).toHaveAttribute("aria-current", "page");
  }
});

test("Message log in the header moves focus to the log, and the log hides and shows", async ({ page }) => {
  await page.goto("/#/devices/plant-waterer");
  await page.getByRole("navigation", { name: "Views" }).getByRole("button", { name: "Message log" }).click();
  await expect(page.locator("#log-title")).toBeFocused();
  await page.getByRole("button", { name: "Hide the log" }).click();
  await expect(page.locator("#log-body")).toBeHidden();
  await page.getByRole("button", { name: "Show the log" }).click();
  await expect(page.locator("#log-body")).toBeVisible();
  await page.getByRole("button", { name: "Hide the log" }).click();
  await page.getByRole("navigation", { name: "Views" }).getByRole("button", { name: "Message log" }).click();
  await expect(page.locator("#log-body")).toBeVisible();
  await expect(page.locator("#log-title")).toBeFocused();
});

test("the phone header labels the hub, connection, protocol and conformance", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/devices/plant-waterer");
  const facts = page.locator("dl.hub.narrow");
  await expect(facts).toBeVisible();
  for (const label of ["Hub", "Connection", "Protocol", "Conformance"]) await expect(facts.locator("dt", { hasText: label })).toBeVisible();
  await expect(page.locator("dl.hub.wide")).toBeHidden();
});

test("the log shows readings on request, expands long messages and copies the trace", async ({ page, browserName, context }) => {
  await page.goto("/#/devices/plant-waterer");
  const agent = await AgentClient.connect("chrome-agent", hubState().agentToken);
  await agent.call("hal/action", { device: "plant-waterer", action: "water", args: { duration: { value: 120, unit: "s" } } });
  await tank("drain");
  await page.waitForTimeout(1500);
  await tank("refill");
  await page.waitForTimeout(1500);
  agent.close();
  const log = await messages(page);
  await expect(log.locator("li").filter({ hasText: "chrome-agent" }).first()).toBeVisible();

  const values = log.locator("li").filter({ hasText: "hal/value" });
  const before = await values.count();
  await page.getByLabel("Show hal/value").check();
  await expect.poll(async () => values.count()).toBeGreaterThan(before);
  await page.getByLabel("Show hal/value").uncheck();

  const blocked = log.locator("li").filter({ hasText: "hal/blocked" }).last();
  await blocked.getByRole("button", { name: "Show the whole message" }).click();
  await expect(blocked.getByRole("button", { name: "Show less" })).toHaveAttribute("aria-expanded", "true");

  if (browserName === "chromium") {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.getByRole("button", { name: "Copy as text" }).click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("-> hal/action");
  }

  await page.getByRole("combobox", { name: "Client", exact: true }).selectOption("chrome-agent");
  await page.getByRole("combobox", { name: "Method", exact: true }).selectOption("hal/initialize");
  await page.getByRole("combobox", { name: "Outcome", exact: true }).selectOption("pending");
  await expect(page.getByText("No messages match these filters.")).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page.getByRole("combobox", { name: "Client", exact: true })).toHaveValue("");
  await expect(log.locator("li").first()).toBeVisible();
});

test("older messages load on request once the log holds more than a page", async ({ page }) => {
  test.setTimeout(90_000);
  const agent = await AgentClient.connect("busy-agent", hubState().agentToken);
  for (let index = 0; index < 210; index++) await agent.call("hal/read", { device: "plant-waterer", channel: "tank" });
  agent.close();
  await page.goto("/#/devices/plant-waterer");
  const older = page.getByRole("button", { name: /^Show \d+ older messages$/ });
  await expect(older).toBeVisible();
  const log = await messages(page);
  const shown = await log.locator("li").count();
  await older.click();
  await expect.poll(async () => log.locator("li").count()).toBeGreaterThan(shown);
});

test("a read-only device shows its limits without live controls and says why", async ({ page }) => {
  await page.goto("/#/devices/bench-lamp");
  await expect(page.getByRole("heading", { name: "Bench lamp", level: 1 })).toBeVisible();
  await expect(page.getByText("error -32015 UNVERIFIED_LIMITS").first()).toBeVisible();
  const brightness = page.locator("form.write").filter({ hasText: "brightness" });
  await expect(brightness.getByText("max 80 %")).toBeVisible();
  await expect(page.getByRole("main").getByRole("slider")).toHaveCount(0);
  await expect(page.getByRole("main").getByRole("spinbutton")).toHaveCount(0);
  await expect(page.getByRole("main").getByRole("button", { name: /^Set / })).toHaveCount(0);
});

test("the stop action reads as the device safe state, not as the global STOP", async ({ page }) => {
  await page.goto("/#/devices/plant-waterer");
  const stop = page.locator("form.action").filter({ hasText: "Turn the pump off now." });
  const run = stop.getByRole("button", { name: "Run stop" });
  await expect(run).toBeVisible();
  await expect(run).not.toHaveClass(/primary/);
  await expect(stop).toContainText("is this device's safe state");
});

test("a person runs an action that asks for confirmation each time, and a queued answer links to the queue", async ({ page }) => {
  await page.goto("/#/devices/curing-heater");
  const vent = page.locator("form.action").filter({ hasText: "vent" });
  await expect(vent).toContainText("Your click is that confirmation.");
  await vent.getByRole("button", { name: "Confirm and run vent" }).click();
  await expect(vent.locator(".result")).toContainText("granted");
  await expect(vent.locator(".result")).toContainText("vent ran");

  await page.route("**/v1/action", (route) =>
    route.fulfill({
      json: { status: "needs_confirmation", code: "confirmation_required", message: "Waiting for a human to approve action:vent on curing-heater.", request_id: "queued-by-test" },
    }),
  );
  await vent.getByRole("button", { name: "Confirm and run vent" }).click();
  const link = vent.getByRole("link", { name: "queued-by-test" });
  await expect(link).toBeVisible();
  await link.click();
  await expect(page.getByRole("heading", { name: "Confirmations", level: 1 })).toBeVisible();
});

test("Keep stopped closes the UNLOCK dialog and the hub stays stopped", async ({ page }) => {
  await page.goto("/#/devices/plant-waterer");
  await page.getByRole("button", { name: /STOP/ }).click();
  await page.getByRole("button", { name: "UNLOCK" }).click();
  const dialog = page.getByRole("dialog", { name: "Lift the stop" });
  await dialog.getByRole("button", { name: "Keep stopped" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: "UNLOCK" })).toBeVisible();
  await page.getByRole("button", { name: "UNLOCK" }).click();
  await dialog.getByLabel("Phrase").fill("unlock");
  await dialog.getByRole("button", { name: "Unlock", exact: true }).click();
  await expect(page.getByRole("button", { name: /STOP/ })).toBeVisible();
});

test("the audit log filters, and verifies its hash chain", async ({ page }) => {
  await page.goto("/#/audit");
  const entries = page.locator("li.entry");
  await expect(entries.first()).toBeVisible();
  await page.getByRole("button", { name: "Verify the hash chain" }).click();
  await expect(page.getByText("chain intact")).toBeVisible();
  for (const [label, value] of [["Device", "curing-heater"], ["Status", "blocked"], ["Event", "action"]] as const) {
    const select = page.getByRole("group", { name: "Filter the audit log" }).getByLabel(label);
    await select.selectOption(value);
    await expect.poll(async () => (await entries.allTextContents()).every((text) => text.includes(value === "blocked" ? "blocked" : value))).toBe(true);
    await select.selectOption("");
  }
});

test("a routine is selected, dry run, enabled, disabled and run from its buttons", async ({ page }) => {
  await page.goto("/#/routines");
  await page.getByRole("link", { name: /cure-cycle/ }).click();
  await expect(page.getByRole("heading", { name: "cure-cycle" })).toBeVisible();
  await page.getByRole("link", { name: /water-when-dry/ }).click();
  await page.getByRole("button", { name: "Dry run" }).click();
  await expect(page.getByRole("heading", { name: "Dry run" })).toBeVisible();
  await page.getByRole("button", { name: "Enable" }).click();
  await expect(page.getByRole("button", { name: "Disable" })).toBeVisible();
  await page.getByRole("button", { name: "Disable" }).click();
  await expect(page.getByRole("button", { name: "Enable" })).toBeVisible();
  await page.getByRole("button", { name: "Run now" }).click();
  await expect(page.getByRole("status").filter({ hasText: /^Run \S+ / })).toBeVisible();
});

test("settings create, copy and revoke a token, and hand out a pairing code", async ({ page, browserName, context }) => {
  const name = `token-${browserName}`;
  await page.goto("/#/settings");
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Create token" }).click();
  await expect(page.getByText(`${name} was created.`)).toBeVisible();
  if (browserName === "chromium") {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.getByRole("button", { name: "Copy the token" }).click();
    await expect(page.getByRole("button", { name: "Copied" })).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toMatch(/^ohal_/);
  }
  const row = page.getByRole("row").filter({ hasText: name });
  await row.getByRole("button", { name: `Revoke ${name}` }).click();
  await row.getByRole("button", { name: "Keep" }).click();
  await expect(row.getByRole("button", { name: `Revoke ${name}` })).toBeVisible();
  await row.getByRole("button", { name: `Revoke ${name}` }).click();
  await row.getByRole("button", { name: `Revoke ${name}` }).click();
  await expect(page.getByRole("row").filter({ hasText: name })).toHaveCount(0);
  await page.getByLabel("Show revoked tokens").check();
  await expect(page.getByRole("row").filter({ hasText: name })).toContainText("revoked");

  await page.getByRole("button", { name: "New pairing code" }).click();
  await expect(page.locator(".code code")).toHaveText(/^\d{6}$/);
});

test("a pairing code from Settings pairs a new browser", async ({ page, browser }) => {
  await page.goto("/#/settings");
  await page.getByRole("button", { name: "New pairing code" }).click();
  const code = (await page.locator(".code code").textContent())!.trim();
  const stranger = await browser.newContext();
  const other = await stranger.newPage();
  await other.goto(hubState().url + "/");
  await other.getByLabel("Pairing code").fill(code);
  await other.getByRole("button", { name: "Pair" }).click();
  await expect(other.getByRole("button", { name: /STOP/ })).toBeVisible();
  await stranger.close();
});

test("the offline page tries the hub again on its own", async ({ page }) => {
  let refuse = true;
  await page.route("**/v1/whoami", (route) => (refuse ? route.abort() : route.continue()));
  await page.goto("/");
  await expect(page.getByText("does not answer")).toBeVisible();
  refuse = false;
  await expect(page.getByRole("button", { name: /STOP/ })).toBeVisible({ timeout: 8_000 });
});

test("the driver writer looks for devices, opens the raw data, takes answers and saves a Device File", async ({ page }) => {
  test.setTimeout(60_000);
  await page.route("**/v1/discover", (route) =>
    route.fulfill({ json: { matched: [], unknown: [], errors: [] } }),
  );
  await page.goto("/#/writer");
  await page.getByRole("button", { name: "Look for devices" }).click();
  await expect(page.getByRole("status").filter({ hasText: "0 matched a library file" })).toBeVisible();
  await page.unroute("**/v1/discover");
  await page.reload();
  await page.getByRole("button", { name: "Start the driver writer" }).click();
  await expect(page.getByRole("heading", { name: "Limits interview" })).toBeVisible({ timeout: 20_000 });
  const raw = page.locator("details").filter({ hasText: "shown as data" });
  await raw.locator("summary").click();
  await expect(raw).toHaveAttribute("open", "");
  const first = page.getByRole("button", { name: /^Use suggested value for / }).first();
  const field = page.locator(".question input").first();
  await field.fill("");
  await first.click();
  await expect(field).not.toHaveValue("");
  for (const button of await page.getByRole("button", { name: /^Use suggested value for / }).all()) await button.click();
  await page.getByRole("button", { name: "Confirm these limits" }).click();
  await expect(page.getByText(/added, \d+ removed since the draft/)).toBeVisible();
  await page.route("**/v1/writer/sessions/*/finish", (route) =>
    route.fulfill({ json: { path: "devices/test-board.hal.yaml", device_id: "test-board", writable: false } }),
  );
  await page.locator(".save input").fill("test-board");
  await page.getByRole("button", { name: "Save the Device File" }).click();
  await expect(page.getByText(/^Saved /)).toBeVisible();
  await page.getByRole("link", { name: "All unknown devices" }).click();
  await expect(page.getByRole("heading", { name: "Unknown devices" })).toBeVisible();
});
