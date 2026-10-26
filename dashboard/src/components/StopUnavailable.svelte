<script lang="ts">
  let { why, host }: { why: "unpaired" | "offline"; host: string } = $props();
</script>

<aside class="stop-unavailable" aria-labelledby="stop-unavailable-title">
  <p id="stop-unavailable-title" class="title">
    <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" stroke-width="2" />
      <path d="M5.5 10h9" stroke="currentColor" stroke-width="2.5" />
    </svg>
    {why === "unpaired" ? "STOP needs a paired browser" : "STOP can't reach the hub"}
  </p>
  {#if why === "unpaired"}
    <p>
      The hub refuses commands from a browser it hasn't paired with. Stop every device with
      <code>openhal stop</code> on the hub's machine.
    </p>
  {:else}
    <p>
      No browser or agent can send STOP to <code class="nobreak">{host}</code> until the hub answers again. OpenHAL
      firmware boards fall to their safe state on their own when the hub's heartbeat stops. Use the hardware e-stop
      for anything else.
    </p>
  {/if}
</aside>

<style>
  .stop-unavailable {
    display: grid;
    gap: var(--s-1);
    max-width: 420px;
    padding: var(--s-3) var(--s-4);
    border: 2px solid var(--blocked);
    border-radius: var(--radius);
    background: var(--bg);
  }

  .title {
    display: flex;
    align-items: center;
    gap: var(--s-2);
    font-weight: 800;
    letter-spacing: 0.02em;
    color: var(--blocked);
  }

  .title svg {
    flex: none;
  }

  p {
    font-size: var(--t-ui);
  }
</style>
