import { expect, test, type Page } from "@playwright/test";
import { AgentClient, hubState, signIn } from "./hub";

async function offenders(page: Page, view: string): Promise<string[]> {
  await page.evaluate(() => document.fonts.ready);
  const found = await page.evaluate(() => {
    const probe = document.createElement("span");
    document.body.append(probe);
    const color = (token: string) => {
      probe.style.color = `var(${token})`;
      return getComputedStyle(probe).color;
    };
    const status = new Set(["--ok", "--confirm", "--blocked", "--unverified"].map(color));
    probe.style.backgroundColor = "var(--confirm-bg)";
    const tint = getComputedStyle(probe).backgroundColor;
    probe.remove();
    const name = (element: Element) =>
      `${element.tagName.toLowerCase()}.${[...element.classList].join(".")} "${(element.textContent ?? "").trim().slice(0, 40)}"`;
    const problems: string[] = [];
    for (const mark of document.querySelectorAll("[data-tone]")) {
      if (mark.querySelector("svg, img, i, [role='img']")) problems.push(`${name(mark)} has an icon inside`);
      for (const side of [mark.previousElementSibling, mark.nextElementSibling]) {
        if (side?.matches("svg, img, i")) problems.push(`${name(mark)} has an icon beside it`);
      }
      for (const pseudo of ["::before", "::after"]) {
        const content = getComputedStyle(mark, pseudo).content;
        if (content && content !== "none" && content !== "normal") problems.push(`${name(mark)} has ${pseudo} ${content}`);
      }
    }
    for (const element of document.querySelectorAll("body *")) {
      if (element.closest(".stop")) continue;
      const style = getComputedStyle(element);
      for (const side of ["Top", "Right", "Bottom", "Left"] as const) {
        const width = parseFloat(style.getPropertyValue(`border-${side.toLowerCase()}-width`));
        const kind = style.getPropertyValue(`border-${side.toLowerCase()}-style`);
        const shade = style.getPropertyValue(`border-${side.toLowerCase()}-color`);
        if (!width || kind === "none" || !status.has(shade)) continue;
        if (side === "Left" && kind === "dashed" && element.matches(".agent")) continue;
        problems.push(`${name(element)} has a status colored ${side.toLowerCase()} border`);
      }
      if (status.has(style.backgroundColor) || style.backgroundColor === tint) problems.push(`${name(element)} has a status background`);
    }
    return problems;
  });
  return found.map((problem) => `${view}: ${problem}`);
}

const VIEWS = [
  "#/devices/printer",
  "#/devices/printer-cam",
  "#/devices/bench-lamp",
  "#/devices/curing-heater",
  "#/confirmations",
  "#/audit",
  "#/routines",
  "#/writer",
  "#/settings",
];

for (const scheme of ["light", "dark"] as const) {
  test(`no status word has a shape, dot, icon or box beside it, in the ${scheme} theme`, async ({ browser }) => {
    test.setTimeout(120_000);
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme });
    await signIn(context);
    const page = await context.newPage();
    const agent = await AgentClient.connect("status-agent", hubState().printToken);
    await agent.write("printer", "extruder_target", 300, "degC");
    const cancel = await agent.call("hal/action", { device: "printer", action: "cancel" });
    agent.close();
    expect(cancel.result?.status).toBe("pending");
    const problems: string[] = [];

    for (const view of VIEWS) {
      await page.goto(`/${view}`);
      await expect(page.locator("main h1, main h2").first()).toBeVisible();
      await page.waitForTimeout(300);
      problems.push(...(await offenders(page, view)));
    }

    await page.goto("/#/routines/water-when-dry");
    await page.getByRole("button", { name: "Dry run" }).click();
    await expect(page.getByRole("heading", { name: "Dry run" })).toBeVisible();
    problems.push(...(await offenders(page, "routine dry run")));

    await page.goto("/#/devices/curing-heater");
    const power = page.locator("form.write").filter({ hasText: "power" });
    await expect(power.locator("output")).toHaveText(/\d+ W/);
    await power.getByRole("spinbutton").fill((await power.locator("output").textContent())!.replace(/[^0-9.]/g, ""));
    await power.getByRole("button", { name: "Set power" }).click();
    await expect(power.locator(".result")).toContainText("granted");
    const vent = page.locator("form.action").filter({ hasText: "vent" });
    await vent.getByRole("button", { name: "Confirm and run vent" }).click();
    await expect(vent.locator(".result")).toContainText("granted");
    problems.push(...(await offenders(page, "write and action results")));

    await page.goto("/#/devices/printer");
    await page.getByRole("button", { name: /STOP/ }).click();
    await expect(page.getByRole("button", { name: "UNLOCK" })).toBeVisible();
    problems.push(...(await offenders(page, "stopped")));
    await page.getByRole("button", { name: "UNLOCK" }).click();
    const dialog = page.getByRole("dialog", { name: "Lift the stop" });
    await dialog.getByLabel("Phrase").fill("unlock");
    await dialog.getByRole("button", { name: "Unlock", exact: true }).click();
    await expect(page.getByRole("button", { name: /STOP/ })).toBeVisible();
    await context.close();

    const stranger = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme });
    const pair = await stranger.newPage();
    await pair.goto("/");
    await expect(pair.getByRole("complementary", { name: "STOP needs a paired browser" })).toBeVisible();
    problems.push(...(await offenders(pair, "pair")));
    await stranger.close();

    expect(problems).toEqual([]);
  });
}
