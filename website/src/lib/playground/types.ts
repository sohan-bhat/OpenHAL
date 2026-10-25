import type { TraceEntry } from "../trace";

export interface Exchange {
  key: number;
  who: "agent" | "person";
  client: string;
  entries: TraceEntry[];
}
