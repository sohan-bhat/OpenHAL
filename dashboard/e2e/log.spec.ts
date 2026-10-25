import { expect, test } from "@playwright/test";
import { AgentClient, hubState, signIn } from "./hub";

test.beforeEach(async ({ context, page }) => {
  await signIn(context);
  page.on("pageerror", (error) => console.log("pageerror", error.message));
  page.on("console", (message) => message.type() === "error" && console.log("console", message.text()));
});

test("a blocked write shows LIMIT_EXCEEDED in the message log", async ({ page }) => {
  await page.goto("/#/devices/desk-fan");
  await expect(page.getByRole("heading", { name: "Message log" })).toBeVisible();
  const agent = await AgentClient.connect("bench-agent", hubState().agentToken);
  const reply = await agent.write("desk-fan", "fan_speed", "150 %");
  agent.close();
  expect(reply.error?.code).toBe(-32010);
  expect(reply.error?.data?.name).toBe("LIMIT_EXCEEDED");

  const error = page.locator('li[data-kind="error"]').filter({ hasText: "LIMIT_EXCEEDED" }).last();
  await expect(error).toBeVisible();
  await expect(error).toContainText("error -32010 LIMIT_EXCEEDED");
  await expect(error).toContainText("fan_speed 150 % exceeds the limit of 100 % (desk-fan.hal.yaml, confirmed by sohan 2026-10-24)");
  await expect(error).toContainText("bench-agent");
  const request = page.locator('li[data-kind="request"]').filter({ hasText: '"150 %"' }).last();
  await expect(request).toContainText("hal/write");
  await expect(request.getByRole("img", { name: "client to hub" })).toBeVisible();
  await expect(error.getByRole("img", { name: "hub to client" })).toBeVisible();
});

test("the log filters by client, device, method and outcome", async ({ page }) => {
  await page.goto("/#/devices/desk-fan");
  const agent = await AgentClient.connect("filter-agent", hubState().agentToken);
  await agent.write("desk-fan", "fan_speed", "150 %");
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
  await expect(log.locator("li").filter({ hasText: "hal/write" })).toHaveCount(0);

  await page.getByRole("combobox", { name: "Device", exact: true }).selectOption("");
  await page.getByRole("combobox", { name: "Method", exact: true }).selectOption("hal/write");
  await expect(log.locator("li").filter({ hasText: "hal/read" })).toHaveCount(0);
});

test("a human write from the Inspector stops at the limit and is decided by the kernel", async ({ page }) => {
  await page.goto("/#/devices/desk-fan");
  const control = page.locator("form.write").filter({ hasText: "fan_speed" });
  const slider = control.getByRole("slider", { name: "fan_speed new value" });
  const number = control.getByRole("spinbutton");
  await expect(slider).toHaveAttribute("max", "100");
  await expect(control.getByText("max 100 %")).toBeVisible();
  await slider.fill("100");
  await expect(number).toHaveValue("100");

  await expect(control.locator("output")).toHaveText(/\d+ %/);
  const now = (await control.locator("output").textContent())!.replace(/[^0-9.]/g, "");
  await number.fill(now);
  await control.getByRole("button", { name: "Set fan_speed" }).click();
  await expect(control.locator(".result")).toContainText("granted");
  await expect(control.locator(".result")).toContainText(`${now} %`);
});
