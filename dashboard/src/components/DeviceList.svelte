<script lang="ts">
  import { isSimulated } from "../lib/devices";
  import { conformanceFor } from "../lib/protocol";
  import { href, router } from "../lib/router.svelte";
  import { inspector } from "../lib/state.svelte";
  import { connectionStatus, unavailableReason, verificationStatus } from "../lib/status";
  import StatusMark from "./StatusMark.svelte";

  const devices = $derived(inspector.devices);
  const simulated = $derived(devices.filter(isSimulated).length);
  const connected = $derived(devices.filter((device) => device.connected).length);
  const selected = $derived(router.route.view === "devices" ? router.route.id ?? devices[0]?.id ?? null : null);
</script>

<section class="device-list" aria-labelledby="devices-title">
  <div class="head">
    <h2 id="devices-title">Devices</h2>
    {#if inspector.devicesLoaded}
      <span class="muted count">{devices.length} registered, {connected} connected</span>
    {/if}
  </div>
  {#if simulated > 0}
    <p class="demo">
      <span class="label">Demo data</span>
      {simulated} of {devices.length} run on the mock driver.
    </p>
  {/if}
  {#if !inspector.devicesLoaded}
    <p class="muted">&emsp;</p>
  {:else if devices.length === 0}
    <p class="empty">
      No devices. Put a Device File in <code>~/.openhal/devices</code> or run <code>openhal discover</code>.
    </p>
  {:else}
    <ul>
      {#each devices as device (device.id)}
        {@const connection = connectionStatus(device)}
        {@const verification = verificationStatus(device.verification)}
        <li>
          <a
            class="device"
            href={href("devices", device.id)}
            aria-current={selected === device.id ? "page" : undefined}
          >
            <span class="name">{device.name}</span>
            <span class="id mono">{device.id}</span>
            <span class="states">
              <StatusMark tone={connection.tone} label={connection.label} />
              <StatusMark tone={verification.tone} label={verification.label} />
            </span>
            {#if unavailableReason(device)}
              <span class="unavailable"><span class="label">unavailable</span> {unavailableReason(device)}</span>
            {/if}
            <span class="facts">
              <span><span class="label">driver</span> <span class="mono">{device.driver}</span></span>
              <span><span class="label">conformance</span> {conformanceFor(device)}</span>
              <span><span class="label">hazard</span> {device.hazard}</span>
              {#if !device.writable}<span class="read-only">read-only</span>{/if}
            </span>
          </a>
        </li>
      {/each}
    </ul>
  {/if}
  {#if inspector.status?.load_problems?.length}
    <div class="problems">
      <h3>Files not loaded</h3>
      {#each inspector.status.load_problems as problem (problem.path)}
        <div class="problem">
          <p class="mono">{problem.path}</p>
          {#each problem.problems as line, index (index)}<p>{line}</p>{/each}
        </div>
      {/each}
    </div>
  {/if}
</section>

<style>
  .device-list > * {
    min-width: 0;
  }

  .device-list {
    display: grid;
    gap: var(--s-3);
    align-content: start;
    padding: var(--s-4);
  }

  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--s-1) var(--s-3);
  }

  .count {
    font-size: var(--t-label);
  }

  .demo {
    font-size: var(--t-label);
    color: var(--text-2);
    padding: var(--s-2) var(--s-3);
    border: 1px dashed var(--border);
    border-radius: var(--radius);
  }

  ul {
    display: grid;
    gap: var(--s-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .device {
    display: grid;
    gap: var(--s-1);
    padding: var(--s-3);
    border: var(--rule);
    border-radius: var(--radius);
    color: var(--text);
    text-decoration: none;
    background: var(--bg);
  }

  .device:hover {
    border-color: var(--text-2);
  }

  .device[aria-current="page"] {
    border-color: var(--accent);
    border-left-width: 3px;
    padding-left: calc(var(--s-3) - 2px);
    background: var(--surface);
  }

  .name {
    font-weight: 700;
    font-size: 16px;
  }

  .id {
    color: var(--accent);
  }

  .states {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-1) var(--s-3);
    margin-top: var(--s-1);
  }

  .unavailable {
    font-size: var(--t-label);
  }

  .facts {
    display: flex;
    flex-wrap: wrap;
    gap: 0 var(--s-3);
    font-size: var(--t-label);
  }

  .facts .label {
    font-weight: 400;
  }

  .read-only {
    font-weight: 700;
    color: var(--text-2);
  }

  .problems {
    display: grid;
    gap: var(--s-2);
  }
</style>
