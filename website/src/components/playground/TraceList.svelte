<script lang="ts">
  import type { Exchange } from "../../lib/playground/types";
  import { arrowSvg, directionWord, payloadHtml } from "../../lib/trace";

  interface Props {
    exchanges: Exchange[];
  }

  let { exchanges }: Props = $props();
</script>

<div class="trace log" tabindex="0" aria-label="Message log, newest first">
  {#if exchanges.length === 0}
    <p class="empty">No messages yet. Send a request to see the hub's answer.</p>
  {:else}
    <ol class="exchanges">
      {#each exchanges as exchange (exchange.key)}
        <li class={`exchange ${exchange.who}`}>
          <p class="who">{exchange.who === "person" ? "Person" : "Agent"} · {exchange.client}</p>
          <ol>
            {#each exchange.entries as entry, index (index)}
              <li class="enter">
                {@html arrowSvg(entry.kind === "request" ? "out" : "in", entry.kind === "notification")}
                <span class="visually-hidden">{directionWord(entry)}</span>
                <div class="line">
                  {#if entry.kind === "error"}
                    <span class="head error-head"><span class="outcome-error">error {entry.code} {entry.name}</span></span>
                    <span class="reason">{entry.reason}</span>
                  {:else}
                    <span class="head">
                      {#if entry.kind === "result"}
                        <span class="outcome-result">result</span>
                      {:else}
                        <span class="method">{entry.method}</span>
                      {/if}
                      <span class="payload">{@html payloadHtml(entry.kind === "result" ? entry.result : entry.params)}</span>
                    </span>
                  {/if}
                </div>
              </li>
            {/each}
          </ol>
        </li>
      {/each}
    </ol>
  {/if}
</div>

<style>
  .log {
    max-height: 520px;
    overflow-y: auto;
  }

  .empty {
    font-family: var(--font-text);
    color: var(--text-2);
  }

  .exchanges {
    gap: var(--s-4) !important;
  }

  .exchange {
    display: block !important;
    padding: var(--s-2) var(--s-3);
    border-radius: 4px;
  }

  .exchange.agent {
    border-left: 2px dashed var(--text-2);
  }

  .exchange.person {
    border-left: 4px solid var(--text);
    background: var(--bg);
  }

  .exchange > ol {
    margin-top: var(--s-1) !important;
  }
</style>
