import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { AgentClient, hubState, signIn } from "./hub";

test.beforeEach(async ({ context }) => {
  await signIn(context);
});

async function focusedText(page: Page): Promise<string> {
  return page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    return (element?.getAttribute("aria-label") || element?.textContent || "").trim();
  });
}

async function hasVisibleFocus(page: Page): Promise<string | true> {
  return page.evaluate(() => {
    const element = document.activeElement as HTMLElement | null;
    if (!element || element === document.body) return "nothing has focus";
    const style = getComputedStyle(element);
    if (style.outlineStyle !== "none" && parseFloat(style.outlineWidth) >= 2) return true;
    return `${element.tagName.toLowerCase()}.${element.className} has no focus outline`;
  });
}

test("the Inspector works from the keyboard with visible focus", async ({ page, browserName }) => {
  await page.goto("/#/devices/desk-fan");
  await expect(page.getByRole("heading", { name: "Desk fan controller" })).toBeVisible();
  const tab = browserName === "webkit" ? "Alt+Tab" : "Tab";

  await page.keyboard.press(tab);
  expect(await focusedText(page)).toBe("Skip to content");
  expect(await hasVisibleFocus(page)).toBe(true);

  const seen: string[] = [];
  for (let step = 0; step < 12; step++) {
    await page.keyboard.press(tab);
    seen.push(await focusedText(page));
    expect(await hasVisibleFocus(page)).toBe(true);
  }
  expect(seen).toContain("STOP every device");
  expect(seen.some((text) => text.startsWith("Confirmations"))).toBe(true);

  await page.locator("nav.views a", { hasText: "Audit log" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();

  await page.locator("nav.views a", { hasText: "Devices" }).focus();
  await page.keyboard.press("Enter");
  const slider = page.getByRole("slider", { name: "fan_speed new value" });
  await slider.focus();
  const before = Number(await slider.inputValue());
  await page.keyboard.press(before >= 100 ? "ArrowLeft" : "ArrowRight");
  expect(Number(await slider.inputValue())).not.toBe(before);
  await page.keyboard.press("End");
  expect(await slider.inputValue()).toBe("100");
});

const VIEWS = ["#/devices/desk-fan", "#/devices/bench-lamp", "#/confirmations", "#/audit", "#/routines", "#/writer", "#/settings"];

for (const scheme of ["light", "dark"] as const) {
  test(`every view passes axe WCAG 2.1 AA in the ${scheme} theme`, async ({ page }) => {
    test.setTimeout(90_000);
    await page.emulateMedia({ colorScheme: scheme });
    const agent = await AgentClient.connect("axe-agent", hubState().agentToken);
    await agent.write("desk-fan", "fan_speed", "150 %");
    await agent.call("hal/action", { device: "desk-fan", action: "spin_test", args: { seconds: "5 s" } });
    agent.close();
    for (const view of VIEWS) {
      await page.goto(`/${view}`);
      await expect(page.locator("main h1, main h2").first()).toBeVisible();
      await page.waitForTimeout(300);
      const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      const problems = results.violations.map(
        (violation) => `${view} ${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`,
      );
      expect(problems).toEqual([]);
    }
  });
}
