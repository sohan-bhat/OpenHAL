<script lang="ts">
  import { inspector } from "../lib/state.svelte";

  const stopped = $derived(inspector.status?.stopped ?? false);
  let busy = $state(false);
  let dialog = $state<HTMLDialogElement | null>(null);
  let phrase = $state("");
  let error = $state<string | null>(null);
  let input = $state<HTMLInputElement | null>(null);

  async function stop() {
    busy = true;
    await inspector.stop();
    busy = false;
  }

  function openUnlock() {
    phrase = "";
    error = null;
    dialog?.showModal();
    queueMicrotask(() => input?.focus());
  }

  async function unlock(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = await inspector.unlock(phrase);
    busy = false;
    if (!error) dialog?.close();
  }
</script>

{#if stopped}
  <button type="button" class="button unlock" onclick={openUnlock} aria-describedby="stopped-state">UNLOCK</button>
{:else}
  <button type="button" class="control stop" onclick={stop} disabled={busy} aria-label="STOP every device">STOP</button>
{/if}

<dialog bind:this={dialog} class="unlock-dialog" aria-labelledby="unlock-title">
  <form method="dialog" onsubmit={unlock}>
    <h2 id="unlock-title">Lift the stop</h2>
    <p>
      Every device was put in its safe state. Every command stays blocked until a person types the phrase
      <code>unlock</code>.
    </p>
    <label class="field">
      <span>Phrase</span>
      <input
        bind:this={input}
        bind:value={phrase}
        type="text"
        autocomplete="off"
        autocapitalize="off"
        spellcheck="false"
        aria-describedby={error ? "unlock-error" : undefined}
      />
    </label>
    {#if error}
      <p id="unlock-error" class="problem" role="alert">{error}</p>
    {/if}
    <div class="actions">
      <button type="button" class="button" onclick={() => dialog?.close()}>Keep stopped</button>
      <button type="submit" class="button primary" disabled={busy || phrase.trim().toLowerCase() !== "unlock"}>
        Unlock
      </button>
    </div>
  </form>
</dialog>

<style>
  .control {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--s-2);
    min-width: 148px;
    min-height: 52px;
    padding: 0 var(--s-5);
    border-radius: var(--radius);
    font-family: var(--font-text);
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 0.08em;
    cursor: pointer;
  }

  .stop {
    background: var(--blocked);
    color: var(--bg);
    border: 2px solid var(--blocked);
    box-shadow: inset 0 0 0 2px var(--bg);
  }

  .stop:hover {
    box-shadow: inset 0 0 0 3px var(--bg);
  }

  .stop:disabled {
    cursor: progress;
  }

  .stop:focus-visible {
    outline: 3px solid var(--text);
    outline-offset: 3px;
  }

  .unlock {
    color: var(--blocked);
    letter-spacing: 0.08em;
  }

  .unlock-dialog {
    width: min(460px, calc(100vw - 32px));
    padding: var(--s-5);
    border: var(--rule);
    border-radius: var(--radius);
    background: var(--bg);
    color: var(--text);
  }

  .unlock-dialog::backdrop {
    background: color-mix(in srgb, var(--text) 35%, transparent);
  }

  form {
    display: grid;
    gap: var(--s-4);
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: var(--s-2);
    flex-wrap: wrap;
  }

  @media (max-width: 767px) {
    .control {
      min-width: 112px;
      min-height: 48px;
      padding: 0 var(--s-4);
      font-size: 18px;
    }
  }
</style>
