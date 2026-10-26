import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import type { BrowserContext } from "@playwright/test";

export const PORT = Number(process.env.INSPECTOR_PORT ?? 7431);
export const STATE_PATH =
  process.env.INSPECTOR_STATE ?? fileURLToPath(new URL("../test-results/inspector-hub.json", import.meta.url));

export interface HubState {
  url: string;
  port: number;
  humanToken: string;
  agentToken: string;
  mediumToken: string;
  printToken: string;
}

export function hubState(): HubState {
  return JSON.parse(readFileSync(STATE_PATH, "utf-8")) as HubState;
}

export async function tank(action: "drain" | "refill"): Promise<void> {
  const response = await fetch(`${hubState().url}/_harness/plant-waterer/${action}`, { method: "POST" });
  if (!response.ok) throw new Error(`The harness could not ${action} the tank.`);
}

async function harness(path: string, what: string): Promise<void> {
  const response = await fetch(`${hubState().url}/_harness/${path}`, { method: "POST" });
  if (!response.ok) throw new Error(`The harness could not ${what}.`);
}

export const showFrame = (name: "first-layer" | "come-loose") => harness(`printer-cam/show/${name}`, `show the ${name} frame`);
export const printAgain = () => harness("printer/print", "start the print again");
export const printerError = () => harness("printer/error", "put the printer in its error state");

export async function signIn(context: BrowserContext): Promise<HubState> {
  const state = hubState();
  await context.addCookies([
    { name: "openhal_session", value: state.humanToken, url: state.url, httpOnly: true, sameSite: "Strict" },
  ]);
  return state;
}

interface RpcMessage {
  jsonrpc: "2.0";
  id?: number;
  method?: string;
  result?: Record<string, unknown>;
  error?: { code: number; message: string; data?: Record<string, unknown> };
}

export class AgentClient {
  private socket: WebSocket;
  private next = 1;
  private waiting = new Map<number, (message: RpcMessage) => void>();

  private constructor(socket: WebSocket) {
    this.socket = socket;
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(String(event.data)) as RpcMessage;
      if (message.id !== undefined && this.waiting.has(message.id)) {
        this.waiting.get(message.id)!(message);
        this.waiting.delete(message.id);
      }
    });
  }

  static async connect(name: string, token: string): Promise<AgentClient> {
    const socket = new WebSocket(`ws://127.0.0.1:${PORT}/rpc`);
    await new Promise<void>((resolve, reject) => {
      socket.addEventListener("open", () => resolve(), { once: true });
      socket.addEventListener("error", () => reject(new Error("The /rpc WebSocket did not open.")), { once: true });
    });
    const client = new AgentClient(socket);
    const hello = await client.call("hal/initialize", {
      protocolVersion: "2026-10-24",
      clientInfo: { name, version: "1.4.0" },
      token,
    });
    if (hello.error) throw new Error(hello.error.message);
    client.notify("hal/initialized");
    return client;
  }

  call(method: string, params: Record<string, unknown> = {}): Promise<RpcMessage> {
    const id = this.next++;
    return new Promise((resolve) => {
      this.waiting.set(id, resolve);
      this.socket.send(JSON.stringify({ jsonrpc: "2.0", id, method, params }));
    });
  }

  notify(method: string): void {
    this.socket.send(JSON.stringify({ jsonrpc: "2.0", method }));
  }

  write(device: string, channel: string, value: number, unit: string): Promise<RpcMessage> {
    return this.call("hal/write", { device, channel, value, unit });
  }

  close(): void {
    this.socket.close();
  }
}
