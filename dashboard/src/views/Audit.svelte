<script lang="ts">
  import { Button } from "$lib/components/ui/button/index.js";
  import * as Table from "$lib/components/ui/table/index.js";
  import * as Tooltip from "$lib/components/ui/tooltip/index.js";
  import SelectField from "../components/SelectField.svelte";
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
        <Tooltip.Root>
          <Tooltip.Trigger>
            {#snippet child({ props })}
              <Button {...props} size="sm" onclick={check}>Verify the hash chain</Button>
            {/snippet}
          </Tooltip.Trigger>
          <Tooltip.Content>The hub computes each entry's hash again and checks that each entry carries the hash of the entry before it.</Tooltip.Content>
        </Tooltip.Root>
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
      <SelectField
        id="audit-device"
        label="Device"
        bind:value={device}
        triggerClass="min-w-[16ch]"
        options={[{ value: "", label: "All devices" }, ...inspector.devices.map((item) => ({ value: item.id, label: item.id }))]}
      />
      <SelectField
        id="audit-status"
        label="Status"
        bind:value={status}
        triggerClass="min-w-[16ch]"
        options={[{ value: "", label: "All statuses" }, ...statuses.map((item) => ({ value: item, label: item }))]}
      />
      <SelectField
        id="audit-event"
        label="Event"
        bind:value={event}
        triggerClass="min-w-[16ch]"
        options={[{ value: "", label: "All events" }, ...seenEvents.map((item) => ({ value: item, label: item }))]}
      />
    </div>
  </header>

  <section class="section" aria-label="Entries">
    {#if error}
      <p class="problem" role="alert">{error}</p>
    {:else if loaded && !entries.length}
      <p class="empty">No entries match these filters.</p>
    {:else}
      <Table.Root region="Audit entries table" class="audit">
        <Table.Header>
          <Table.Row>
            <Table.Head scope="col" class="pl-3">Seq</Table.Head>
            <Table.Head scope="col">Time</Table.Head>
            <Table.Head scope="col">Event</Table.Head>
            <Table.Head scope="col">By</Table.Head>
            <Table.Head scope="col">Target</Table.Head>
            <Table.Head scope="col">Status</Table.Head>
          </Table.Row>
        </Table.Header>
        {#each entries as entry (entry.seq)}
          {@const who = principalInfo(entry.principal)}
          {@const mark = auditStatus(entry.status ?? "")}
          {@const registry = fromKernelCode(entry.code)}
          {@const text = reason(entry)}
          {@const more = extra(entry)}
          {@const target = [entry.device, entry.target].filter(Boolean).join(" ")}
          <Table.Body class="entry {who.kind} tone-{mark.tone}{mark.tone === 'blocked' ? ' blocked' : ''}{text || more ? ' has-more' : ''}">
            <Table.Row class="main">
              <Table.Cell class="seq"><span class="key">seq</span> {entry.seq}</Table.Cell>
              <Table.Cell class="time"><span class="key">time</span> {formatDateTime(entry.at)}</Table.Cell>
              <Table.Cell class="cell event"><span class="key">event</span> <span class="mono">{entry.event}</span></Table.Cell>
              <Table.Cell class="cell principal"><span class="key">by</span> <span class="mono nobreak">{entry.principal}</span></Table.Cell>
              <Table.Cell class="cell target{target ? '' : ' none'}"><span class="key">target</span> <span class="mono"><Prose text={target} /></span></Table.Cell>
              <Table.Cell class="cell status{!entry.status && !entry.code ? ' none' : ''}">
                <span class="key">status</span>
                <span class="marks">
                  {#if entry.status}<StatusMark tone={mark.tone} label={mark.label} />{/if}
                  {#if registry}
                    <span class="mono code">{registry.code} {registry.name}</span>
                  {:else if entry.code}
                    <span class="mono code">{entry.code}</span>
                  {/if}
                </span>
              </Table.Cell>
            </Table.Row>
            {#if text || more}
              <Table.Row class="more">
                <Table.Cell colspan={2} class="pad"></Table.Cell>
                <Table.Cell colspan={4}>
                  <div class="notes">
                    {#if text}<p class="reason"><Reason {text} code={identifiersOf(entry.device, entry.target)} /></p>{/if}
                    {#if more}<span class="details"><Json value={stripImageData(more)} limit={600} /></span>{/if}
                  </div>
                </Table.Cell>
              </Table.Row>
            {/if}
          </Table.Body>
        {/each}
      </Table.Root>
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

  .view :global(table.audit) {
    font-size: var(--t-mono);
  }

  .view :global(.entry td) {
    border-bottom: 0;
    padding-top: var(--s-2);
    padding-bottom: var(--s-2);
    vertical-align: baseline;
  }

  .view :global(.entry.has-more tr.main td) {
    padding-bottom: 2px;
  }

  .view :global(.entry tr.more td) {
    padding-top: 0;
  }

  .view :global(.entry td:first-child) {
    padding-left: var(--s-3);
  }

  .view :global(tbody.entry) {
    border-top: 2px solid var(--bg);
    border-left: 2px solid transparent;
  }

  .view :global(tbody.entry.agent) {
    border-left: 2px dashed var(--text-2);
  }

  .view :global(tbody.entry.human) {
    border-left: 2px solid var(--text);
    background: var(--surface);
  }

  .view :global(tbody.entry.agent.blocked) {
    border-left-color: var(--blocked);
  }

  .view :global(.entry .seq),
  .view :global(.entry .time) {
    font-family: var(--font-mono);
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
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

  .view :global(.tone-blocked .code) {
    color: var(--blocked);
  }

  .view :global(.tone-confirm .code) {
    color: var(--confirm);
  }

  .notes {
    display: grid;
    gap: 2px;
  }

  .reason {
    font-size: var(--t-ui);
  }

  @media (max-width: 1023px) {
    .view :global(table.audit thead) {
      display: none;
    }

    .view :global(table.audit),
    .view :global(tbody.entry),
    .view :global(tbody.entry tr) {
      display: block;
    }

    .view :global(tbody.entry) {
      padding: var(--s-2) var(--s-3);
      border-top: 0;
      margin-bottom: 2px;
    }

    .view :global(tbody.entry tr.main) {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      row-gap: var(--s-1);
    }

    .view :global(tbody.entry td),
    .view :global(.entry td:first-child) {
      padding: 0;
    }

    .view :global(.entry .seq) {
      color: var(--text);
      font-weight: 700;
    }

    .view :global(.entry .time) {
      text-align: right;
    }

    .view :global(.entry .cell) {
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: 7ch minmax(0, 1fr);
      column-gap: var(--s-3);
      align-items: baseline;
    }

    .view :global(.entry .cell.none),
    .view :global(.entry .pad) {
      display: none;
    }

    .notes {
      padding-top: var(--s-1);
    }

    .view :global(.entry .cell .key) {
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
  }
</style>
