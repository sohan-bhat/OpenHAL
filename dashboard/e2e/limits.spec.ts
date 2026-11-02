import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { hubState, signIn } from "./hub";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function violations(page: Page, name: string): Promise<string[]> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(200);
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return results.violations.map((violation) => `${name} ${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

async function resetHeater(): Promise<void> {
  const response = await fetch(`${hubState().url}/_harness/curing-heater/reset`, { method: "POST" });
  if (!response.ok) throw new Error("The harness could not put the curing heater's file back.");
}

async function agentAsksForMore(): Promise<string> {
  const state = hubState();
  const response = await fetch(`${state.url}/v1/limits`, {
    method: "POST",
    headers: { Authorization: `Bearer ${state.mediumToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ device: "curing-heater", channel: "power", max: { value: 70, unit: "W" } }),
  });
  const result = (await response.json()) as { status: string; request_id: string };
  expect(result.status).toBe("pending");
  return result.request_id;
}

async function heaterMax(): Promise<number> {
  const state = hubState();
  const response = await fetch(`${state.url}/v1/devices/curing-heater/limits`, { headers: { Authorization: `Bearer ${state.humanToken}` } });
  const data = (await response.json()) as { channels: { power: { max: number } } };
  return data.channels.power.max;
}

test.describe.configure({ mode: "serial" });
test.beforeEach(resetHeater);
test.afterAll(resetHeater);

test("a person narrows a limit at once and widens a limit with the typed phrase", async ({ page, context }) => {
  await signIn(context);
  await page.goto("/#/devices/curing-heater");
  const editor = page.getByRole("form", { name: "Limits of power" });
  await expect(editor).toBeVisible();
  await editor.getByLabel("Max, in W").fill("40");
  await editor.getByRole("button", { name: "Review the change" }).click();
  await expect(editor.getByText("60 W to 40 W")).toBeVisible();
  await expect(editor.getByLabel("Phrase")).toHaveCount(0);
  await editor.getByRole("button", { name: "Save the limits" }).click();
  await expect(editor.getByRole("status")).toContainText("Done. curing-heater.power max 60 W to 40 W");
  await expect.poll(heaterMax).toBe(40);

  await editor.getByLabel("Max, in W").fill("55");
  await editor.getByRole("button", { name: "Review the change" }).click();
  await expect(editor.getByText("40 W to 55 W")).toBeVisible();
  const save = editor.getByRole("button", { name: "Save the limits" });
  await expect(save).toBeDisabled();
  await editor.getByLabel("Phrase").fill("confirm");
  await save.click();
  await expect.poll(heaterMax).toBe(55);
});

test("an agent's wider limit waits in Confirmations until a person types approve", async ({ page, context }) => {
  await signIn(context);
  const requestId = await agentAsksForMore();
  const state = hubState();
  const byAgent = await fetch(`${state.url}/v1/confirmations/${requestId}/approve`, {
    method: "POST",
    headers: { Authorization: `Bearer ${state.mediumToken}`, "Content-Type": "application/json" },
    body: JSON.stringify({ phrase: "approve" }),
  });
  expect(byAgent.status).toBe(403);
  expect(await heaterMax()).toBe(60);

  await page.goto("/#/confirmations");
  const change = page.getByRole("listitem").filter({ hasText: "sends a request to widen the limits of" });
  await expect(change).toBeVisible();
  await expect(change.getByText("max 60 W to 70 W", { exact: true })).toBeVisible();
  const approve = change.getByRole("button", { name: "Approve the change" });
  await expect(approve).toBeDisabled();
  await change.getByLabel("Phrase").fill("approve");
  await approve.click();
  await expect.poll(heaterMax).toBe(70);
});

test("an agent's session gets no limits editor", async ({ browser }) => {
  const state = hubState();
  const context = await browser.newContext();
  await context.addCookies([{ name: "openhal_session", value: state.agentToken, url: state.url, httpOnly: true, sameSite: "Strict" }]);
  const page = await context.newPage();
  await page.goto("/#/devices/curing-heater");
  await expect(page.getByRole("heading", { name: "Resin curing heater", level: 1 })).toBeVisible();
  await expect(page.getByRole("form", { name: "Limits of power" })).toHaveCount(0);
  await context.close();
});

for (const scheme of ["light", "dark"] as const) {
  test(`the limits editor and a pending limit change pass axe WCAG 2.1 AA in the ${scheme} theme`, async ({ browser }) => {
    test.setTimeout(240_000);
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme });
    await signIn(context);
    const page = await context.newPage();
    const problems: string[] = [];
    await page.goto("/#/devices/curing-heater");
    const editor = page.getByRole("form", { name: "Limits of power" });
    await editor.getByLabel("Max, in W").fill("65");
    await editor.getByRole("button", { name: "Review the change" }).click();
    await expect(editor.getByLabel("Phrase")).toBeVisible();
    problems.push(...(await violations(page, "limits editor widening")));
    await agentAsksForMore();
    await page.goto("/#/confirmations");
    await expect(page.getByRole("heading", { name: /^Limit changes/ })).toBeVisible();
    problems.push(...(await violations(page, "pending limit change")));
    await context.close();
    expect(problems).toEqual([]);
  });
}
