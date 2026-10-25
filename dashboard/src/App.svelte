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

  $effect(() => {
    document.title = `${titles[view] ?? "Devices"} · OpenHAL Inspector`;
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
  <div class="app" class:log-closed={!logOpen} data-view={view}>
    <div class="chrome">
      <Header />
    </div>
    <aside class="left" aria-label="Device list">
      <DeviceList />
    </aside>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <main id="main" class="main" tabindex="0" aria-label={titles[view] ?? "Devices"}>
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
    <div class="bottom">
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
    grid-template-rows: auto minmax(0, 1fr) auto;
    grid-template-areas:
      "chrome chrome"
      "left main"
      "bottom bottom";
    height: 100dvh;
  }

  .chrome {
    grid-area: chrome;
  }

  .left {
    grid-area: left;
    overflow: auto;
    border-right: var(--rule);
  }

  .main {
    grid-area: main;
    overflow: auto;
    padding: var(--s-5) var(--s-6);
  }

  .main:focus-visible {
    outline-offset: -2px;
  }

  .bottom {
    grid-area: bottom;
    border-top: var(--rule);
  }

  .log-slot {
    height: var(--log-height);
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
      border-right: 0;
      border-bottom: var(--rule);
    }

    .app:not([data-view="devices"]) .left {
      display: none;
    }

    .main {
      padding: var(--s-4);
      overflow: visible;
    }

    .log-slot {
      height: auto;
    }
  }
</style>
