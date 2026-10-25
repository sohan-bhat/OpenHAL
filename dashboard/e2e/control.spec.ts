import { expect, test } from "@playwright/test";
import { AgentClient, hubState, signIn } from "./hub";

test.beforeEach(async ({ context }) => {
  await signIn(context);
});

test("STOP puts the hub in the stopped state and UNLOCK needs the typed phrase", async ({ page }) => {
  await page.goto("/#/devices/desk-fan");
  await page.getByRole("button", { name: /STOP/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "error -32014 STOPPED" })).toBeVisible();
  const unlock = page.getByRole("button", { name: "UNLOCK" });
  await expect(unlock).toBeVisible();

  const agent = await AgentClient.connect("stopped-agent", hubState().agentToken);
  const refused = await agent.write("desk-fan", "fan_speed", "10 %");
  agent.close();
  expect(refused.error?.data?.name).toBe("STOPPED");
  await expect(page.locator('li[data-kind="error"]').filter({ hasText: "error -32014 STOPPED" }).last()).toBeVisible();

  await unlock.click();
  const dialog = page.getByRole("dialog", { name: "Lift the stop" });
  await expect(dialog).toBeVisible();
  const confirm = dialog.getByRole("button", { name: "Unlock", exact: true });
  await dialog.getByLabel("Phrase").fill("open");
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel("Phrase").fill("unlock");
  await confirm.click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("button", { name: /STOP/ })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "STOPPED" })).toHaveCount(0);
});

async function queueVent(name: string): Promise<string> {
  const agent = await AgentClient.connect(name, hubState().mediumToken);
  const pending = await agent.call("hal/action", { device: "curing-heater", action: "vent", args: { seconds: "5 s" } });
  agent.close();
  expect(pending.result?.status).toBe("pending");
  return String(pending.result?.requestId);
}

test("a person approves a pending request and sees the result", async ({ page }) => {
  const requestId = await queueVent("approve-agent");
  await page.goto("/#/confirmations");
  const request = page.getByRole("main").getByRole("listitem").filter({ hasText: requestId });
  await expect(request).toContainText("agent:lab-script");
  await expect(request).toContainText("hal/action");
  await expect(request).toContainText('"vent"');
  await expect(request).toContainText("dry run");
  await request.getByRole("button", { name: "Approve" }).click();
  const decided = page.getByRole("region", { name: "Your decisions" }).getByRole("listitem").filter({ hasText: requestId });
  await expect(decided).toContainText("approved");
  await expect(page.getByRole("main").getByRole("listitem").filter({ hasText: "requested by" }).filter({ hasText: requestId })).toHaveCount(0);
});

test("a person rejects a pending request with a reason", async ({ page }) => {
  const requestId = await queueVent("reject-agent");
  await page.goto("/#/confirmations");
  const request = page.getByRole("main").getByRole("listitem").filter({ hasText: requestId });
  await request.getByLabel("Reason to reject, optional").fill("not while the plant is drying");
  await request.getByRole("button", { name: "Reject" }).click();
  const decided = page.getByRole("region", { name: "Your decisions" }).getByRole("listitem").filter({ hasText: requestId });
  await expect(decided).toContainText("rejected");
  await expect(page.getByRole("table").getByRole("row").filter({ hasText: requestId })).toContainText("rejected");
});
