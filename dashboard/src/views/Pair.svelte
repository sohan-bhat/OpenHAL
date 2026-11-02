<script lang="ts">
  import wordmarkLight from "../../../docs/assets/wordmark-light.svg";
  import wordmarkDark from "../../../docs/assets/wordmark-dark.svg";
  import { Button } from "$lib/components/ui/button/index.js";
  import { Input } from "$lib/components/ui/input/index.js";
  import { Label } from "$lib/components/ui/label/index.js";
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
  <div class="brand"><picture class="wordmark"><source srcset={wordmarkDark} media="(prefers-color-scheme: dark)" /><img src={wordmarkLight} alt="OpenHAL" width="88" height="24" /></picture> <span class="muted">Inspector</span></div>
  <StopUnavailable why="unpaired" {host} />
</header>
<main class="pair" id="main">
  <section aria-labelledby="pair-title">
    <h1 id="pair-title">Pair this browser with the hub</h1>
    <p>The Inspector acts as you, a human Principal. Run this on the machine that runs the hub, then enter the code.</p>
    <pre class="command"><code>openhal pair</code></pre>
    <form onsubmit={pair}>
      <div class="field">
        <Label for="pair-code">Pairing code</Label>
        <Input
          id="pair-code"
          type="text"
          inputmode="numeric"
          autocomplete="one-time-code"
          pattern={"[0-9]{6}"}
          maxlength={6}
          bind:value={code}
          aria-describedby={error ? "pair-error" : "pair-help"}
          aria-invalid={error ? "true" : undefined}
          class="w-[12ch] font-mono text-2xl tracking-[0.15em]"
        />
      </div>
      <p id="pair-help" class="muted">Six digits. Each code works once and expires after 300 s.</p>
      {#if error}<p id="pair-error" class="problem" role="alert">{error}</p>{/if}
      <Button variant="primary" class="justify-self-start" type="submit" disabled={busy || !/^\d{6}$/.test(code.trim())}>Pair</Button>
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
    display: block;
    line-height: 0;
  }

  .wordmark img {
    display: block;
    width: auto;
    height: 24px;
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
</style>
