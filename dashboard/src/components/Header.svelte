<script lang="ts">
  import wordmarkLight from "../../../docs/assets/wordmark-light.svg";
  import wordmarkDark from "../../../docs/assets/wordmark-dark.svg";
  import { NAV, href, router } from "../lib/router.svelte";
  import { inspector } from "../lib/state.svelte";
  import type { StatusWord } from "../lib/status";
  import ArrowDownIcon from "@lucide/svelte/icons/arrow-down";
  import { Button } from "$lib/components/ui/button/index.js";
  import * as NavigationMenu from "$lib/components/ui/navigation-menu/index.js";
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
    <picture class="wordmark"><source srcset={wordmarkDark} media="(prefers-color-scheme: dark)" /><img src={wordmarkLight} alt="" width="88" height="24" /></picture>
    <span class="product">Inspector</span>
  </a>
  {@render facts("wide")}
  <div class="stop-slot">
    <StopControl />
  </div>
</header>

{@render facts("narrow")}

<NavigationMenu.Root class="views" aria-label="Views">
  <NavigationMenu.List class="flex-wrap gap-x-1 px-4 max-lg:gap-x-0 max-lg:px-2">
    {#each NAV as item (item.view)}
      <NavigationMenu.Item>
        <NavigationMenu.Link
          href={href(item.view)}
          active={router.route.view === item.view}
          class="-mb-px inline-flex min-h-10 items-center gap-2 border-b-2 border-transparent px-2 font-bold text-muted-foreground underline-offset-4 hover:underline data-active:border-accent data-active:text-foreground max-lg:px-1.5"
        >
          {item.label}
          {#if item.view === "confirmations" && pending > 0}
            <span class="count">{pending}<span class="visually-hidden"> pending confirmation</span></span>
          {/if}
        </NavigationMenu.Link>
      </NavigationMenu.Item>
    {/each}
    <NavigationMenu.Item class="ml-auto">
      <Button
        variant="ghost"
        class="min-h-10 px-2 font-bold underline-offset-4 not-disabled:hover:bg-transparent not-disabled:hover:text-muted-foreground hover:underline max-lg:px-1.5"
        onclick={showLog}
      >
        <ArrowDownIcon class="size-3.5" aria-hidden="true" />
        Message log
      </Button>
    </NavigationMenu.Item>
  </NavigationMenu.List>
</NavigationMenu.Root>

{#if status?.stopped}
  <div class="stopped" id="stopped-state" role="status">
    <StatusMark tone="blocked" label="stopped" />
    <p>
      Every command is blocked with <code>error -32014 STOPPED</code> until a person lifts the stop with
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
    display: block;
    line-height: 0;
  }

  .wordmark img {
    display: block;
    width: auto;
    height: 24px;
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

  :global(.views) {
    border-bottom: var(--rule);
    background: var(--bg);
  }

  .stop-slot {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    min-height: 52px;
  }

  .count {
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
    border-bottom: var(--rule);
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
      min-height: 48px;
    }
  }
</style>
