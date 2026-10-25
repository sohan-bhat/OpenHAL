export type Tone = "ok" | "confirm" | "blocked" | "unverified" | "neutral" | "pending";

export interface StatusWord {
  tone: Tone;
  label: string;
}

export function verificationStatus(status: string): StatusWord {
  if (status === "verified-on-hardware") return { tone: "ok", label: "verified on hardware" };
  if (status === "tested-reads") return { tone: "unverified", label: "reads tested, writes unverified" };
  return { tone: "unverified", label: "unverified" };
}

export function connectionStatus(device: { connected: boolean }): StatusWord {
  return device.connected ? { tone: "ok", label: "connected" } : { tone: "neutral", label: "not connected" };
}

export function unavailableReason(device: { connected: boolean; unavailable: string | null }): string | null {
  if (!device.unavailable || (!device.connected && device.unavailable === "not connected")) return null;
  return device.unavailable;
}

export function confirmTier(tier: string | null | undefined): StatusWord {
  if (tier === "confirm-each-time") return { tone: "confirm", label: "confirmation required each time" };
  if (tier === "confirm") return { tone: "confirm", label: "confirmation required" };
  return { tone: "neutral", label: "no confirmation" };
}

export function decisionStatus(status: string): StatusWord {
  switch (status) {
    case "done":
    case "ok":
    case "approved":
      return { tone: "ok", label: status === "approved" ? "approved" : status === "ok" ? "ok" : "granted" };
    case "allowed":
      return { tone: "ok", label: "allowed" };
    case "pending":
    case "needs_confirmation":
      return { tone: "confirm", label: "confirmation required" };
    case "blocked":
      return { tone: "blocked", label: "blocked" };
    case "failed":
      return { tone: "blocked", label: "failed" };
    case "rejected":
      return { tone: "neutral", label: "rejected" };
    case "expired":
      return { tone: "neutral", label: "expired" };
    case "cancelled":
      return { tone: "neutral", label: "cancelled" };
    case "running":
      return { tone: "pending", label: "running" };
    default:
      return { tone: "neutral", label: status || "recorded" };
  }
}

export function hazardLabel(hazard: string): string {
  return `${hazard} hazard`;
}

export function auditStatus(status: string): StatusWord {
  if (status === "done") return { tone: "ok", label: "done" };
  return decisionStatus(status);
}
