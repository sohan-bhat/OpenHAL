import { expect, test } from "@playwright/test";

test.describe("catalog filters", () => {
  test("each driver filter narrows the table, stays in the address and an impossible search says so", async ({ page }) => {
    await page.goto("/drivers/");
    const all = await page.locator("[data-driver]").count();
    await expect(page.locator("[data-shown]")).toHaveText(`${all} drivers.`);
    for (const [label, option] of [["Tier", "Tier 2"], ["Conformance", "core"], ["Hazard", "high"]] as const) {
      const select = page.getByRole("combobox", { name: label, exact: true });
      await select.click();
      await page.getByRole("option", { name: option, exact: true }).click();
      await expect(select).toHaveText(option);
      await expect(page).toHaveURL(new RegExp(`[?&]${label.toLowerCase()}=`));
      const shown = await page.locator("[data-driver]:visible").count();
      expect(shown, label).toBeGreaterThan(0);
      expect(shown, label).toBeLessThan(all);
      await expect(page.locator("[data-shown]")).toHaveText(`${shown} of ${all} drivers.`);
      await select.click();
      await page.getByRole("option", { name: "Any", exact: true }).click();
      await expect(select).toHaveText("Any");
    }
    await expect(page).toHaveURL(/\/drivers\/$/);
    await expect(page.locator("[data-shown]")).toHaveText(`${all} drivers.`);
    await page.getByLabel("Filter", { exact: true }).fill("scpi");
    await expect(page.locator("[data-driver]:visible")).toHaveCount(1);
    await expect(page).toHaveURL(/\?q=scpi$/);
    await page.getByLabel("Filter", { exact: true }).fill("no such driver");
    await expect(page.locator("[data-empty]")).toBeVisible();
    await expect(page.locator("[data-shown]")).toHaveText(`0 of ${all} drivers.`);
  });

  test("a filter is drawn only when it has more than one value, after Any", async ({ page }) => {
    await page.goto("/drivers/");
    const selects = await page.locator("[data-filters] [role=combobox]").all();
    expect(selects.length).toBeGreaterThan(0);
    for (const select of selects) {
      await select.click();
      const options = page.getByRole("option");
      await expect(options.first()).toHaveText("Any");
      expect(await options.count()).toBeGreaterThan(2);
      await page.keyboard.press("Escape");
      await expect(page.getByRole("listbox")).toHaveCount(0);
    }
  });

  test("the selects open, move, choose and close from the keyboard", async ({ page }) => {
    await page.goto("/drivers/");
    await page.getByLabel("Filter", { exact: true }).focus();
    await page.keyboard.press("Tab");
    const tier = page.getByRole("combobox", { name: "Tier", exact: true });
    await expect(tier).toBeFocused();
    await page.keyboard.press("Enter");
    const list = page.getByRole("listbox");
    await expect(list).toBeVisible();
    await expect(page.getByRole("option", { name: "Any", exact: true })).toBeFocused();
    await page.keyboard.press("ArrowDown");
    const second = await page.getByRole("option").nth(1).innerText();
    await page.keyboard.press("Enter");
    await expect(list).toHaveCount(0);
    await expect(tier).toBeFocused();
    await expect(tier).toHaveText(second);
    await page.keyboard.press("Space");
    await expect(list).toBeVisible();
    await page.keyboard.press("End");
    await page.keyboard.press("Escape");
    await expect(list).toHaveCount(0);
    await expect(tier).toBeFocused();
    await expect(tier).toHaveText(second);
    await page.keyboard.press("ArrowUp");
    await expect(list).toBeVisible();
    await page.keyboard.press("Home");
    await expect(page.getByRole("option", { name: "Any", exact: true })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(tier).toHaveText("Any");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("combobox").nth(1)).toBeFocused();
  });

  test("a shared address opens with its filters chosen", async ({ page }) => {
    await page.goto("/drivers/?q=serial&hazard=high");
    await expect(page.getByRole("combobox", { name: "Hazard", exact: true })).toHaveText("high");
    await expect(page.getByLabel("Filter", { exact: true })).toHaveValue("serial");
    const shown = page.locator("[data-driver]:visible");
    await expect(shown.first()).toBeVisible();
    for (const row of await shown.all()) {
      await expect(row).toHaveAttribute("data-hazard", "high");
      await expect(row).toHaveAttribute("data-text", /serial/);
    }
    await expect(page.locator("[data-shown]")).toHaveText(new RegExp(`^${await shown.count()} of \\d+ drivers\\.$`));
  });

  test("the library filter keeps its search in the address", async ({ page }) => {
    await page.goto("/library/");
    const all = await page.locator("[data-entry]").count();
    await page.getByLabel("Filter", { exact: true }).fill("no such device");
    await expect(page.locator("[data-empty]")).toBeVisible();
    await expect(page.locator("[data-shown]")).toHaveText(`0 of ${all} device files.`);
    await expect(page).toHaveURL(/\?q=no\+such\+device$/);
    await page.goto("/library/?q=rigol");
    await expect(page.getByLabel("Filter", { exact: true })).toHaveValue("rigol");
    await expect(page.locator("[data-entry]:visible").first()).toBeVisible();
    expect(await page.locator("[data-entry]:visible").count()).toBeLessThan(all);
  });
});

test.describe("catalog filters without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  test("show the full table and hide the filters that need a script", async ({ page }) => {
    for (const [path, row, noun] of [["/drivers/", "[data-driver]", "drivers"], ["/library/", "[data-entry]", "device files"]] as const) {
      await page.goto(path);
      const all = await page.locator(row).count();
      expect(all, path).toBeGreaterThan(0);
      await expect(page.locator(`${row}:visible`), path).toHaveCount(all);
      await expect(page.locator("[data-filters]"), path).toBeHidden();
      await expect(page.locator("[data-shown]"), path).toHaveText(`${all} ${noun}.`);
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
