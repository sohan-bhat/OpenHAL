<script lang="ts">
  import Mark from "../components/Mark.svelte";
  import StopUnavailable from "../components/StopUnavailable.svelte";
  import { api } from "../lib/api";

  let { onpaired }: { onpaired: () => void } = $props();

  let code = $state("");
  let error = $state<string | null>(null);
  let busy = $state(false);
  const host = typeof location === "undefined" ? "" : location.host;

  async function pair(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = null;
    try {
      await api.pair(code.trim());
      onpaired();
    } catch (failure) {
      error = failure instanceof Error ? failure.message : "Pairing failed.";
    }
    busy = false;
  }
</script>

<header class="bar">
  <div class="brand"><Mark size={28} /><span class="wordmark">OpenHAL</span> <span class="muted">Inspector</span></div>
  <StopUnavailable why="unpaired" {host} />
</header>
<main class="pair" id="main">
  <section aria-labelledby="pair-title">
    <h1 id="pair-title">Pair this browser with the hub</h1>
    <p>The Inspector acts as you, a human Principal. Run this on the machine that runs the hub, then enter the code.</p>
    <pre class="command"><code>openhal pair</code></pre>
    <form onsubmit={pair}>
      <label class="field">
        <span>Pairing code</span>
        <input
          type="text"
          inputmode="numeric"
          autocomplete="one-time-code"
          pattern={"[0-9]{6}"}
          maxlength="6"
          bind:value={code}
          aria-describedby={error ? "pair-error" : "pair-help"}
          aria-invalid={error ? "true" : undefined}
        />
      </label>
      <p id="pair-help" class="muted">Six digits. Each code works once and expires after 300 s.</p>
      {#if error}<p id="pair-error" class="problem" role="alert">{error}</p>{/if}
      <button class="button primary" type="submit" disabled={busy || !/^\d{6}$/.test(code.trim())}>Pair</button>
    </form>
  </section>
</main>

<style>
  .bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--s-4) var(--s-6);
    padding: var(--s-3) var(--s-5);
    border-bottom: var(--rule);
  }

  .pair {
    display: grid;
    gap: var(--s-6);
    max-width: 520px;
    margin: 0 auto;
    padding: var(--s-7) var(--s-4);
  }

  @media (max-width: 767px) {
    .bar {
      padding: var(--s-3) var(--s-4);
    }

    .pair {
      padding-top: var(--s-5);
    }
  }

  .brand {
    display: flex;
    align-items: center;
    gap: var(--s-2);
    font-size: 20px;
  }

  .wordmark {
    font-weight: 700;
  }

  section,
  form {
    display: grid;
    gap: var(--s-4);
  }

  h1 {
    font-size: 26px;
  }

  .command {
    padding: var(--s-3) var(--s-4);
    border: var(--rule);
    border-radius: var(--radius);
    background: var(--surface);
  }

  input {
    width: 12ch;
    font-family: var(--font-mono);
    font-size: 20px;
    letter-spacing: 0.15em;
  }

  form .button {
    justify-self: start;
  }
</style>
