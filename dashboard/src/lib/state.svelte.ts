import { api, ApiError } from "./api";
import { applyReading, sortDevices, type ReadingEvent } from "./devices";
import { lastSeq, mergeEntries, parseLiveFrame } from "./logstore";
import { LiveSocket, type SocketState } from "./socket";
import type { LogEntry } from "./trace";
import type { ConfirmationRequest, DeviceSummary, DeviceView, Principal, Status } from "./types";

export type AuthState = "checking" | "paired" | "unpaired" | "offline";

interface HubEvent {
  type?: string;
  device?: string;
  event?: string;
  [key: string]: unknown;
}

class Inspector {
  auth = $state<AuthState>("checking");
  you = $state<Principal | null>(null);
  status = $state<Status | null>(null);
  devices = $state<DeviceSummary[]>([]);
  devicesLoaded = $state(false);
  views = $state<Record<string, DeviceView>>({});
  confirmations = $state<ConfirmationRequest[]>([]);
  log = $state.raw<LogEntry[]>([]);
  logAvailable = $state<boolean | null>(null);
  live = $state<SocketState>("connecting");
  logLive = $state<SocketState>("connecting");
  auditTick = $state(0);
  routineTick = $state(0);
  stopError = $state<string | null>(null);

  private liveSocket: LiveSocket | null = null;
  private logSocket: LiveSocket | null = null;
  private pending = new Set<string>();
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private pollTimer: ReturnType<typeof setInterval> | null = null;

  async boot(): Promise<void> {
    try {
      this.you = await api.whoami();
      this.auth = "paired";
    } catch (error) {
      this.auth = error instanceof ApiError && error.status === 401 ? "unpaired" : "offline";
      if (this.auth === "offline") setTimeout(() => void this.boot(), 3000);
      return;
    }
    await Promise.all([this.refreshStatus(), this.refreshDevices(), this.refreshConfirmations(), this.loadLog()]);
    this.startSockets();
    this.pollTimer = setInterval(() => {
      void this.refreshStatus();
      void this.refreshConfirmations();
    }, 5000);
  }

  shutdown(): void {
    this.liveSocket?.stop();
    this.logSocket?.stop();
    if (this.pollTimer) clearInterval(this.pollTimer);
  }

  private startSockets(): void {
    this.liveSocket = new LiveSocket("/v1/live", {
      message: (data) => this.onHubEvent(data as HubEvent),
      state: (state) => {
        this.live = state;
      },
      open: () => {
        this.schedule("status", "devices", "confirmations");
      },
    });
    this.liveSocket.start();
    if (this.logAvailable) this.startLogSocket();
  }

  private startLogSocket(): void {
    this.logSocket = new LiveSocket("/v1/rpc/log/live", {
      message: (data) => {
        const entries = parseLiveFrame(data);
        if (entries.length) this.log = mergeEntries(this.log, entries);
      },
      state: (state) => {
        this.logLive = state;
      },
      open: () => void this.loadLog(lastSeq(this.log)),
    });
    this.logSocket.start();
  }

  async loadLog(since = 0): Promise<void> {
    try {
      const entries = await api.rpcLog(since);
      if (entries === null) {
        this.logAvailable = false;
        return;
      }
      this.logAvailable = true;
      this.log = mergeEntries(this.log, entries);
    } catch {
      this.logAvailable = this.logAvailable ?? false;
    }
  }

  clearLog(): void {
    this.log = [];
  }

  async refreshStatus(): Promise<void> {
    try {
      this.status = await api.status();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) this.auth = "unpaired";
    }
  }

  async refreshDevices(): Promise<void> {
    try {
      this.devices = sortDevices(await api.devices());
      this.devicesLoaded = true;
      for (const id of Object.keys(this.views)) {
        if (this.devices.some((device) => device.id === id)) void this.refreshDevice(id);
      }
    } catch {
      this.devicesLoaded = true;
    }
  }

  async refreshDevice(id: string): Promise<DeviceView | null> {
    try {
      const view = await api.device(id);
      this.views = { ...this.views, [id]: view };
      return view;
    } catch {
      return null;
    }
  }

  async refreshConfirmations(): Promise<void> {
    try {
      this.confirmations = await api.confirmations();
    } catch {
      return;
    }
  }

  private onHubEvent(event: HubEvent): void {
    if (event.type === "reading" && typeof event.device === "string") {
      const view = this.views[event.device];
      if (view) this.views = { ...this.views, [event.device]: applyReading(view, event as unknown as ReadingEvent) };
      return;
    }
    if (event.type === "state") {
      this.schedule("devices", "status");
      return;
    }
    if (event.type === "audit") {
      this.auditTick += 1;
      const name = String(event.event ?? "");
      if (name.startsWith("routine")) this.routineTick += 1;
      this.schedule("status", "confirmations");
      if (typeof event.device === "string" && this.views[event.device]) this.pending.add(`device:${event.device}`);
      if (["stop", "unlock", "connect", "safe_state", "writer_finish"].includes(name)) this.schedule("devices");
      return;
    }
    if (event.type === "watchdog") this.schedule("devices", "status");
  }

  private schedule(...keys: string[]): void {
    for (const key of keys) this.pending.add(key);
    if (this.flushTimer) return;
    this.flushTimer = setTimeout(() => {
      this.flushTimer = null;
      const keys = [...this.pending];
      this.pending.clear();
      if (keys.includes("status")) void this.refreshStatus();
      if (keys.includes("devices")) void this.refreshDevices();
      if (keys.includes("confirmations")) void this.refreshConfirmations();
      for (const key of keys) if (key.startsWith("device:")) void this.refreshDevice(key.slice(7));
    }, 150);
  }

  async stop(): Promise<void> {
    this.stopError = null;
    try {
      await api.stop("stopped from the Inspector");
    } catch (error) {
      this.stopError = error instanceof Error ? error.message : "The stop request failed.";
    }
    await Promise.all([this.refreshStatus(), this.refreshDevices()]);
  }

  async unlock(phrase: string): Promise<string | null> {
    try {
      await api.unlock(phrase);
    } catch (error) {
      return error instanceof Error ? error.message : "The hub refused to unlock.";
    }
    await Promise.all([this.refreshStatus(), this.refreshDevices()]);
    return null;
  }
}

export const inspector = new Inspector();
