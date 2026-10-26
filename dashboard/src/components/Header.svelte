<script lang="ts">
  import { NAV, href, router } from "../lib/router.svelte";
  import { inspector } from "../lib/state.svelte";
  import type { StatusWord } from "../lib/status";
  import StatusMark from "./StatusMark.svelte";
  import StopControl from "./StopControl.svelte";

  let { onshowlog }: { onshowlog?: () => void } = $props();

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
    onshowlog?.();
    requestAnimationFrame(() => {
      document.getElementById("message-log")?.scrollIntoView({ block: "start" });
      document.getElementById("log-title")?.focus();
    });
  }
</script>

{#snippet facts(where: string)}
  <dl class="hub {where}">
    <div class="hub-name">
      <dt class="label">Hub</dt>
      <dd>
        {#if status}{status.product} {status.version} <span class="muted">at</span>{/if}
        <span class="mono nobreak">{host}</span>
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
{/snippet}

<header class="top">
  <a class="brand" href={href("devices")} aria-label="OpenHAL Inspector, devices">
    <span class="wordmark">OpenHAL</span>
    <span class="product">Inspector</span>
  </a>
  {@render facts("wide")}
  <div class="stop-slot">
    <StopControl />
  </div>
</header>

{@render facts("narrow")}

<nav class="views" aria-label="Views">
  <ul>
    {#each NAV as item (item.view)}
      <li>
        <a href={href(item.view)} aria-current={router.route.view === item.view ? "page" : undefined}>
          {item.label}
          {#if item.view === "confirmations" && pending > 0}
            <span class="count">
              <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
                <circle cx="6" cy="6" r="4.75" fill="none" stroke="currentColor" stroke-width="1.5" />
                <path d="M6 1.25a4.75 4.75 0 0 0 0 9.5z" fill="currentColor" />
              </svg>
              {pending}<span class="visually-hidden"> waiting for confirmation</span>
            </span>
          {/if}
        </a>
      </li>
    {/each}
    <li class="jump">
      <button type="button" onclick={showLog}>
        <svg width="12" height="14" viewBox="0 0 12 14" aria-hidden="true" focusable="false">
          <path d="M6 1v7.5" stroke="currentColor" stroke-width="1.5" />
          <path d="M6 13 2.5 7h7z" fill="currentColor" />
        </svg>
        Message log
      </button>
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
    font-weight: 800;
    font-size: 20px;
    letter-spacing: -0.06em;
  }

  .product {
    font-size: 20px;
    color: var(--text-2);
    letter-spacing: -0.02em;
  }

  .hub {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-1) var(--s-5);
    margin: 0;
  }

  .hub div {
    display: grid;
    align-content: start;
    gap: 2px;
  }

  .hub dd {
    margin: 0;
    min-height: 20px;
    font-size: var(--t-ui);
  }

  .hub.narrow {
    display: none;
  }

  .connection {
    display: inline-block;
    min-width: 7.5em;
  }

  .views {
    border-bottom: var(--rule);
    background: var(--bg);
  }

  .views ul {
    display: flex;
    flex-wrap: wrap;
    gap: 0 var(--s-1);
    margin: 0;
    padding: 0 var(--s-4);
    list-style: none;
  }

  .views a,
  .jump button {
    display: inline-flex;
    align-items: center;
    gap: var(--s-2);
    min-height: 40px;
    padding: 0 var(--s-2);
    color: var(--text-2);
    font: inherit;
    font-weight: 700;
    text-decoration: none;
    text-underline-offset: 4px;
  }

  .views a {
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }

  .views a:hover,
  .jump button:hover {
    text-decoration: underline;
  }

  .jump {
    margin-left: auto;
  }

  .jump button {
    border: 0;
    background: none;
    cursor: pointer;
  }

  .views a[aria-current="page"] {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }

  .count {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 0 6px;
    border-radius: var(--radius);
    background: var(--confirm-bg);
    color: var(--confirm);
    font-family: var(--font-mono);
    font-size: var(--t-label);
    font-variant-numeric: tabular-nums;
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

    .hub.wide {
      display: none;
    }

    .hub.narrow {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--s-2) var(--s-4);
      padding: var(--s-3) var(--s-4);
      border-bottom: var(--rule);
    }

    .stop-slot {
      grid-column: 2;
      grid-row: 1;
    }

    .views ul {
      gap: 0;
      padding: 0 var(--s-2);
    }

    .views a,
    .jump button {
      padding: 0 6px;
    }
  }
</style>
