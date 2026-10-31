<script lang="ts">
  import Prose from "./Prose.svelte";
  import { onMount, tick } from "svelte";
  import { SvelteSet } from "svelte/reactivity";
  import { isValueNotification } from "../lib/logstore";
  import { inspector } from "../lib/state.svelte";
  import {
    buildTrace,
    filterOptions,
    filterRows,
    formatTime,
    NO_FILTERS,
    plainTrace,
    stringifyCompact,
    type TraceFilters,
    type TraceRow,
  } from "../lib/trace";
  import Json from "./Json.svelte";
  import StatusMark from "./StatusMark.svelte";
  import TraceArrow from "./TraceArrow.svelte";

  let { collapsed = false, ontoggle }: { collapsed?: boolean; ontoggle?: () => void } = $props();

  let filters = $state<TraceFilters>({ ...NO_FILTERS });
  let showValues = $state(false);
  let copied = $state(false);
  let scroller = $state<HTMLElement | null>(null);
  let follow = $state(true);
  let announcement = $state("");

  const entries = $derived(showValues ? inspector.log : inspector.log.filter((entry) => !isValueNotification(entry)));
  const rows = $derived(buildTrace(entries));
  const options = $derived(filterOptions(rows));
  const PAGE = 400;
  const SHORT = 240;
  const expanded = new SvelteSet<number>();
  let shown = $state(PAGE);
  const matching = $derived(filterRows(rows, filters));
  const visible = $derived(matching.length > shown ? matching.slice(matching.length - shown) : matching);
  const hidden = $derived(matching.length - visible.length);
  const filtered = $derived(Object.values(filters).some(Boolean));
  const host = typeof location === "undefined" ? "127.0.0.1:7420" : location.host;
  const live = $derived(
    inspector.logLive === "open"
      ? ({ tone: "ok", label: "live" } as const)
      : inspector.logLive === "connecting"
        ? ({ tone: "pending", label: "connecting" } as const)
        : ({ tone: "neutral", label: "reconnecting" } as const),
  );

  const outcomes: { value: string; label: string }[] = [
    { value: "granted", label: "result" },
    { value: "pending", label: "confirmation required" },
    { value: "error", label: "error" },
    { value: "notification", label: "notification" },
    { value: "open", label: "no response yet" },
  ];

  let painted = $state(false);

  onMount(() => {
    let timer = 0;
    const frame = requestAnimationFrame(() => {
      timer = window.setTimeout(() => (painted = true), 0);
    });
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timer);
    };
  });

  let lastAnnounced = 0;
  $effect(() => {
    const blocked = rows.filter((row) => row.kind === "error" && row.seq > lastAnnounced);
    if (rows.length) lastAnnounced = rows[rows.length - 1]!.seq;
    const latest = blocked[blocked.length - 1];
    if (latest) announcement = `${latest.client} ${latest.method ?? ""} got ${latest.head}`;
  });

  $effect(() => {
    void matching[matching.length - 1]?.seq;
    if (!follow || !scroller) return;
    void tick().then(() => {
      if (scroller) scroller.scrollTop = scroller.scrollHeight;
    });
  });

  function onScroll() {
    if (!scroller) return;
    follow = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 48;
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(plainTrace(matching));
      copied = true;
      setTimeout(() => (copied = false), 2000);
    } catch {
      copied = false;
    }
  }

  function principalClass(row: TraceRow): string {
    return row.principal.kind === "human" ? "human" : row.principal.kind === "agent" ? "agent" : "other";
  }
</script>

<section class="log" class:collapsed aria-labelledby="log-title">
  <div class="log-head">
    <div class="title">
      <h2 id="log-title" tabindex="-1">Message log</h2>
      {#if inspector.logAvailable}<StatusMark tone={live.tone} label={live.label} />{/if}
      <span class="muted count">{matching.length} of {rows.length} messages</span>
      {#if ontoggle}
        <button type="button" class="button small toggle" aria-expanded={!collapsed} aria-controls="log-body" onclick={ontoggle}>
          {collapsed ? "Show the log" : "Hide the log"}
        </button>
      {/if}
    </div>
    {#if !collapsed}
    <div class="filters" role="group" aria-label="Filter the message log">
      <label class="field">
        <span>Client</span>
        <select bind:value={filters.client}>
          <option value="">All clients</option>
          {#each options.clients as client (client)}<option value={client}>{client}</option>{/each}
        </select>
      </label>
      <label class="field">
        <span>Device</span>
        <select bind:value={filters.device}>
          <option value="">All devices</option>
          {#each options.devices as device (device)}<option value={device}>{device}</option>{/each}
        </select>
      </label>
      <label class="field">
        <span>Method</span>
        <select bind:value={filters.method}>
          <option value="">All methods</option>
          {#each options.methods as method (method)}<option value={method}>{method}</option>{/each}
        </select>
      </label>
      <label class="field">
        <span>Outcome</span>
        <select bind:value={filters.outcome}>
          <option value="">All outcomes</option>
          {#each outcomes as outcome (outcome.value)}<option value={outcome.value}>{outcome.label}</option>{/each}
        </select>
      </label>
      <label class="check">
        <input type="checkbox" bind:checked={showValues} />
        <span>Show <code>hal/value</code></span>
      </label>
      <button type="button" class="button small" onclick={copy} disabled={!visible.length}>
        {copied ? "Copied as text" : "Copy as text"}
      </button>
    </div>
    {/if}
  </div>

  <div class="visually-hidden" aria-live="polite">{announcement}</div>

  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <div class="scroller" id="log-body" hidden={collapsed} bind:this={scroller} onscroll={onScroll} tabindex="0" role="region" aria-label="Messages">
    {#if inspector.logAvailable === false}
      <p class="empty">
        This hub does not serve the message log. It needs <code>GET /v1/rpc/log</code> and the live feed at
        <code>/v1/rpc/log/live</code>.
      </p>
    {:else if !rows.length}
      <p class="empty">
        No messages yet. Clients connect to <code>ws://{host}/rpc</code> and send <code>hal/initialize</code>.
      </p>
    {:else if !matching.length}
      <div class="empty filters-empty">
        <p>No messages match these filters.</p>
        <button type="button" class="button small" onclick={() => (filters = { ...NO_FILTERS })}>Clear filters</button>
      </div>
    {:else}
      {#if hidden > 0}
        <button type="button" class="button small older" onclick={() => (shown += PAGE)}>
          Show {Math.min(hidden, PAGE)} older messages
        </button>
      {/if}
      <ol class="trace" aria-label="JSON-RPC messages, oldest first" translate="no">
        {#each painted ? visible : [] as row (row.seq)}
          <li class="row appear {principalClass(row)}" class:start={row.startsExchange} data-kind={row.kind} data-seq={row.seq}>
            <span class="who">
              <span class="time mono">{formatTime(row.at)}</span>
              <span class="client mono">{row.client}</span>
            </span>
            <span class="arrow"><TraceArrow arrow={row.arrow} /></span>
            <span class="head mono tone-{row.tone}">
              {#if row.kind === "error"}
                <span class="word">error</span> <span class="code">{row.errorCode}</span>
                {#if row.errorName}<span class="name">{row.errorName}</span>{/if}
              {:else}
                {row.head}
              {/if}
            </span>
            <span class="payload">
              {#if row.hasPayload}
                {@const short = row.kind === "notification" ? SHORT / 2 : SHORT}
                {@const long = row.summary !== undefined || stringifyCompact(row.payload).length > short}
                {#if row.summary !== undefined && !expanded.has(row.seq)}
                  <Json value={row.summary} />
                {:else}
                  <Json value={row.payload} limit={long && !expanded.has(row.seq) ? short : 100000} />
                {/if}
                {#if long}
                  <button
                    type="button"
                    class="more"
                    aria-expanded={expanded.has(row.seq)}
                    onclick={() => (expanded.has(row.seq) ? expanded.delete(row.seq) : expanded.add(row.seq))}
                  >
                    {expanded.has(row.seq) ? "Show less" : "Show the whole message"}
                  </button>
                {/if}
              {/if}
              {#if row.tone === "pending"}<StatusMark tone="confirm" label="confirmation required" compact />{/if}
              {#if row.kind === "notification" && row.errorName}
                <span class="mono inline-error"><span class="code">{row.errorCode}</span> <span class="name">{row.errorName}</span></span>
              {/if}
            </span>
            {#if row.reason}<span class="reason mono"><Prose text={row.reason} /></span>{/if}
          </li>
        {/each}
      </ol>
    {/if}
  </div>
</section>

<style>
  .log {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    min-height: 0;
    height: 100%;
    background: var(--surface);
  }

  .log.collapsed {
    grid-template-rows: auto;
    height: auto;
  }

  .log.collapsed .log-head {
    border-bottom: 0;
  }

  .scroller[hidden] {
    display: none;
  }

  .toggle {
    margin-left: var(--s-2);
  }

  .log-head {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    justify-content: space-between;
    gap: var(--s-2) var(--s-5);
    padding: var(--s-3) var(--s-5);
    border-bottom: var(--rule);
    background: var(--bg);
  }

  .title {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-2) var(--s-3);
  }

  .count {
    font-size: var(--t-label);
    font-variant-numeric: tabular-nums;
  }

  .filters {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: var(--s-2) var(--s-3);
  }

  .filters select {
    min-height: 32px;
    max-width: 200px;
    font-size: var(--t-label);
  }

  .check {
    display: inline-flex;
    align-items: center;
    gap: var(--s-1);
    min-height: 32px;
    font-size: var(--t-label);
  }

  .check input {
    accent-color: var(--accent);
  }

  .scroller {
    overflow: auto;
    min-height: 0;
    padding: var(--s-2) var(--s-5) var(--s-4);
  }

  .scroller:focus-visible {
    outline-offset: -2px;
  }

  .empty {
    margin: var(--s-3) 0;
    background: var(--bg);
  }

  .filters-empty {
    display: grid;
    gap: var(--s-2);
    justify-items: start;
  }

  .older {
    margin: var(--s-2) 0;
  }

  .trace {
    display: grid;
    grid-template-columns: 12.5ch minmax(8ch, 14ch) 22px minmax(9ch, max-content) minmax(0, 1fr);
    column-gap: var(--s-3);
    margin: 0;
    padding: 0;
    list-style: none;
    font-family: var(--font-mono);
    font-size: var(--t-mono);
  }

  .row {
    display: grid;
    grid-column: 1 / -1;
    grid-template-columns: subgrid;
    align-items: baseline;
    padding: 3px var(--s-3);
    line-height: 1.55;
  }

  .row.start {
    margin-top: var(--s-3);
  }

  .row.agent {
    border-left: 2px dashed var(--text-2);
  }

  .row.human {
    border-left: 2px solid var(--text);
    background: var(--bg);
  }

  .row.other {
    border-left: 2px solid transparent;
  }

  .who {
    display: contents;
  }

  .time {
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
    font-size: var(--t-label);
  }

  .client {
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .arrow {
    align-self: start;
    display: inline-flex;
    padding-top: 0.42em;
  }

  .head {
    white-space: nowrap;
  }

  .row[data-kind="error"] .head {
    grid-column: 4 / 6;
  }

  .tone-method {
    color: var(--syn-method);
    font-weight: 700;
  }

  .tone-result {
    color: var(--ok);
    font-weight: 700;
  }

  .tone-pending {
    color: var(--confirm);
    font-weight: 700;
  }

  .tone-error,
  .inline-error {
    color: var(--syn-error);
    font-weight: 700;
  }

  .tone-plain {
    color: var(--text-2);
  }

  .payload {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-1) var(--s-3);
    min-width: 0;
  }

  .more {
    padding: 0;
    border: 0;
    background: none;
    color: var(--accent);
    font: inherit;
    font-family: var(--font-text);
    font-size: var(--t-label);
    text-decoration: underline;
    text-underline-offset: 2px;
    cursor: pointer;
  }

  .reason {
    grid-column: 5;
    color: var(--text);
  }

  @media (max-width: 1023px) {
    .log-head,
    .scroller {
      padding-inline: var(--s-4);
    }

    .trace {
      grid-template-columns: 30px minmax(0, 1fr);
      column-gap: 0;
    }

    .row {
      grid-template-columns: 30px minmax(0, 1fr);
      column-gap: 0;
      row-gap: 2px;
    }

    .arrow {
      padding-right: var(--s-2);
    }

    .who {
      grid-column: 1 / -1;
      display: flex;
      gap: var(--s-3);
      min-width: 0;
    }

    .arrow {
      grid-column: 1;
    }

    .head,
    .row[data-kind="error"] .head {
      grid-column: 2;
      white-space: normal;
    }

    .payload,
    .reason {
      grid-column: 1 / -1;
    }
  }
</style>
