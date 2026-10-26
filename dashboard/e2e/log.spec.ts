import { expect, test } from "@playwright/test";
import { AgentClient, hubState, printAgain, printerError, signIn } from "./hub";

test.beforeEach(async ({ context, page }) => {
  await signIn(context);
  page.on("pageerror", (error) => console.log("pageerror", error.message));
});

test("a nozzle over the limit shows LIMIT_EXCEEDED in the message log", async ({ page }) => {
  await page.goto("/#/devices/printer");
  await expect(page.getByRole("heading", { name: "Message log" })).toBeVisible();
  const agent = await AgentClient.connect("print-watcher", hubState().printToken);
  const reply = await agent.write("printer", "extruder_target", 300, "degC");
  agent.close();
  expect(reply.error?.code).toBe(-32010);
  expect(reply.error?.data?.name).toBe("LIMIT_EXCEEDED");

  const error = page.locator('li[data-kind="error"]').filter({ hasText: "LIMIT_EXCEEDED" }).last();
  await expect(error).toBeVisible();
  await expect(error).toContainText("error -32010 LIMIT_EXCEEDED");
  await expect(error).toContainText("extruder_target 300 degC exceeds the limit of 260 degC (printer.hal.yaml, confirmed by owner");
  await expect(error).toContainText("print-watcher");
  const request = page.locator('li[data-kind="request"]').filter({ hasText: '"value": 300' }).last();
  await expect(request).toContainText("hal/write");
  await expect(request.getByRole("img", { name: "client to hub" })).toBeVisible();
  await expect(error.getByRole("img", { name: "hub to client" })).toBeVisible();
});

test("a printer in its error state shows INTERLOCK_BLOCKED with the device file's reason", async ({ page }) => {
  await page.goto("/#/devices/printer");
  await printerError();
  try {
    await expect(page.locator("main tr").filter({ hasText: "state" }).locator("output")).toHaveText("error");
    const agent = await AgentClient.connect("interlock-agent", hubState().printToken);
    const reply = await agent.write("printer", "extruder_target", 200, "degC");
    agent.close();
    expect(reply.error?.data?.name).toBe("INTERLOCK_BLOCKED");
    const error = page.locator('li[data-kind="error"]').filter({ hasText: "INTERLOCK_BLOCKED" }).last();
    await expect(error).toContainText("error -32012 INTERLOCK_BLOCKED");
    await expect(error).toContainText("Clear the printer error before heating.");
  } finally {
    await printAgain();
  }
  await expect(page.locator("main tr").filter({ hasText: "state" }).locator("output")).toHaveText("printing");
});

test("a number sent as one string is refused with UNIT_INVALID", async ({ page }) => {
  await page.goto("/#/devices/printer");
  const agent = await AgentClient.connect("string-agent", hubState().printToken);
  const reply = await agent.call("hal/write", { device: "printer", channel: "bed_target", value: "70 degC" });
  agent.close();
  expect(reply.error?.data?.name).toBe("UNIT_INVALID");
  await expect(page.locator('li[data-kind="error"]').filter({ hasText: "error -32023 UNIT_INVALID" }).last()).toBeVisible();
});

test("the log filters by client, device, method and outcome", async ({ page }) => {
  await page.goto("/#/devices/printer");
  const agent = await AgentClient.connect("filter-agent", hubState().printToken);
  await agent.write("printer", "extruder_target", 300, "degC");
  await agent.call("hal/read", { device: "printer-cam", channel: "frame" });
  agent.close();

  const log = page.getByRole("region", { name: "Messages" });
  await expect(log.locator("li").filter({ hasText: "filter-agent" }).first()).toBeVisible();
  await page.getByRole("combobox", { name: "Client", exact: true }).selectOption("filter-agent");
  await page.getByRole("combobox", { name: "Outcome", exact: true }).selectOption("error");
  const rows = log.locator("li");
  await expect(rows.first()).toBeVisible();
  for (const text of await rows.allTextContents()) expect(text).toContain("filter-agent");
  await expect(log.locator('li[data-kind="error"]').first()).toContainText("LIMIT_EXCEEDED");

  await page.getByRole("combobox", { name: "Outcome", exact: true }).selectOption("");
  await page.getByRole("combobox", { name: "Device", exact: true }).selectOption("printer-cam");
  await expect(log.locator("li").filter({ hasText: "hal/read" }).first()).toBeVisible();
  await expect(log.locator("li").filter({ hasText: "hal/write" })).toHaveCount(0);

  await page.getByRole("combobox", { name: "Device", exact: true }).selectOption("");
  await page.getByRole("combobox", { name: "Method", exact: true }).selectOption("hal/write");
  await expect(log.locator("li").filter({ hasText: "hal/read" })).toHaveCount(0);
});

test("a change from the Inspector stops at the limit and is decided by the kernel", async ({ page }) => {
  await page.goto("/#/devices/curing-heater");
  const control = page.locator("form.write").filter({ hasText: "power" });
  const slider = control.getByRole("slider", { name: "power new value" });
  const number = control.getByRole("spinbutton");
  await expect(slider).toHaveAttribute("max", "60");
  await expect(control.getByText("max 60 W")).toBeVisible();
  await expect(control.getByText("min 0 W")).toBeVisible();
  await expect(control.locator(".ticks .tick")).toHaveText("30 W");
  await slider.fill("60");
  await expect(number).toHaveValue("60");

  await expect(control.locator("output")).toHaveText(/\d+ W/);
  const now = (await control.locator("output").textContent())!.replace(/[^0-9.]/g, "");
  await number.fill(now);
  await control.getByRole("button", { name: "Set power" }).click();
  await expect(control.locator(".result")).toContainText("granted");
  await expect(control.locator(".result")).toContainText(`${now} W`);
});

test("the printer's targets stop at the limits its device file confirms", async ({ page }) => {
  await page.goto("/#/devices/printer");
  const nozzle = page.locator("form.write").filter({ hasText: "extruder_target" });
  await expect(nozzle.getByRole("slider", { name: "extruder_target new value" })).toHaveAttribute("max", "260");
  await expect(nozzle.getByText("max 260 °C")).toBeVisible();
  const bed = page.locator("form.write").filter({ hasText: "bed_target" });
  await expect(bed.getByRole("slider", { name: "bed_target new value" })).toHaveAttribute("max", "110");
  await expect(page.locator("form.action").filter({ hasText: "cancel" })).toContainText("confirmation required each time");
});

test("an action argument stops at its limit", async ({ page }) => {
  await page.goto("/#/devices/plant-waterer");
  const action = page.locator("form.action").filter({ hasText: "Run the pump" });
  const slider = action.getByRole("slider", { name: "duration for water, slider" });
  await expect(slider).toHaveAttribute("max", "30");
  await expect(action.getByText("max 30 s")).toBeVisible();
  await expect(action.getByText("min 1 s")).toBeVisible();
  await expect(action.locator(".ticks .tick")).toHaveText("16 s");
  await expect(action.getByRole("spinbutton", { name: "duration in s" })).toHaveValue("1");
  await expect(action.getByText("at most 3 runs per 1 h")).toBeVisible();
  await expect(action.getByText("pump can't run while tank is empty")).toBeVisible();
  await expect(page.getByText("5 of 5 devices are simulated.")).toBeVisible();
  await slider.fill("30");
  await expect(action.getByRole("spinbutton", { name: "duration in s" })).toHaveValue("30");
});
