<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import DeviceList from "./components/DeviceList.svelte";
  import Header from "./components/Header.svelte";
  import MessageLog from "./components/MessageLog.svelte";
  import Mark from "./components/Mark.svelte";
  import { router } from "./lib/router.svelte";
  import { inspector } from "./lib/state.svelte";
  import Audit from "./views/Audit.svelte";
  import Confirmations from "./views/Confirmations.svelte";
  import Device from "./views/Device.svelte";
  import Pair from "./views/Pair.svelte";
  import Routines from "./views/Routines.svelte";
  import Settings from "./views/Settings.svelte";
  import Writer from "./views/Writer.svelte";

  let logOpen = $state(true);
  const view = $derived(router.route.view);
  const titles: Record<string, string> = {
    devices: "Devices",
    confirmations: "Confirmations",
    audit: "Audit log",
    routines: "Routines",
    writer: "Driver writer",
    settings: "Settings",
  };

  let mainElement = $state<HTMLElement | null>(null);
  let chromeHeight = $state(0);

  $effect(() => {
    document.title = `${titles[view] ?? "Devices"} · OpenHAL Inspector`;
  });

  $effect(() => {
    void router.route.view;
    void router.route.id;
    window.scrollTo(0, 0);
    if (mainElement) mainElement.scrollTop = 0;
  });

  onMount(() => void inspector.boot());
  onDestroy(() => inspector.shutdown());
</script>

{#if inspector.auth === "unpaired"}
  <Pair onpaired={() => void inspector.boot()} />
{:else if inspector.auth === "offline"}
  <main class="offline" id="main">
    <div class="brand"><Mark size={24} /><strong>OpenHAL</strong> <span class="muted">Inspector</span></div>
    <p>The hub at <code>{location.host}</code> does not answer. Start it with <code>openhald</code>.</p>
    <p class="muted">Trying again every 3 s.</p>
  </main>
{:else}
  <a class="skip-link" href="#main">Skip to content</a>
  <div class="app" class:log-closed={!logOpen} data-view={view} style="--chrome-height: {chromeHeight}px">
    <div class="chrome" bind:clientHeight={chromeHeight}>
      <Header />
    </div>
    <aside class="left" aria-label="Device list">
      <DeviceList />
    </aside>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <main id="main" class="main" tabindex="0" bind:this={mainElement} aria-label={titles[view] ?? "Devices"}>
      {#if view === "devices"}
        <Device />
      {:else if view === "confirmations"}
        <Confirmations />
      {:else if view === "audit"}
        <Audit />
      {:else if view === "routines"}
        <Routines />
      {:else if view === "writer"}
        <Writer />
      {:else}
        <Settings />
      {/if}
    </main>
    <div class="bottom" id="message-log">
      <div class="log-slot">
        <MessageLog collapsed={!logOpen} ontoggle={() => (logOpen = !logOpen)} />
      </div>
    </div>
  </div>
{/if}

<style>
  .app {
    display: grid;
    grid-template-columns: var(--pane-left) minmax(0, 1fr);
    grid-template-rows: auto auto 1fr;
    grid-template-areas:
      "chrome chrome"
      "left main"
      "left bottom";
    min-height: 100dvh;
  }

  .chrome {
    grid-area: chrome;
    position: sticky;
    top: 0;
    z-index: 3;
  }

  .left {
    grid-area: left;
    position: sticky;
    top: var(--chrome-height);
    align-self: start;
    max-height: calc(100dvh - var(--chrome-height));
    overflow: auto;
  }

  .main {
    grid-area: main;
    min-width: 0;
    padding: var(--s-5) var(--s-6) var(--s-7);
    border-left: var(--rule);
  }

  .main:focus-visible {
    outline-offset: -2px;
  }

  .bottom {
    grid-area: bottom;
    border-top: var(--rule);
    border-left: var(--rule);
    scroll-margin-top: var(--chrome-height);
  }

  .log-slot {
    height: calc(100dvh - var(--chrome-height));
    min-height: 420px;
  }

  .log-closed .log-slot {
    height: auto;
  }

  .offline {
    display: grid;
    gap: var(--s-3);
    max-width: 560px;
    margin: 0 auto;
    padding: var(--s-7) var(--s-4);
  }

  .offline .brand {
    display: flex;
    align-items: center;
    gap: var(--s-2);
  }

  @media (max-width: 1023px) {
    .app {
      display: block;
      height: auto;
    }

    .chrome {
      display: contents;
    }

    .left {
      position: static;
      max-height: none;
      overflow: visible;
      border-bottom: var(--rule);
    }

    .bottom {
      border-left: 0;
      scroll-margin-top: 72px;
    }

    .app:not([data-view="devices"]) .left {
      display: none;
    }

    .main {
      padding: var(--s-4);
      border-left: 0;
    }

    .log-slot {
      height: auto;
      min-height: 0;
    }
  }
</style>
