<script lang="ts">
  import StatusMark from "../components/StatusMark.svelte";
  import { api } from "../lib/api";
  import { formatDateTime } from "../lib/units";
  import { inspector } from "../lib/state.svelte";
  import type { TokenInfo } from "../lib/types";

  let tokens = $state<TokenInfo[]>([]);
  let loaded = $state(false);
  let name = $state("");
  let kind = $state<"agent" | "human">("agent");
  let scope = $state("read");
  let created = $state<(TokenInfo & { token: string }) | null>(null);
  let confirming = $state<string | null>(null);
  let error = $state<string | null>(null);
  let code = $state<{ code: string; expires_in_s: number } | null>(null);
  let copied = $state(false);
  let showRevoked = $state(false);

  const shown = $derived(showRevoked ? tokens : tokens.filter((token) => !token.revoked));
  const host = typeof location === "undefined" ? "" : location.host;
  const loopback = /^(127\.|localhost|\[::1\])/.test(host);
  const lan = $derived(inspector.status?.allow_lan);

  $effect(() => {
    void load();
  });

  const settle = inspector.hold();

  async function load() {
    try {
      tokens = await api.tokens();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "Tokens did not load.";
    }
    loaded = true;
    settle();
  }

  async function create(event: SubmitEvent) {
    event.preventDefault();
    error = null;
    try {
      created = await api.createToken(name.trim(), kind, kind === "human" ? "control_medium" : scope);
      name = "";
      copied = false;
      await load();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "The token was not created.";
    }
  }

  async function revoke(id: string) {
    try {
      await api.revokeToken(id);
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "The token was not revoked.";
    }
    confirming = null;
    await load();
  }

  async function copyToken() {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.token);
      copied = true;
    } catch {
      copied = false;
    }
  }

  async function newCode() {
    try {
      code = await api.pairCode();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "No pairing code.";
    }
  }

</script>

<div class="view">
  <header class="section">
    <h1>Settings</h1>
    <dl class="facts">
      <div><dt class="label">you are</dt><dd class="mono">{inspector.you ? `${inspector.you.kind}:${inspector.you.name}` : ""}</dd></div>
      <div><dt class="label">scope</dt><dd class="mono">{inspector.you?.scope ?? ""}</dd></div>
      <div><dt class="label">protocol</dt><dd class="mono">{inspector.status?.protocol_version ?? ""}</dd></div>
      <div><dt class="label">conformance</dt><dd>{inspector.status?.conformance ?? ""}</dd></div>
      <div><dt class="label">hub</dt><dd class="mono">{inspector.status ? `${inspector.status.product} ${inspector.status.version}` : ""}</dd></div>
    </dl>
  </header>

  <section class="section" aria-labelledby="tokens-title">
    <div class="section-head">
      <h2 id="tokens-title">Client tokens</h2>
      <label class="check"><input type="checkbox" bind:checked={showRevoked} /> Show revoked tokens</label>
    </div>
    <p class="muted">
      Each client sends a bearer token. Agent tokens carry a scope. High hazard devices always need a person, whatever the
      scope.
    </p>
    {#if error}<p class="problem" role="alert">{error}</p>{/if}
    {#if loaded && !shown.length}
      <p class="empty">No tokens. Create one below or run <code>openhal token create --agent --scope read</code>.</p>
    {:else}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <div class="table-scroll" tabindex="0" role="region" aria-label="Client tokens table">
        <table class="grid tokens">
        <thead>
          <tr><th scope="col">Name</th><th scope="col">Kind</th><th scope="col">Scope</th><th scope="col">Id</th><th scope="col">Created</th><th scope="col">State</th><th scope="col"><span class="visually-hidden">Revoke</span></th></tr>
        </thead>
        <tbody>
          {#each shown as token (token.token_id)}
            <tr class={token.kind}>
              <td class="name nobreak">{token.name}</td>
              <td data-label="kind">{token.kind}</td>
              <td class="mono" data-label="scope">{token.scope}</td>
              <td class="mono" data-label="id">{token.token_id}</td>
              <td class="mono" data-label="created">{formatDateTime(token.created_at)}</td>
              <td data-label="state"><StatusMark tone={token.revoked ? "neutral" : "ok"} label={token.revoked ? "revoked" : "active"} /></td>
              <td class="end">
                {#if !token.revoked}
                  <div class="revoke">
                    {#if confirming === token.token_id}
                      <button class="button small" type="button" onclick={() => revoke(token.token_id)}>Revoke {token.name}</button>
                      <button class="button small" type="button" onclick={() => (confirming = null)}>Keep</button>
                    {:else}
                      <button class="button small" type="button" onclick={() => (confirming = token.token_id)} aria-label="Revoke {token.name}">Revoke</button>
                    {/if}
                  </div>
                {/if}
              </td>
            </tr>
          {/each}
        </tbody>
        </table>
      </div>
    {/if}

    <form class="create" onsubmit={create}>
      <h3>Create a token</h3>
      <div class="row">
        <label class="field"><span>Name</span><input type="text" bind:value={name} maxlength="80" required autocomplete="off" /></label>
        <label class="field">
          <span>Kind</span>
          <select bind:value={kind}><option value="agent">agent</option><option value="human">human</option></select>
        </label>
        <label class="field">
          <span>Scope</span>
          <select bind:value={scope} disabled={kind === "human"}>
            <option value="read">read</option>
            <option value="control_low">control_low</option>
            <option value="control_medium">control_medium</option>
          </select>
        </label>
        <button class="button primary" type="submit" disabled={!name.trim()}>Create token</button>
      </div>
      {#if kind === "human"}<p class="muted small">A human token can approve, reject and lift a stop. Give it only to a person.</p>{/if}
    </form>
    {#if created}
      <div class="created human-surface" aria-live="polite">
        <p><strong>{created.name}</strong> was created. The hub shows this token once and stores only its hash.</p>
        <p class="token"><code>{created.token}</code></p>
        <button class="button small" type="button" onclick={copyToken}>{copied ? "Copied" : "Copy the token"}</button>
      </div>
    {/if}
  </section>

  <section class="section" aria-labelledby="pair-title">
    <h2 id="pair-title">Pair another browser</h2>
    <p class="muted">A pairing code gives one browser a human session cookie, like <code>openhal pair</code>.</p>
    <div><button class="button" type="button" onclick={newCode}>New pairing code</button></div>
    {#if code}<p class="code" aria-live="polite"><code>{code.code}</code> <span class="muted">works once, for {code.expires_in_s} s</span></p>{/if}
  </section>

  <section class="section" aria-labelledby="lan-title">
    <h2 id="lan-title">LAN access</h2>
    <dl class="facts">
      <div><dt class="label">this page</dt><dd class="mono">{host}</dd></div>
      <div>
        <dt class="label">LAN access</dt>
        <dd>
          {#if lan === undefined}
            not reported
          {:else}
            <StatusMark tone="neutral" label={lan ? "on, other machines can connect" : "off, loopback only"} />
          {/if}
        </dd>
      </div>
      <div><dt class="label">reached over</dt><dd>{loopback ? "loopback" : "the network"}</dd></div>
      <div><dt class="label">setting</dt><dd class="mono">api.allow_lan</dd></div>
    </dl>
    <p class="muted">
      The Inspector shows LAN access read-only. To change it, set <code>api.allow_lan</code> in
      <code>~/.openhal/config.yaml</code> and restart <code>openhald</code>. It is off unless you turn it on.
    </p>
  </section>
</div>

<style>
  .view {
    display: grid;
    max-width: 1000px;
  }

  .facts {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-3) var(--s-6);
    margin: var(--s-3) 0 0;
  }

  .facts div {
    display: grid;
    gap: 2px;
  }

  dd {
    margin: 0;
  }

  .check {
    display: inline-flex;
    align-items: center;
    gap: var(--s-2);
    font-size: var(--t-label);
    cursor: pointer;
  }

  .tokens td {
    vertical-align: middle;
  }

  .tokens tr.agent td:first-child {
    border-left: 2px dashed var(--text-2);
    padding-left: var(--s-3);
  }

  .tokens tr.human td:first-child {
    border-left: 2px solid var(--text);
    padding-left: var(--s-3);
  }

  .tokens .end {
    padding-right: 0;
  }

  .revoke {
    display: flex;
    flex-wrap: wrap;
    gap: var(--s-2);
    justify-content: flex-end;
  }

  @media (max-width: 767px) {
    .tokens thead {
      display: none;
    }

    .tokens,
    .tokens tbody {
      display: block;
    }

    .tokens tr {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: var(--s-2) var(--s-4);
      padding: var(--s-3) 0 var(--s-3) var(--s-3);
      border-bottom: var(--rule);
    }

    .tokens tr.agent {
      border-left: 2px dashed var(--text-2);
    }

    .tokens tr.human {
      border-left: 2px solid var(--text);
    }

    .tokens tr td,
    .tokens tr.agent td:first-child,
    .tokens tr.human td:first-child {
      display: grid;
      align-content: start;
      gap: 2px;
      padding: 0;
      border: 0;
      overflow-wrap: anywhere;
    }

    .tokens td[data-label]::before {
      content: attr(data-label);
      font-family: var(--font-text);
      font-size: var(--t-label);
      font-weight: 700;
      font-variant-caps: all-small-caps;
      letter-spacing: 0.04em;
      color: var(--text-2);
    }

    .tokens .name {
      grid-column: 1 / -1;
      font-weight: 700;
      font-size: 16px;
    }

    .tokens .end {
      grid-column: 1 / -1;
    }

    .tokens .end:empty {
      display: none;
    }

    .revoke {
      justify-content: flex-start;
    }
  }

  .create {
    display: grid;
    gap: var(--s-3);
    margin-top: var(--s-3);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: end;
    gap: var(--s-3);
  }

  .small {
    font-size: var(--t-label);
  }

  .created {
    display: grid;
    gap: var(--s-2);
    justify-items: start;
    padding: var(--s-3) var(--s-4);
  }

  .token code {
    overflow-wrap: anywhere;
  }

  .code code {
    font-size: 22px;
    letter-spacing: 0.15em;
  }
</style>
