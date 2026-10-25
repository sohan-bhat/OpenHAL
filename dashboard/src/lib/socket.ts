import { wsUrl } from "./api";

export type SocketState = "connecting" | "open" | "closed";

export interface SocketHandlers {
  message: (data: unknown) => void;
  state: (state: SocketState) => void;
  open?: () => void;
}

export class LiveSocket {
  private socket: WebSocket | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private delay = 1000;
  private stopped = false;

  constructor(
    private readonly path: string | (() => string),
    private readonly handlers: SocketHandlers,
  ) {}

  start(): void {
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.socket?.close();
    this.socket = null;
  }

  private connect(): void {
    this.handlers.state("connecting");
    let socket: WebSocket;
    try {
      socket = new WebSocket(wsUrl(typeof this.path === "string" ? this.path : this.path()));
    } catch {
      this.retry();
      return;
    }
    this.socket = socket;
    socket.addEventListener("open", () => {
      this.delay = 1000;
      this.handlers.state("open");
      this.handlers.open?.();
    });
    socket.addEventListener("message", (event) => {
      let data: unknown = event.data;
      if (typeof data === "string") {
        try {
          data = JSON.parse(data);
        } catch {
          return;
        }
      }
      this.handlers.message(data);
    });
    socket.addEventListener("close", () => {
      if (this.socket === socket) this.socket = null;
      this.handlers.state("closed");
      this.retry();
    });
  }

  private retry(): void {
    if (this.stopped) return;
    this.timer = setTimeout(() => this.connect(), this.delay);
    this.delay = Math.min(this.delay * 2, 10000);
  }
}
