import { expect, test } from "@playwright/test";
import { AgentClient, hubState, signIn } from "./hub";

test.beforeEach(async ({ context, page }) => {
  await signIn(context);
  page.on("pageerror", (error) => console.log("pageerror", error.message));
});

const seconds = (value: number) => ({ value, unit: "s" });

test("a blocked command shows LIMIT_EXCEEDED in the message log", async ({ page }) => {
  await page.goto("/#/devices/plant-waterer");
  await expect(page.getByRole("heading", { name: "Message log" })).toBeVisible();
  const agent = await AgentClient.connect("bench-agent", hubState().agentToken);
  const reply = await agent.call("hal/action", { device: "plant-waterer", action: "water", args: { duration: seconds(120) } });
  agent.close();
  expect(reply.error?.code).toBe(-32010);
  expect(reply.error?.data?.name).toBe("LIMIT_EXCEEDED");

  const error = page.locator('li[data-kind="error"]').filter({ hasText: "LIMIT_EXCEEDED" }).last();
  await expect(error).toBeVisible();
  await expect(error).toContainText("error -32010 LIMIT_EXCEEDED");
  await expect(error).toContainText("water duration 120 s exceeds the limit of 30 s (plant-waterer.hal.yaml, confirmed by sohan");
  await expect(error).toContainText("bench-agent");
  const request = page.locator('li[data-kind="request"]').filter({ hasText: '"value": 120' }).last();
  await expect(request).toContainText("hal/action");
  await expect(request.getByRole("img", { name: "client to hub" })).toBeVisible();
  await expect(error.getByRole("img", { name: "hub to client" })).toBeVisible();
});

test("a number sent as one string is refused with UNIT_INVALID", async ({ page }) => {
  await page.goto("/#/devices/plant-waterer");
  const agent = await AgentClient.connect("string-agent", hubState().agentToken);
  const reply = await agent.call("hal/action", { device: "plant-waterer", action: "water", args: { duration: "20 s" } });
  agent.close();
  expect(reply.error?.data?.name).toBe("UNIT_INVALID");
  await expect(page.locator('li[data-kind="error"]').filter({ hasText: "error -32023 UNIT_INVALID" }).last()).toBeVisible();
});

test("the log filters by client, device, method and outcome", async ({ page }) => {
  await page.goto("/#/devices/plant-waterer");
  const agent = await AgentClient.connect("filter-agent", hubState().agentToken);
  await agent.call("hal/action", { device: "plant-waterer", action: "water", args: { duration: seconds(120) } });
  await agent.call("hal/read", { device: "curing-heater", channel: "temperature" });
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
  await page.getByRole("combobox", { name: "Device", exact: true }).selectOption("curing-heater");
  await expect(log.locator("li").filter({ hasText: "hal/read" }).first()).toBeVisible();
  await expect(log.locator("li").filter({ hasText: "hal/action" })).toHaveCount(0);

  await page.getByRole("combobox", { name: "Device", exact: true }).selectOption("");
  await page.getByRole("combobox", { name: "Method", exact: true }).selectOption("hal/action");
  await expect(log.locator("li").filter({ hasText: "hal/read" })).toHaveCount(0);
});

test("a change from the Inspector stops at the limit and is decided by the kernel", async ({ page }) => {
  await page.goto("/#/devices/curing-heater");
  const control = page.locator("form.write").filter({ hasText: "power" });
  const slider = control.getByRole("slider", { name: "power new value" });
  const number = control.getByRole("spinbutton");
  await expect(slider).toHaveAttribute("max", "60");
  await expect(control.getByText("max 60 W")).toBeVisible();
  await slider.fill("60");
  await expect(number).toHaveValue("60");

  await expect(control.locator("output")).toHaveText(/\d+ W/);
  const now = (await control.locator("output").textContent())!.replace(/[^0-9.]/g, "");
  await number.fill(now);
  await control.getByRole("button", { name: "Set power" }).click();
  await expect(control.locator(".result")).toContainText("granted");
  await expect(control.locator(".result")).toContainText(`${now} W`);
});

test("an action argument stops at its limit", async ({ page }) => {
  await page.goto("/#/devices/plant-waterer");
  const action = page.locator("form.action").filter({ hasText: "Run the pump" });
  const slider = action.getByRole("slider", { name: "duration for water, slider" });
  await expect(slider).toHaveAttribute("max", "30");
  await expect(action.getByText("max 30 s")).toBeVisible();
  await slider.fill("30");
  await expect(action.getByRole("spinbutton", { name: "duration in s" })).toHaveValue("30");
});
