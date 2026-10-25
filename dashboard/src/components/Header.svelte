<script lang="ts">
  import { NAV, href, router } from "../lib/router.svelte";
  import { inspector } from "../lib/state.svelte";
  import type { StatusWord } from "../lib/status";
  import Mark from "./Mark.svelte";
  import StatusMark from "./StatusMark.svelte";
  import StopControl from "./StopControl.svelte";

  const status = $derived(inspector.status);
  const connection = $derived<StatusWord>(
    inspector.live === "open"
      ? { tone: "ok", label: "live" }
      : inspector.live === "connecting"
        ? { tone: "pending", label: "connecting" }
        : { tone: "neutral", label: "reconnecting" },
  );
  const pending = $derived(inspector.confirmations.filter((request) => request.status === "pending").length);
  const host = typeof location === "undefined" ? "" : location.host;

  function showLog() {
    const log = document.getElementById("message-log");
    if (!log) return;
    log.scrollIntoView({ block: "start" });
    document.getElementById("log-title")?.focus();
  }
</script>

<header class="top">
  <a class="brand" href={href("devices")} aria-label="OpenHAL Inspector, devices">
    <Mark size={22} />
    <span class="wordmark">OpenHAL</span>
    <span class="product">Inspector</span>
  </a>
  <dl class="hub">
    <div>
      <dt class="label">Hub</dt>
      <dd>
        {#if status}
          {status.product} {status.version} <span class="muted">at</span> <span class="mono">{host}</span>
        {:else}
          <span class="mono">{host}</span>
        {/if}
      </dd>
    </div>
    <div>
      <dt class="label">Connection</dt>
      <dd class="connection"><StatusMark tone={connection.tone} label={connection.label} /></dd>
    </div>
    <div>
      <dt class="label">Protocol</dt>
      <dd class="mono">{#if status?.protocol_version}{status.protocol_version}{:else}&emsp;{/if}</dd>
    </div>
    <div>
      <dt class="label">Conformance</dt>
      <dd>{#if status?.conformance}{status.conformance}{:else}&emsp;{/if}</dd>
    </div>
  </dl>
  <div class="stop-slot">
    <StopControl />
  </div>
</header>

<p class="hub-line">
  {#if status}{status.product} {status.version}{/if} <span class="mono">{host}</span>
  <span class="connection"><StatusMark tone={connection.tone} label={connection.label} /></span>
  {#if status?.protocol_version}<span class="muted">protocol</span> <span class="mono">{status.protocol_version}</span>{/if}
  {#if status?.conformance}<span class="muted">conformance</span> {status.conformance}{/if}
</p>

<nav class="views" aria-label="Views">
  <ul>
    {#each NAV as item (item.view)}
      <li>
        <a href={href(item.view)} aria-current={router.route.view === item.view ? "page" : undefined}>
          {item.label}
          {#if item.view === "confirmations" && pending > 0}
            <span class="count" aria-label="{pending} pending">{pending}</span>
          {/if}
        </a>
      </li>
    {/each}
    <li class="jump">
      <button type="button" onclick={showLog}>Message log</button>
    </li>
  </ul>
</nav>

{#if status?.stopped}
  <div class="stopped" id="stopped-state" role="status">
    <StatusMark tone="blocked" label="stopped" />
    <p>
      Every command is refused with <code>error -32014 STOPPED</code> until a person lifts the stop with
      UNLOCK.
      {#if status.stop_reason}<span class="reason"><span class="label">Reason</span> {status.stop_reason}</span>{/if}
    </p>
  </div>
{/if}

<style>
  .top {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--s-3) var(--s-6);
    padding: var(--s-3) var(--s-5);
    border-bottom: var(--rule);
    background: var(--bg);
  }

  .brand {
    display: inline-flex;
    align-items: center;
    gap: var(--s-2);
    color: var(--text);
    text-decoration: none;
  }

  .wordmark {
    font-weight: 700;
    font-size: 19px;
  }

  .product {
    font-size: 19px;
    color: var(--text-2);
  }

  .hub {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-1) var(--s-5);
    margin: 0;
  }

  .hub div {
    display: grid;
    gap: 2px;
  }

  .hub dd {
    margin: 0;
    min-height: 20px;
    font-size: var(--t-ui);
  }

  .connection {
    display: inline-block;
    min-width: 7.5em;
  }

  .views {
    border-bottom: var(--rule);
    background: var(--bg);
  }

  .hub-line {
    display: none;
  }

  .views ul {
    display: flex;
    flex-wrap: wrap;
    gap: 0 var(--s-1);
    margin: 0;
    padding: 0 var(--s-4);
    list-style: none;
  }

  .views a {
    display: inline-flex;
    align-items: center;
    gap: var(--s-2);
    min-height: 40px;
    padding: 0 var(--s-2);
    color: var(--text-2);
    text-decoration: none;
    font-weight: 700;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }

  .views a:hover,
  .jump button:hover {
    color: var(--text);
  }

  .jump {
    margin-left: auto;
  }

  .jump button {
    min-height: 40px;
    padding: 0 var(--s-2);
    border: 0;
    background: none;
    color: var(--text-2);
    font: inherit;
    font-weight: 700;
    cursor: pointer;
  }

  .views a[aria-current="page"] {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }

  .count {
    min-width: 22px;
    padding: 0 6px;
    border-radius: var(--radius);
    background: var(--confirm-bg);
    color: var(--confirm);
    font-family: var(--font-mono);
    font-size: var(--t-label);
    text-align: center;
  }

  .stopped {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-2) var(--s-4);
    padding: var(--s-3) var(--s-5);
    border-bottom: 2px solid var(--blocked);
    background: var(--surface);
  }

  .stopped code {
    color: var(--blocked);
    font-weight: 700;
  }

  .reason {
    margin-left: var(--s-3);
  }

  @media (max-width: 1023px) {
    .top {
      grid-template-columns: minmax(0, 1fr) auto;
      padding: var(--s-2) var(--s-4);
      position: sticky;
      top: 0;
      z-index: 2;
    }

    .hub {
      display: none;
    }

    .hub-line {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: var(--s-1) var(--s-3);
      padding: var(--s-2) var(--s-4);
      border-bottom: var(--rule);
      font-size: var(--t-label);
    }

    .stop-slot {
      grid-column: 2;
      grid-row: 1;
    }

    .views ul {
      padding: 0 var(--s-2);
    }
  }
</style>
