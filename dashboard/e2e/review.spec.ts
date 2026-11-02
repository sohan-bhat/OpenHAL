import AxeBuilder from "@axe-core/playwright";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { hubState, signIn } from "./hub";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

async function violations(page: Page, name: string): Promise<string[]> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(200);
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return results.violations.map((violation) => `${name} ${violation.id}: ${violation.nodes.map((node) => node.target.join(" ")).join(", ")}`);
}

async function resetLamp(): Promise<void> {
  const response = await fetch(`${hubState().url}/_harness/bench-lamp/reset`, { method: "POST" });
  if (!response.ok) throw new Error("The harness could not put the bench lamp's file back.");
}

async function useEverySuggestion(page: Page): Promise<void> {
  for (const button of await page.getByRole("button", { name: /^Use suggested value for / }).all()) await button.click();
}

async function openReview(page: Page): Promise<void> {
  await page.goto("/#/devices/bench-lamp");
  await expect(page.getByRole("heading", { name: "Bench lamp", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Review limits" }).click();
  await expect(page.getByRole("heading", { name: "Review limits", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Limits interview" })).toBeVisible();
}

test.describe.configure({ mode: "serial" });
test.afterEach(resetLamp);

test("Review limits walks the interview, holds a value past the device's range and loads the file writable", async ({ page, context }) => {
  await signIn(context);
  await openReview(page);
  await useEverySuggestion(page);
  const maximum = page.getByLabel("brightness, in percent. The most an agent may set.");
  await maximum.fill("120 %");
  const confirm = page.getByRole("button", { name: "Confirm the limits" });
  await expect(confirm).toBeDisabled();
  await page.getByLabel("Phrase").fill("confirm");
  await confirm.click();
  const held = page.getByText("120 % is above 100 %, the most the device reports. Answer a value from 0 % to 100 %.");
  await expect(held).toBeVisible();
  await expect(page.getByLabel("brightness, in percent. The most an agent may set.")).toHaveAttribute("aria-invalid", "true");
  await page.getByLabel("brightness, in percent. The most an agent may set.").fill("60 %");
  await page.getByRole("button", { name: "Confirm the limits" }).click();
  await expect(page.getByText("is now writable.")).toBeVisible();
  await page.getByRole("link", { name: "bench-lamp" }).first().click();
  await expect(page.getByRole("heading", { name: "Bench lamp", level: 1 })).toBeVisible();
  await expect(page.getByText("takes commands")).toBeVisible();
  await expect(page.getByRole("button", { name: "Review limits" })).toHaveCount(0);
});

test("the phrase is the last step and a wrong phrase keeps the button off", async ({ page, context }) => {
  await signIn(context);
  await openReview(page);
  await useEverySuggestion(page);
  const confirm = page.getByRole("button", { name: "Confirm the limits" });
  await page.getByLabel("Phrase").fill("yes");
  await expect(confirm).toBeDisabled();
  await page.getByLabel("Phrase").fill("CONFIRM");
  await expect(confirm).toBeEnabled();
});

test("an agent's session never sees Review limits, and an agent token can't start, answer or finish a review", async ({ browser }) => {
  const state = hubState();
  const agentContext: BrowserContext = await browser.newContext();
  await agentContext.addCookies([
    { name: "openhal_session", value: state.agentToken, url: state.url, httpOnly: true, sameSite: "Strict" },
  ]);
  const page = await agentContext.newPage();
  await page.goto("/#/devices/bench-lamp");
  await expect(page.getByRole("heading", { name: "Bench lamp", level: 1 })).toBeVisible();
  await expect(page.getByText("limits not confirmed")).toBeVisible();
  await expect(page.getByRole("button", { name: "Review limits" })).toHaveCount(0);
  await agentContext.close();

  const asAgent = { Authorization: `Bearer ${state.mediumToken}`, "Content-Type": "application/json" };
  const asPerson = { Authorization: `Bearer ${state.humanToken}`, "Content-Type": "application/json" };
  const refused = await fetch(`${state.url}/v1/writer/sessions`, { method: "POST", headers: asAgent, body: JSON.stringify({ device: "bench-lamp" }) });
  expect(refused.status).toBe(403);
  const started = await fetch(`${state.url}/v1/writer/sessions`, { method: "POST", headers: asPerson, body: JSON.stringify({ device: "bench-lamp" }) });
  const session = (await started.json()) as { id: string };
  const base = `${state.url}/v1/writer/sessions/${session.id}`;
  const questions = (await (await fetch(`${base}/interview`, { headers: asPerson })).json()) as { questions: { id: string; suggested: unknown; unit: string | null }[] };
  const answers = Object.fromEntries(questions.questions.map((question) => [question.id, `${question.suggested}${question.unit === "percent" ? " %" : ""}`]));
  const answered = await fetch(`${base}/answers`, { method: "POST", headers: asAgent, body: JSON.stringify({ answers }) });
  expect(answered.status).toBe(403);
  await fetch(`${base}/answers`, { method: "POST", headers: asPerson, body: JSON.stringify({ answers }) });
  const finished = await fetch(`${base}/finish`, { method: "POST", headers: asAgent, body: JSON.stringify({ phrase: "confirm" }) });
  expect(finished.status).toBe(403);
  const device = (await (await fetch(`${state.url}/v1/devices/bench-lamp`, { headers: asPerson })).json()) as { writable: boolean };
  expect(device.writable).toBe(false);
});

for (const scheme of ["light", "dark"] as const) {
  test(`the Review limits flow passes axe WCAG 2.1 AA in the ${scheme} theme`, async ({ browser }) => {
    test.setTimeout(240_000);
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme });
    await signIn(context);
    const page = await context.newPage();
    const problems: string[] = [];
    await page.goto("/#/devices/bench-lamp");
    await expect(page.getByRole("button", { name: "Review limits" })).toBeVisible();
    problems.push(...(await violations(page, "device with Review limits")));
    await page.getByRole("button", { name: "Review limits" }).click();
    await expect(page.getByRole("heading", { name: "Limits interview" })).toBeVisible();
    problems.push(...(await violations(page, "review interview")));
    await useEverySuggestion(page);
    await page.getByLabel("brightness, in percent. The most an agent may set.").fill("120 %");
    await page.getByLabel("Phrase").fill("confirm");
    await page.getByRole("button", { name: "Confirm the limits" }).click();
    await expect(page.getByText("the most the device reports")).toBeVisible();
    problems.push(...(await violations(page, "review with a held answer")));
    await page.getByLabel("brightness, in percent. The most an agent may set.").fill("60 %");
    await page.getByRole("button", { name: "Confirm the limits" }).click();
    await expect(page.getByText("is now writable.")).toBeVisible();
    problems.push(...(await violations(page, "review confirmed")));
    await context.close();
    expect(problems).toEqual([]);
  });
}
