import { expect, test } from "@playwright/test";

test.describe("catalog filters", () => {
  test("each driver filter narrows the table and an impossible search says so", async ({ page }) => {
    await page.goto("/drivers/");
    const all = await page.locator("[data-driver]").count();
    for (const [label, option] of [["tier", "Tier 2"], ["conformance", "core"], ["hazard", "high"]] as const) {
      const select = page.locator(`select[name="${label}"]`);
      await select.selectOption({ label: option });
      const shown = await page.locator("[data-driver]:visible").count();
      expect(shown, label).toBeGreaterThan(0);
      expect(shown, label).toBeLessThan(all);
      await select.selectOption("");
    }
    await page.getByLabel("Filter", { exact: true }).fill("scpi");
    await expect(page.locator("[data-driver]:visible")).toHaveCount(1);
    await page.getByLabel("Filter", { exact: true }).fill("no such driver");
    await expect(page.locator("[data-empty]")).toBeVisible();
    await expect(page.locator("[data-shown]")).toHaveText(`0 of ${all} drivers.`);
  });

  test("a filter is drawn only when it has more than one value", async ({ page }) => {
    await page.goto("/drivers/");
    for (const select of await page.locator("[data-filters] select").all()) {
      expect(await select.locator("option").count()).toBeGreaterThan(2);
    }
  });
});

test.describe("playground controls", () => {
  test("the example picker opens on the printer and loads the desk fan too", async ({ page }) => {
    await page.goto("/spec/playground/");
    await page.locator("summary", { hasText: "Build your own request" }).click();
    const picker = page.locator(".example select");
    await expect(picker).toHaveValue(/printer/);
    await picker.selectOption({ label: "spec/examples/desk-fan-confirmed.hal.yaml" });
    await expect(page.getByLabel("Device file YAML")).toHaveValue(/fan_speed/);
    await expect(page.getByRole("button", { name: "Send hal/write" })).toBeEnabled();
  });

  test("the client picker changes who sends, and a read-only agent is refused", async ({ page }) => {
    await page.goto("/spec/playground/");
    await page.locator("summary", { hasText: "Build your own request" }).click();
    const as = page.locator(".request select").nth(0);
    const options = await as.locator("option").allTextContents();
    expect(options.length).toBeGreaterThan(1);
    const reader = options.find((option) => /read/i.test(option))!;
    await as.selectOption({ label: reader });
    await page.getByLabel("Value").fill("240 degC");
    await page.getByRole("button", { name: /^Send hal\// }).click();
    await expect(page.locator(".exchanges > li").first()).toContainText("error");
  });

  test("Stop refuses every request until a person types unlock", async ({ page }) => {
    await page.goto("/spec/playground/");
    await page.getByRole("button", { name: "Stop", exact: true }).click();
    await expect(page.locator(".stop-area .status.blocked")).toHaveText("stopped");
    await page.getByRole("button", { name: "Pause the print" }).click();
    await expect(page.locator(".exchanges > li").first()).toContainText("STOPPED");
    await page.getByLabel("Type unlock to lift the stop").fill("unlock");
    await page.getByRole("button", { name: "Unlock" }).click();
    await expect(page.getByRole("button", { name: "Stop", exact: true })).toBeVisible();
  });

  test("a person can reject a request that waits for confirmation", async ({ page }) => {
    await page.goto("/spec/playground/?example=grbl-laser");
    await page.getByLabel("Simulated reading for door_closed").fill("true");
    await page.getByLabel("Simulated reading for door_closed").press("Enter");
    await page.getByLabel("Channel or action").selectOption("laser_power");
    await page.waitForTimeout(1000);
    await page.getByLabel("Value").fill("10 %");
    await page.getByRole("button", { name: "Send hal/write" }).click();
    await expect(page.locator(".exchanges > li").first()).toContainText('"status": "pending"');
    await page.getByRole("button", { name: "Reject" }).click();
    await expect(page.locator(".exchanges > li").first()).toContainText("hal/confirmations/reject");
    await expect(page.getByRole("button", { name: "Reject" })).toHaveCount(0);
  });

  test("the device picker lists the devices in the file", async ({ page }) => {
    await page.goto("/spec/playground/");
    await page.locator("summary", { hasText: "Build your own request" }).click();
    const device = page.locator(".request select").nth(1);
    await expect(device).toHaveValue("printer");
    expect(await device.locator("option").count()).toBeGreaterThan(0);
  });
});
