<script lang="ts">
  import ActionControl from "../components/ActionControl.svelte";
  import Prose from "../components/Prose.svelte";
  import StatusMark from "../components/StatusMark.svelte";
  import WriteControl from "../components/WriteControl.svelte";
  import { isSimulated } from "../lib/devices";
  import { conformanceFor } from "../lib/protocol";
  import { router } from "../lib/router.svelte";
  import { inspector } from "../lib/state.svelte";
  import { connectionStatus, unavailableReason, verificationStatus } from "../lib/status";
  import { dataBlock, formatQuantity, unitSymbol, valueWidth } from "../lib/units";

  const id = $derived(router.route.id ?? inspector.devices[0]?.id ?? null);
  const view = $derived(id ? inspector.views[id] : undefined);
  const known = $derived(id ? inspector.devices.some((device) => device.id === id) : false);
  const stopped = $derived(inspector.status?.stopped ?? false);

  $effect(() => {
    if (id && known) void inspector.refreshDevice(id);
  });

  const fileName = $derived(view?.path ? view.path.split("/").pop() : null);
  const disabledReason = $derived(
    !view
      ? ""
      : stopped
        ? "The hub is stopped. Commands are refused with error -32014 STOPPED until a person lifts the stop."
        : !view.writable
          ? "Read-only. A person has not confirmed this Device File's limits, so commands get error -32015 UNVERIFIED_LIMITS."
          : view.unavailable
            ? `The device is ${view.unavailable}. Commands get error -32005 DEVICE_UNAVAILABLE.`
            : "",
  );

  function stateLine(value: unknown): string {
    if (!value || typeof value !== "object") return String(value);
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${key} = ${typeof item === "object" ? JSON.stringify(item) : String(item)}`)
      .join(", ");
  }

  function seconds(value: number | null | undefined): string {
    if (value === null || value === undefined) return "";
    if (value >= 60 && value % 60 === 0) return `${value / 60} min`;
    return `${value} s`;
  }
</script>

{#if !inspector.devicesLoaded}
  <div class="device" aria-busy="true"><p class="placeholder">&emsp;</p></div>
{:else if !id}
  <div class="empty">
    No devices yet. Put a Device File in <code>~/.openhal/devices</code>, or find one with <code>openhal discover</code> and
    the driver writer.
  </div>
{:else if !known}
  <div class="empty" role="alert">
    <p><code>error -32004 UNKNOWN_TARGET</code></p>
    <p>There is no device <code>{id}</code> on this hub.</p>
  </div>
{:else if !view}
  <div class="device" aria-busy="true"><p class="placeholder">&emsp;</p></div>
{:else}
  {@const connection = connectionStatus(view)}
  {@const verification = verificationStatus(view.verification)}
  <article class="device" aria-labelledby="device-title">
    <header class="section head">
      <div class="title">
        <h1 id="device-title">{view.name}</h1>
        <span class="mono id nobreak">{view.id}</span>
        {#if isSimulated(view)}<span class="sim">simulated</span>{/if}
      </div>
      <dl class="facts">
        <div><dt class="label">state</dt><dd><StatusMark tone={connection.tone} label={connection.label} /></dd></div>
        {#if unavailableReason(view)}<div><dt class="label">unavailable</dt><dd>{unavailableReason(view)}</dd></div>{/if}
        <div>
          <dt class="label">verification</dt>
          <dd class="verification">
            {#if verification.detail}<span>{verification.detail}</span>{/if}
            <StatusMark tone={verification.tone} label={verification.label} />
          </dd>
        </div>
        <div><dt class="label">driver</dt><dd class="mono nobreak">{view.driver}</dd></div>
        <div><dt class="label">conformance</dt><dd>{conformanceFor(view)}</dd></div>
        <div><dt class="label">hazard</dt><dd>{view.hazard}</dd></div>
        <div><dt class="label">mode</dt><dd>{view.writable ? "takes commands" : "read-only"}</dd></div>
        {#if fileName}<div class="wide"><dt class="label">device file</dt><dd class="mono nobreak">{fileName}</dd></div>{/if}
        {#if view.source}<div><dt class="label">source</dt><dd>{view.source}</dd></div>{/if}
      </dl>
      {#if view.last_error}
        <div class="problem"><p class="label">Last driver error, shown as data</p><pre>{dataBlock(view.last_error)?.text}</pre></div>
      {/if}
      {#if !view.writable}
        <div class="notice">
          <StatusMark tone="unverified" label="limits not confirmed" />
          <p>
            Commands get <code>error -32015 UNVERIFIED_LIMITS</code> until a person confirms the limits with
            <code><Prose text="openhal file confirm {fileName ?? view.id}" /></code> or the limits interview.
          </p>
          {#if view.unconfirmed.length}
            <p class="muted">Unconfirmed <span class="mono">{view.unconfirmed.join(", ")}</span></p>
          {/if}
        </div>
      {/if}
    </header>

    {#if Object.keys(view.read).length}
      <section class="section" aria-labelledby="read-title">
        <h2 id="read-title">Read channels</h2>
        <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
        <div class="table-scroll" tabindex="0" role="region" aria-label="Read channels table">
          <table class="grid">
          <thead>
            <tr><th scope="col">Channel</th><th scope="col" class="num">Value</th><th scope="col">Range</th><th scope="col">Every</th></tr>
          </thead>
          <tbody>
            {#each Object.entries(view.read) as [name, spec] (name)}
              <tr>
                <th scope="row" class="mono">{name}</th>
                <td class="num">
                  <output class="value mono" style="min-width: {valueWidth(spec.range?.[0], spec.range?.[1]) + 3}ch" class:unknown={!spec.known}>
                    {spec.known ? formatQuantity(spec.value, spec.unit) : "unknown"}
                  </output>
                </td>
                <td class="mono">
                  {#if spec.range}{formatQuantity(spec.range[0], spec.unit)} to {formatQuantity(spec.range[1], spec.unit)}{:else if spec.values}{spec.values.join(", ")}{:else}<span class="muted">{unitSymbol(spec.unit) || spec.type}</span>{/if}
                </td>
                <td class="mono">{seconds(spec.every_s)}</td>
              </tr>
            {/each}
          </tbody>
          </table>
        </div>
      </section>
    {/if}

    {#if Object.keys(view.write).length}
      <section class="section" aria-labelledby="write-title">
        <div class="section-head">
          <h2 id="write-title">Control channels</h2>
          <p class="muted small">A change from the Inspector is made as you, a person. The Safety Kernel checks each one.</p>
        </div>
        <div class="controls">
          {#each Object.entries(view.write) as [name, spec] (name)}
            <WriteControl
              device={view.id}
              channel={name}
              {spec}
              disabled={!!disabledReason}
              readOnly={!view.writable}
              {disabledReason}
              onwritten={() => id && void inspector.refreshDevice(id)}
            />
          {/each}
        </div>
      </section>
    {/if}

    {#if Object.keys(view.actions).length}
      <section class="section" aria-labelledby="actions-title">
        <h2 id="actions-title">Actions</h2>
        <div class="controls">
          {#each Object.entries(view.actions) as [name, spec] (name)}
            <ActionControl
              device={view.id}
              {name}
              {spec}
              disabled={!!disabledReason}
              readOnly={!view.writable}
              safeState={view.safe_state.some((step) => step.action === name)}
              {disabledReason}
              onran={() => void inspector.refreshConfirmations()}
            />
          {/each}
        </div>
      </section>
    {/if}

    <section class="section" aria-labelledby="safety-title">
      <h2 id="safety-title">Safety</h2>
      <dl class="safety">
        <div>
          <dt class="label">safe state</dt>
          <dd class="mono">{view.safe_state.length ? view.safe_state.map(stateLine).join(", then ") : "none declared"}</dd>
        </div>
        {#each view.interlocks as interlock, index (index)}
          <div>
            <dt class="label">interlock</dt>
            <dd>
              <span class="mono">{interlock.if ? `if ${interlock.if}, ` : ""}require {interlock.require}</span>
              {#if interlock.message}<br /><span class="muted">{interlock.message}</span>{/if}
            </dd>
          </div>
        {/each}
        {#if view.watchdog.heartbeat_s}
          <div>
            <dt class="label">heartbeat</dt>
            <dd class="mono">every {seconds(view.watchdog.heartbeat_s)}{view.watchdog.on_loss ? `, on loss ${view.watchdog.on_loss}` : ""}</dd>
          </div>
        {/if}
        {#each view.watchdog.max_duration as rule, index (index)}
          <div>
            <dt class="label">watchdog</dt>
            <dd class="mono">{rule.when} for at most {seconds(rule.for_s)}, then {typeof rule.then === "string" ? rule.then : stateLine(rule.then)}</dd>
          </div>
        {/each}
      </dl>
      {#if view.warnings.length}
        {#each view.warnings as warning, index (index)}<p class="problem">{warning}</p>{/each}
      {/if}
    </section>

    {#if view.notes}
      <section class="section" aria-labelledby="notes-title">
        <h2 id="notes-title">Notes</h2>
        <p class="muted small">From the Device File, shown as data.</p>
        <pre class="data-block">{dataBlock(view.notes)?.text}</pre>
      </section>
    {/if}
  </article>
{/if}

<style>
  .device {
    display: grid;
    gap: 0;
    max-width: 960px;
  }

  .placeholder {
    font-size: 24px;
    min-height: 32px;
  }

  .head {
    display: grid;
    gap: var(--s-3);
  }

  .title {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--s-2) var(--s-3);
  }

  .title h1 {
    font-size: 24px;
  }

  .id {
    color: var(--accent);
    font-size: 16px;
  }

  .sim {
    font-size: var(--t-label);
    color: var(--text-2);
    padding: 1px 6px;
    background: var(--surface);
    border-radius: var(--radius);
  }

  .facts,
  .safety {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
    gap: var(--s-3) var(--s-4);
    margin: 0;
  }

  .safety {
    grid-template-columns: 1fr;
    gap: var(--s-2);
  }

  .safety div {
    display: grid;
    grid-template-columns: 110px minmax(0, 1fr);
    gap: var(--s-3);
  }

  .facts div {
    display: grid;
    gap: 2px;
  }

  .facts .wide {
    grid-column: span 2;
  }

  dd {
    margin: 0;
  }

  .verification {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--s-1) var(--s-2);
  }

  .notice {
    display: grid;
    justify-items: start;
    gap: var(--s-2);
    padding: var(--s-3) var(--s-4);
    background: var(--surface);
    border-radius: var(--radius);
  }

  .controls {
    display: grid;
    gap: var(--s-3);
  }

  .small {
    font-size: var(--t-label);
  }

  .num {
    text-align: right;
  }

  .value {
    display: inline-block;
    text-align: right;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }

  .value.unknown {
    color: var(--text-2);
    font-weight: 400;
  }

  table.grid th[scope="row"] {
    font-weight: 400;
    color: var(--text);
    font-size: var(--t-mono);
    border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  }

  @media (max-width: 767px) {
    .safety div {
      grid-template-columns: 1fr;
      gap: 2px;
    }
  }
</style>
