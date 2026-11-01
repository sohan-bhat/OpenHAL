import { expect, test, type Locator, type Page } from "@playwright/test";
import { liftStop, signIn } from "./hub";

test.beforeEach(async ({ context }) => {
  await signIn(context);
});

test.afterEach(async () => {
  await liftStop();
});

interface PageFrame {
  overflowY: string;
  paddingRight: string;
  marginRight: string;
  clientWidth: number;
  scrollY: number;
}

async function frame(page: Page): Promise<PageFrame> {
  return page.evaluate(() => {
    const body = getComputedStyle(document.body);
    return {
      overflowY: body.overflowY,
      paddingRight: body.paddingRight,
      marginRight: body.marginRight,
      clientWidth: document.documentElement.clientWidth,
      scrollY: Math.round(window.scrollY),
    };
  });
}

async function expectPageInPlace(page: Page, before: PageFrame, overlay: Locator): Promise<void> {
  await expect(overlay).toBeVisible();
  await page.waitForTimeout(250);
  const open = await frame(page);
  expect(open.overflowY).not.toBe("hidden");
  expect(open.paddingRight).toBe(before.paddingRight);
  expect(open.marginRight).toBe(before.marginRight);
  expect(open.clientWidth).toBe(before.clientWidth);
}

test("an open dialog, confirmation or select leaves the page's scrollbar in place", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 700 });
  await page.goto("/#/devices/printer");
  await expect(page.getByRole("heading", { name: "Klipper 3D printer", level: 1 })).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 400));
  const before = await frame(page);
  expect(before.scrollY).toBeGreaterThan(0);

  await page.getByRole("button", { name: /STOP/ }).click();
  await page.getByRole("button", { name: "UNLOCK" }).click();
  const dialog = page.getByRole("dialog", { name: "Lift the stop" });
  await expectPageInPlace(page, before, dialog);
  const scrolled = (await frame(page)).scrollY;
  const box = (await dialog.boundingBox())!;
  await page.mouse.move(box.x - 60, box.y + 20);
  await page.mouse.wheel(0, 600);
  await page.mouse.move(box.x + 20, box.y + 20);
  await page.mouse.wheel(0, 600);
  await page.waitForTimeout(300);
  expect((await frame(page)).scrollY).toBe(scrolled);
  await dialog.getByLabel("Phrase").fill("unlock");
  await dialog.getByRole("button", { name: "Unlock", exact: true }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: /STOP/ })).toBeVisible();

  const client = page.getByRole("combobox", { name: "Client", exact: true });
  const list = page.getByRole("listbox");
  const atList = await frame(page);
  await client.click();
  await expectPageInPlace(page, atList, list);
  await page.keyboard.press("Escape");
  await expect(list).toBeHidden();

  await page.goto("/#/settings");
  await page.getByLabel("Name").fill("overlay-token");
  await page.getByRole("button", { name: "Create token" }).click();
  await expect(page.getByText("overlay-token was created.")).toBeVisible();
  const atSettings = await frame(page);
  await page.getByRole("button", { name: "Revoke overlay-token" }).click();
  const confirm = page.getByRole("alertdialog", { name: "Revoke overlay-token" });
  await expectPageInPlace(page, atSettings, confirm);
  await confirm.getByRole("button", { name: "Keep" }).click();
  await expect(confirm).toBeHidden();
});
