import { expect, test, type Page } from "@playwright/test";
import { AgentClient, hubState, liftStop, signIn } from "./hub";

test.beforeEach(async ({ context }) => {
  await signIn(context);
});

test.afterEach(async () => {
  await liftStop();
});

function tabKey(browserName: string): string {
  return browserName === "webkit" ? "Alt+Tab" : "Tab";
}

async function focusedName(page: Page): Promise<string> {
  return page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    return (element?.getAttribute("aria-label") || element?.textContent || "").trim();
  });
}

async function tabTo(page: Page, key: string, name: string, limit = 40): Promise<number> {
  for (let presses = 1; presses <= limit; presses++) {
    await page.keyboard.press(key);
    if ((await focusedName(page)) === name) return presses;
  }
  throw new Error(`${name} was not reached in ${limit} presses of ${key}.`);
}

async function queueCancel(name: string): Promise<string> {
  const agent = await AgentClient.connect(name, hubState().printToken);
  const pending = await agent.call("hal/action", { device: "printer", action: "cancel" });
  agent.close();
  expect(pending.result?.status).toBe("pending");
  return String(pending.result?.requestId);
}

const VIEWS = ["#/devices/printer", "#/confirmations", "#/audit", "#/routines", "#/writer", "#/settings"];

test("STOP is the third Tab stop on every view", async ({ page, browserName }) => {
  test.setTimeout(120_000);
  const key = tabKey(browserName);
  for (const view of VIEWS) {
    await page.goto(`/${view}`);
    await page.reload();
    await expect(page.locator("main h1, main h2").first()).toBeVisible();
    expect(await tabTo(page, key, "STOP every device"), view).toBe(3);
  }
});

test("STOP and UNLOCK work from the keyboard alone, and Escape keeps the hub stopped", async ({ page, browserName }) => {
  test.setTimeout(90_000);
  const key = tabKey(browserName);
  await page.goto("/#/devices/printer");
  await expect(page.getByRole("heading", { name: "Klipper 3D printer", level: 1 })).toBeVisible();
  await tabTo(page, key, "STOP every device");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: "error -32014 STOPPED" })).toBeVisible();

  await page.goto("/#/devices/printer");
  const unlock = page.getByRole("button", { name: "UNLOCK" });
  await expect(unlock).toBeVisible();
  await tabTo(page, key, "UNLOCK");
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Lift the stop" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Phrase")).toBeFocused();
  await page.keyboard.press(key);
  await expect(dialog.getByRole("button", { name: "Keep stopped" })).toBeFocused();
  await page.keyboard.press(key);
  await expect(dialog.getByLabel("Phrase")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(unlock).toBeFocused();
  await expect(page.getByRole("status").filter({ hasText: "error -32014 STOPPED" })).toBeVisible();

  await page.keyboard.press("Space");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel("Phrase")).toBeFocused();
  await page.keyboard.type("open");
  await page.keyboard.press("Enter");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Unlock", exact: true })).toBeDisabled();
  await dialog.getByLabel("Phrase").fill("");
  await page.keyboard.type("unlock");
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: /STOP/ })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "STOPPED" })).toHaveCount(0);
});

test("approve and reject work from the keyboard in their order", async ({ page, browserName }) => {
  const key = tabKey(browserName);
  const rejected = await queueCancel("keyboard-reject");
  await page.goto("/#/confirmations");
  const request = page.getByRole("main").getByRole("listitem").filter({ hasText: rejected });
  const approve = request.getByRole("button", { name: "Approve and run cancel" });
  await approve.focus();
  await page.keyboard.press(key);
  await expect(request.getByLabel("Reason to reject, optional")).toBeFocused();
  await page.keyboard.type("checked by keyboard");
  await page.keyboard.press(key);
  await expect(request.getByRole("button", { name: "Reject" })).toBeFocused();
  await page.keyboard.press("Enter");
  const decided = page.getByRole("region", { name: "Your decisions" }).getByRole("listitem").filter({ hasText: rejected });
  await expect(decided).toContainText("rejected");

  const approved = await queueCancel("keyboard-approve");
  await page.reload();
  const next = page.getByRole("main").getByRole("listitem").filter({ hasText: approved });
  await next.getByRole("button", { name: "Approve and run cancel" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Your decisions" }).getByRole("listitem").filter({ hasText: approved })).toContainText("approved");
});

test("selects, checkboxes, the tooltip, the views menu and the collapsible work from the keyboard", async ({ page, browserName }) => {
  test.setTimeout(90_000);
  const key = tabKey(browserName);
  const agent = await AgentClient.connect("keyboard-agent", hubState().printToken);
  await agent.call("hal/read", { device: "printer", channel: "state" });
  agent.close();
  await page.goto("/#/devices/printer");
  const client = page.getByRole("combobox", { name: "Client", exact: true });
  await client.focus();
  await page.keyboard.press("Enter");
  const list = page.getByRole("listbox");
  await expect(list).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(list).toBeHidden();
  await expect(client).toBeFocused();
  await expect(client).toHaveText("All clients");
  await page.keyboard.press("ArrowDown");
  await expect(list).toBeVisible();
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await expect(list).toBeHidden();
  await expect(client).not.toHaveText("All clients");

  const values = page.getByRole("checkbox", { name: "Show hal/value" });
  await values.focus();
  await page.keyboard.press("Space");
  await expect(values).toBeChecked();
  await page.keyboard.press("Space");
  await expect(values).not.toBeChecked();

  const views = page.getByRole("navigation", { name: "Views" });
  await views.getByRole("link", { name: "Devices" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(views.getByRole("link", { name: /^Confirmations/ })).toBeFocused();
  await page.keyboard.press(key);
  await expect(views.getByRole("link", { name: "Audit log" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();

  const verify = page.getByRole("button", { name: "Verify the hash chain" });
  await page.getByRole("heading", { name: "Audit log", level: 1 }).click();
  await tabTo(page, key, "Verify the hash chain");
  await expect(page.getByRole("tooltip")).toBeVisible();
  await expect(verify).toHaveAttribute("aria-describedby", /.+/);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toBeHidden();
  await page.keyboard.press("Enter");
  await expect(page.getByText("chain intact")).toBeVisible();

  await page.goto("/#/writer");
  await page.getByRole("button", { name: "Start the driver writer" }).focus();
  await page.keyboard.press("Enter");
  const raw = page.getByRole("button", { name: "Everything the device and its sources reported" });
  await expect(raw).toBeVisible({ timeout: 20_000 });
  await raw.focus();
  await page.keyboard.press("Enter");
  await expect(raw).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Space");
  await expect(raw).toHaveAttribute("aria-expanded", "false");
});

test("a bool channel is a radio group that moves with the arrow keys", async ({ page }) => {
  await page.route("**/v1/devices/bench-lamp", async (route) => {
    const response = await route.fetch();
    const view = (await response.json()) as Record<string, unknown>;
    await route.fulfill({ response, json: { ...view, writable: true } });
  });
  await page.goto("/#/devices/bench-lamp");
  const group = page.getByRole("radiogroup", { name: "enabled new value" });
  await expect(group).toBeVisible();
  const off = group.getByRole("radio", { name: "false" });
  const on = group.getByRole("radio", { name: "true" });
  await off.focus();
  await page.keyboard.press("ArrowRight");
  await expect(on).toBeFocused();
  await expect(on).toBeChecked();
  await page.keyboard.press("ArrowLeft");
  await expect(off).toBeChecked();
  await expect(page.locator("form.write").filter({ hasText: "enabled" }).getByRole("button", { name: "Set enabled" })).toBeEnabled();
});

test("the revoke confirmation opens, holds focus and closes from the keyboard", async ({ page }) => {
  await page.goto("/#/settings");
  await page.getByLabel("Name").fill("keyboard-token");
  await page.keyboard.press("Enter");
  await expect(page.getByText("keyboard-token was created.")).toBeVisible();
  const revoke = page.getByRole("row").filter({ hasText: "keyboard-token" }).getByRole("button", { name: "Revoke keyboard-token" });
  await revoke.focus();
  await page.keyboard.press("Enter");
  const confirm = page.getByRole("alertdialog", { name: "Revoke keyboard-token" });
  await expect(confirm.getByRole("button", { name: "Keep" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(confirm).toBeHidden();
  await expect(revoke).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(confirm).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(confirm.getByRole("button", { name: "Revoke keyboard-token" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("row").filter({ hasText: "keyboard-token" })).toHaveCount(0);
});
