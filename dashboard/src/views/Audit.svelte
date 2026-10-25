<script lang="ts">
  import Json from "../components/Json.svelte";
  import StatusMark from "../components/StatusMark.svelte";
  import { api } from "../lib/api";
  import { fromKernelCode } from "../lib/protocol";
  import { inspector } from "../lib/state.svelte";
  import { auditStatus } from "../lib/status";
  import { principalInfo } from "../lib/trace";
  import type { AuditEntry } from "../lib/types";

  let device = $state("");
  let status = $state("");
  let event = $state("");
  let entries = $state<AuditEntry[]>([]);
  let loaded = $state(false);
  let error = $state<string | null>(null);
  let verify = $state<{ ok: boolean; broken_at: number | null; head: string | null } | null>(null);
  let seenEvents = $state<string[]>([]);

  const statuses = ["done", "blocked", "failed", "pending", "needs_confirmation", "allowed"];

  $effect(() => {
    void inspector.auditTick;
    const filters = { device, status, event };
    void load(filters);
  });

  let timer: ReturnType<typeof setTimeout> | null = null;
  async function load(filters: { device: string; status: string; event: string }) {
    if (timer) clearTimeout(timer);
    await new Promise<void>((resolve) => (timer = setTimeout(resolve, 120)));
    try {
      entries = await api.audit({ ...filters, limit: 200 });
      error = null;
      const names = new Set([...seenEvents, ...entries.map((entry) => entry.event)]);
      seenEvents = [...names].sort();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "The audit log did not load.";
    }
    loaded = true;
  }

  async function check() {
    verify = await api.auditVerify();
  }

  function when(at: number): string {
    const date = new Date(at * 1000);
    const pad = (value: number) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  }

  function reason(entry: AuditEntry): string | null {
    const message = entry.details.message;
    return typeof message === "string" ? message : null;
  }

  function extra(entry: AuditEntry): Record<string, unknown> | null {
    const { message: _message, ...rest } = entry.details;
    return Object.keys(rest).length ? rest : null;
  }
</script>

<div class="view">
  <header class="section">
    <div class="section-head">
      <h1>Audit log</h1>
      <div class="verify">
        <button class="button small" type="button" onclick={check}>Verify the hash chain</button>
        {#if verify}
          <span aria-live="polite">
            {#if verify.ok}
              <StatusMark tone="ok" label="chain intact" />
            {:else}
              <StatusMark tone="blocked" label="chain broken at seq {verify.broken_at}" />
            {/if}
          </span>
        {/if}
      </div>
    </div>
    <p class="muted">Every decision the hub made, newest first. Each entry is hashed with the one before it.</p>
    <div class="filters" role="group" aria-label="Filter the audit log">
      <label class="field">
        <span>Device</span>
        <select bind:value={device}>
          <option value="">All devices</option>
          {#each inspector.devices as item (item.id)}<option value={item.id}>{item.id}</option>{/each}
        </select>
      </label>
      <label class="field">
        <span>Status</span>
        <select bind:value={status}>
          <option value="">All statuses</option>
          {#each statuses as item (item)}<option value={item}>{item}</option>{/each}
        </select>
      </label>
      <label class="field">
        <span>Event</span>
        <select bind:value={event}>
          <option value="">All events</option>
          {#each seenEvents as item (item)}<option value={item}>{item}</option>{/each}
        </select>
      </label>
    </div>
  </header>

  <section class="section" aria-label="Entries">
    {#if error}
      <p class="problem" role="alert">{error}</p>
    {:else if loaded && !entries.length}
      <p class="empty">No entries match these filters.</p>
    {:else}
      <ol class="entries">
        {#each entries as entry (entry.seq)}
          {@const who = principalInfo(entry.principal)}
          {@const mark = auditStatus(entry.status ?? "")}
          {@const registry = fromKernelCode(entry.code)}
          {@const text = reason(entry)}
          {@const more = extra(entry)}
          <li class="entry {who.kind}" class:blocked={entry.status === "blocked" || entry.status === "failed"}>
            <span class="seq mono">{entry.seq}</span>
            <span class="time mono">{when(entry.at)}</span>
            <span class="event mono">{entry.event}</span>
            <span class="principal mono">{entry.principal}</span>
            <span class="target mono">{[entry.device, entry.target].filter(Boolean).join(" ")}</span>
            <span class="status">
              {#if entry.status}<StatusMark tone={mark.tone} label={mark.label} />{/if}
              {#if registry}
                <span class="mono code" class:error={entry.status === "blocked" || entry.status === "failed"}>{registry.code} {registry.name}</span>
              {:else if entry.code}
                <span class="mono">{entry.code}</span>
              {/if}
            </span>
            {#if text}<span class="reason mono">{text}</span>{/if}
            {#if more}<span class="details"><Json value={more} limit={600} /></span>{/if}
          </li>
        {/each}
      </ol>
    {/if}
  </section>
</div>

<style>
  .view {
    display: grid;
    max-width: 1200px;
  }

  .verify {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--s-3);
  }

  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-3);
  }

  .entries {
    margin: 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 2px;
  }

  .entry {
    display: grid;
    grid-template-columns: 5ch 19ch 15ch minmax(14ch, 20ch) minmax(22ch, 1fr) minmax(20ch, 28ch);
    column-gap: var(--s-3);
    row-gap: 2px;
    align-items: baseline;
    padding: var(--s-2) var(--s-3);
    border-left: 2px solid transparent;
    font-size: var(--t-mono);
  }

  .entry.agent {
    border-left: 2px dashed var(--text-2);
  }

  .entry.human {
    border-left: 2px solid var(--text);
    background: var(--surface);
  }

  .entry.blocked {
    border-left: 3px solid var(--blocked);
  }

  .seq,
  .time {
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }

  .principal,
  .target {
    overflow-wrap: anywhere;
  }

  .status {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-2);
  }

  .code.error {
    color: var(--blocked);
    font-weight: 700;
  }

  .reason,
  .details {
    grid-column: 3 / -1;
  }

  .entry.blocked .reason {
    font-weight: 700;
  }

  @media (max-width: 1023px) {
    .entry {
      grid-template-columns: 6ch minmax(0, 1fr);
    }

    .entry > :nth-child(n + 3) {
      grid-column: 1 / -1;
    }

    .time {
      grid-column: 2;
    }
  }
</style>
