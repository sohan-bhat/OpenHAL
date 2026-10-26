import { expect, test } from "@playwright/test";
import { AgentClient, hubState, printAgain, showFrame, signIn } from "./hub";

test.beforeEach(async ({ context }) => {
  await signIn(context);
});

test("STOP puts the hub in the stopped state and UNLOCK needs the typed phrase", async ({ page }) => {
  await page.goto("/#/devices/printer");
  await page.getByRole("button", { name: /STOP/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "error -32014 STOPPED" })).toBeVisible();
  const unlock = page.getByRole("button", { name: "UNLOCK" });
  await expect(unlock).toBeVisible();

  const agent = await AgentClient.connect("stopped-agent", hubState().printToken);
  const refused = await agent.write("printer", "bed_target", 70, "degC");
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

async function queueCancel(name: string): Promise<string> {
  const agent = await AgentClient.connect(name, hubState().printToken);
  const pending = await agent.call("hal/action", { device: "printer", action: "cancel" });
  agent.close();
  expect(pending.result?.status).toBe("pending");
  return String(pending.result?.requestId);
}

test("the cancel request says what the agent asked and why it waits, with the camera beside it", async ({ page }) => {
  await showFrame("come-loose");
  const requestId = await queueCancel("print-watcher");
  await page.goto("/#/confirmations");
  const request = page.getByRole("main").getByRole("listitem").filter({ hasText: requestId });
  await expect(request.getByRole("heading", { level: 3 })).toHaveText("The agent print-watcher asks to run cancel on Klipper 3D printer.");
  await expect(request).toContainText("agent:print-watcher");
  await expect(request).toContainText('"action": "cancel"');
  await expect(request).toContainText("Cancel the print. It can't be resumed afterwards.");
  await expect(request).toContainText("printer.hal.yaml asks a person to confirm cancel each time.");
  await expect(request).toContainText(/Expires in\s+\d+ s/);
  await expect(request.getByRole("img")).toHaveCount(0);
  await expect(request).toContainText("Pick the camera that watches Klipper 3D printer.");
  await request.getByRole("combobox", { name: "Show a camera" }).selectOption("printer-cam/frame");
  const frame = request.getByRole("img", { name: /^Demo frame from Printer camera, frame/ });
  await expect(frame).toBeVisible();
  await expect(request).toContainText("24 KB");
  await expect(request.locator("a img")).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("main").getByRole("listitem").filter({ hasText: requestId }).getByRole("img", { name: /^Demo frame from Printer camera/ })).toBeVisible();
  await expect(request.getByRole("button", { name: "Approve and run cancel" })).toBeVisible();
  await expect(request.getByRole("button", { name: "Reject" })).toBeVisible();
});

test("a person approves a pending cancel and sees the result", async ({ page }) => {
  await printAgain();
  const requestId = await queueCancel("approve-agent");
  await page.goto("/#/confirmations");
  const request = page.getByRole("main").getByRole("listitem").filter({ hasText: requestId });
  await expect(request).toContainText("hal/action");
  await request.getByRole("button", { name: "Approve and run cancel" }).click();
  const decided = page.getByRole("region", { name: "Your decisions" }).getByRole("listitem").filter({ hasText: requestId });
  await expect(decided).toContainText("approved");
  await expect(decided).toContainText("granted");
  await expect(page.getByRole("main").getByRole("listitem").filter({ hasText: "asks to run" }).filter({ hasText: requestId })).toHaveCount(0);
  await printAgain();
});

test("a person rejects a pending cancel with a reason", async ({ page }) => {
  const requestId = await queueCancel("reject-agent");
  await page.goto("/#/confirmations");
  const request = page.getByRole("main").getByRole("listitem").filter({ hasText: requestId });
  await request.getByLabel("Reason to reject, optional").fill("the print looks fine");
  await request.getByRole("button", { name: "Reject" }).click();
  const decided = page.getByRole("region", { name: "Your decisions" }).getByRole("listitem").filter({ hasText: requestId });
  await expect(decided).toContainText("rejected");
  await expect(page.getByRole("table").getByRole("row").filter({ hasText: requestId })).toContainText("rejected");
});
