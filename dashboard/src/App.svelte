<script lang="ts">
  import { onDestroy, onMount, tick, untrack, type Component } from "svelte";
  import DeviceList from "./components/DeviceList.svelte";
  import Header from "./components/Header.svelte";
  import MessageLog from "./components/MessageLog.svelte";
  import Mark from "./components/Mark.svelte";
  import { router, type View } from "./lib/router.svelte";
  import { inspector } from "./lib/state.svelte";
  import Device from "./views/Device.svelte";

  type Lazy = "confirmations" | "audit" | "routines" | "writer" | "settings" | "pair";
  const LOADERS: Record<Lazy, () => Promise<{ default: Component<any> }>> = {
    confirmations: () => import("./views/Confirmations.svelte"),
    audit: () => import("./views/Audit.svelte"),
    routines: () => import("./views/Routines.svelte"),
    writer: () => import("./views/Writer.svelte"),
    settings: () => import("./views/Settings.svelte"),
    pair: () => import("./views/Pair.svelte"),
  };
  let loaded = $state<Partial<Record<Lazy, Component<any>>>>({});

  function load(name: Lazy): void {
    if (loaded[name]) return;
    void LOADERS[name]().then((module) => {
      loaded = { ...loaded, [name]: module.default };
    });
  }

  const wanted = $derived<Lazy | null>(inspector.auth === "unpaired" ? "pair" : router.route.view === "devices" ? null : (router.route.view as Exclude<View, "devices">));
  const ViewComponent = $derived(router.route.view === "devices" ? Device : loaded[router.route.view as Lazy] ?? null);
  const Pair = $derived(loaded.pair ?? null);

  $effect(() => {
    if (wanted) load(wanted);
  });

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

  function measure(element: HTMLElement) {
    const observer = new ResizeObserver(([entry]) => {
      chromeHeight = Math.round(entry?.borderBoxSize?.[0]?.blockSize ?? 0);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }

  $effect(() => {
    document.title = `${titles[view] ?? "Devices"} · OpenHAL Inspector`;
  });

  let lastRoute = `${router.route.view}/${router.route.id}`;

  $effect(() => {
    const route = `${router.route.view}/${router.route.id}`;
    if (route === lastRoute) return;
    lastRoute = route;
    window.scrollTo(0, 0);
    const pane = untrack(() => mainElement);
    if (pane) pane.scrollTop = 0;
  });

  let patient = $state(false);
  const shell = $derived((inspector.ready && ViewComponent !== null) || patient);
  const hidden = $derived(!inspector.settled && !patient);

  $effect(() => {
    if (shell) void tick().then(() => inspector.trySettle());
  });

  onMount(() => {
    void inspector.boot();
    const timer = setTimeout(() => (patient = true), 800);
    return () => clearTimeout(timer);
  });
  onDestroy(() => inspector.shutdown());
</script>

{#if inspector.auth === "unpaired"}
  {#if Pair}<Pair onpaired={() => void inspector.boot()} />{/if}
{:else if inspector.auth === "offline"}
  <main class="offline" id="main">
    <div class="brand"><Mark size={24} /><strong>OpenHAL</strong> <span class="muted">Inspector</span></div>
    <p>The hub at <code>{location.host}</code> does not answer. Start it with <code>openhald</code>.</p>
    <p class="muted">Trying again every 3 s.</p>
  </main>
{:else if !shell}
  <div class="booting" aria-busy="true"></div>
{:else}
  <a class="skip-link" href="#main">Skip to content</a>
  <div class="app" class:log-closed={!logOpen} class:settling={hidden} data-view={view} style="--chrome-height: {chromeHeight}px">
    <div class="chrome" {@attach measure}>
      <Header />
    </div>
    <aside class="left" aria-label="Device list">
      <DeviceList />
    </aside>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <main id="main" class="main" tabindex="0" bind:this={mainElement} aria-label={titles[view] ?? "Devices"}>
      {#if ViewComponent}
        <ViewComponent />
      {:else}
        <div class="pending" aria-busy="true"></div>
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

  .settling {
    visibility: hidden;
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

  .booting {
    min-height: 100dvh;
  }

  .pending {
    min-height: 60dvh;
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
