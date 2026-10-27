<script lang="ts">
  import Json from "../components/Json.svelte";
  import Prose from "../components/Prose.svelte";
  import Reason from "../components/Reason.svelte";
  import StatusMark from "../components/StatusMark.svelte";
  import { api } from "../lib/api";
  import { stripImageData } from "../lib/images";
  import { formatDateTime, identifiersOf } from "../lib/units";
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

  const settle = inspector.hold();
  let timer: ReturnType<typeof setTimeout> | null = null;
  async function load(filters: { device: string; status: string; event: string }) {
    if (timer) clearTimeout(timer);
    if (loaded) await new Promise<void>((resolve) => (timer = setTimeout(resolve, 120)));
    try {
      entries = await api.audit({ ...filters, limit: 200 });
      error = null;
      const names = new Set([...seenEvents, ...entries.map((entry) => entry.event)]);
      seenEvents = [...names].sort();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "The audit log did not load.";
    }
    loaded = true;
    settle();
  }

  async function check() {
    verify = await api.auditVerify();
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
      <div class="columns" aria-hidden="true">
        <span>Seq</span><span>Time</span><span>Event</span><span>By</span><span>Target</span><span>Status</span>
      </div>
      <ol class="entries">
        {#each entries as entry (entry.seq)}
          {@const who = principalInfo(entry.principal)}
          {@const mark = auditStatus(entry.status ?? "")}
          {@const registry = fromKernelCode(entry.code)}
          {@const text = reason(entry)}
          {@const more = extra(entry)}
          {@const target = [entry.device, entry.target].filter(Boolean).join(" ")}
          <li class="entry {who.kind} tone-{mark.tone}" class:blocked={mark.tone === "blocked"}>
            <span class="seq mono"><span class="key">seq</span> {entry.seq}</span>
            <span class="time mono"><span class="key">time</span> {formatDateTime(entry.at)}</span>
            <span class="cell event"><span class="key">event</span> <span class="mono">{entry.event}</span></span>
            <span class="cell principal"><span class="key">by</span> <span class="mono nobreak">{entry.principal}</span></span>
            <span class="cell target" class:none={!target}><span class="key">target</span> <span class="mono"><Prose text={target} /></span></span>
            <span class="cell status" class:none={!entry.status && !entry.code}>
              <span class="key">status</span>
              <span class="marks">
                {#if entry.status}<StatusMark tone={mark.tone} label={mark.label} />{/if}
                {#if registry}
                  <span class="mono code">{registry.code} {registry.name}</span>
                {:else if entry.code}
                  <span class="mono code">{entry.code}</span>
                {/if}
              </span>
            </span>
            {#if text}<p class="reason"><Reason {text} code={identifiersOf(entry.device, entry.target)} /></p>{/if}
            {#if more}<span class="details"><Json value={stripImageData(more)} limit={600} /></span>{/if}
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

  .columns,
  .entry {
    display: grid;
    grid-template-columns: 5ch 19ch 15ch minmax(14ch, 20ch) minmax(22ch, 1fr) minmax(24ch, 30ch);
    column-gap: var(--s-3);
  }

  .columns {
    padding: 0 var(--s-3) var(--s-2) calc(var(--s-3) + 2px);
    font-size: var(--t-label);
    font-weight: 700;
    color: var(--text-2);
  }

  .entries {
    margin: 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 2px;
  }

  .entry {
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

  .entry.agent.blocked {
    border-left-color: var(--blocked);
  }

  .key {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
  }

  .seq,
  .time {
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
  }

  .marks {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-2);
  }

  .code {
    font-weight: 700;
    white-space: nowrap;
    color: var(--text-2);
  }

  .tone-blocked .code {
    color: var(--blocked);
  }

  .tone-confirm .code {
    color: var(--confirm);
  }

  .reason,
  .details {
    grid-column: 3 / -1;
  }

  .reason {
    font-size: var(--t-ui);
  }

  @media (max-width: 1023px) {
    .columns {
      display: none;
    }

    .entry {
      grid-template-columns: minmax(0, 1fr) auto;
      row-gap: var(--s-1);
    }

    .seq {
      color: var(--text);
      font-weight: 700;
    }

    .time {
      text-align: right;
    }

    .cell {
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: 7ch minmax(0, 1fr);
      column-gap: var(--s-3);
      align-items: baseline;
    }

    .cell.none {
      display: none;
    }

    .cell .key {
      position: static;
      width: auto;
      height: auto;
      margin: 0;
      overflow: visible;
      clip: auto;
      font-family: var(--font-text);
      font-size: var(--t-label);
      font-weight: 700;
      font-variant-caps: all-small-caps;
      letter-spacing: 0.04em;
      color: var(--text-2);
    }

    .reason,
    .details {
      grid-column: 1 / -1;
    }
  }
</style>
