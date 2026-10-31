<script lang="ts">
  let { why, host }: { why: "unpaired" | "offline"; host: string } = $props();
</script>

<aside class="stop-unavailable" aria-labelledby="stop-unavailable-title">
  <p id="stop-unavailable-title" class="title">
    {why === "unpaired" ? "STOP needs a paired browser" : "STOP can't reach the hub"}
  </p>
  {#if why === "unpaired"}
    <p>
      The hub blocks commands from a browser that isn't paired with the hub. Stop every device with
      <code>openhal stop</code> on the hub's machine.
    </p>
  {:else}
    <p>
      No browser or agent can send STOP to <code class="nobreak">{host}</code> until the hub is reachable again. OpenHAL
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
    border-radius: var(--radius);
    background: var(--surface);
  }

  .title {
    font-weight: 800;
    letter-spacing: 0.02em;
    color: var(--blocked);
  }

  p {
    font-size: var(--t-ui);
  }
</style>
