import { api, ApiError } from "./api";
import { applyReading, sortDevices, type ReadingEvent } from "./devices";
import { lastSeq, mergeEntries, parseLiveFrame } from "./logstore";
import { router } from "./router.svelte";
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

function same(next: unknown, current: unknown): boolean {
  return current !== undefined && current !== null && JSON.stringify(next) === JSON.stringify(current);
}

class Inspector {
  auth = $state<AuthState>("checking");
  ready = $state(false);
  settled = $state(false);
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
  private holds = 0;

  async boot(): Promise<void> {
    const routed = router.route.view === "devices" ? router.route.id : null;
    const first = Promise.all([
      this.refreshStatus(),
      this.refreshDevices(),
      this.refreshConfirmations(),
      this.loadLog(),
      routed ? this.refreshDevice(routed) : null,
    ]);
    try {
      this.you = await api.whoami();
      this.auth = "paired";
    } catch (error) {
      this.auth = error instanceof ApiError && error.status === 401 ? "unpaired" : "offline";
      if (this.auth === "offline") setTimeout(() => void this.boot(), 3000);
      return;
    }
    await first;
    await this.loadSelected();
    this.ready = true;
    this.startSockets();
    this.pollTimer = setInterval(() => {
      void this.refreshStatus();
      void this.refreshConfirmations();
    }, 5000);
  }

  hold(): () => void {
    this.holds += 1;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      this.holds -= 1;
      this.trySettle();
    };
  }

  trySettle(): void {
    if (this.ready && this.holds === 0 && !this.settled) this.settled = true;
  }

  private async loadSelected(): Promise<void> {
    if (router.route.view !== "devices") return;
    const id = router.route.id ?? this.devices[0]?.id;
    if (id && !this.views[id] && this.devices.some((device) => device.id === id)) await this.refreshDevice(id);
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
    this.logSocket = new LiveSocket(() => `/v1/rpc/log/live?since=${lastSeq(this.log)}`, {
      message: (data) => {
        const entries = parseLiveFrame(data);
        if (entries.length) this.log = mergeEntries(this.log, entries);
      },
      state: (state) => {
        this.logLive = state;
      },
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
      const status = await api.status();
      if (!same(status, this.status)) this.status = status;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) this.auth = "unpaired";
    }
  }

  async refreshDevices(): Promise<void> {
    try {
      const devices = sortDevices(await api.devices());
      if (!same(devices, this.devices)) this.devices = devices;
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
      if (same(view, this.views[id])) return this.views[id] ?? view;
      this.views = { ...this.views, [id]: view };
      return view;
    } catch {
      return null;
    }
  }

  async refreshConfirmations(): Promise<void> {
    try {
      const confirmations = await api.confirmations();
      if (!same(confirmations, this.confirmations)) this.confirmations = confirmations;
    } catch {
      return;
    }
  }

  private onHubEvent(event: HubEvent): void {
    if (event.type === "reading" && typeof event.device === "string") {
      const view = this.views[event.device];
      if (!view) return;
      const next = applyReading(view, event as unknown as ReadingEvent);
      if (next !== view) this.views = { ...this.views, [event.device]: next };
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
