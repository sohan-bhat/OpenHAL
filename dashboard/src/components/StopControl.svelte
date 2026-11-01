<script lang="ts">
  import { Button } from "$lib/components/ui/button/index.js";
  import * as Dialog from "$lib/components/ui/dialog/index.js";
  import { Input } from "$lib/components/ui/input/index.js";
  import { Label } from "$lib/components/ui/label/index.js";
  import { inspector } from "../lib/state.svelte";

  const stopped = $derived(inspector.status?.stopped ?? false);
  let busy = $state(false);
  let open = $state(false);
  let phrase = $state("");
  let error = $state<string | null>(null);
  let input = $state<HTMLInputElement | null>(null);

  async function stop() {
    busy = true;
    await inspector.stop();
    busy = false;
  }

  function opening(next: boolean) {
    if (!next) return;
    phrase = "";
    error = null;
  }

  function focusPhrase(event: Event) {
    event.preventDefault();
    input?.focus();
  }

  async function unlock(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = await inspector.unlock(phrase);
    busy = false;
    if (!error) open = false;
  }
</script>

<Dialog.Root bind:open onOpenChange={opening}>
  {#if stopped}
    <Dialog.Trigger aria-describedby="stopped-state">
      {#snippet child({ props })}
        <Button {...props} class="unlock text-blocked tracking-[0.08em]">UNLOCK</Button>
      {/snippet}
    </Dialog.Trigger>
  {:else}
    <Button variant="stop" size="stop" class="control stop" onclick={stop} disabled={busy} aria-label="STOP every device">STOP</Button>
  {/if}

  <Dialog.Content class="unlock-dialog" interactOutsideBehavior="ignore" onOpenAutoFocus={focusPhrase}>
    <form class="grid gap-4" onsubmit={unlock}>
      <Dialog.Title>Lift the stop</Dialog.Title>
      <Dialog.Description>
        Every device was put in its safe state. Every command stays blocked until a person types the phrase
        <code>unlock</code>.
      </Dialog.Description>
      <div class="field">
        <Label for="unlock-phrase">Phrase</Label>
        <Input
          id="unlock-phrase"
          bind:ref={input}
          bind:value={phrase}
          type="text"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
          aria-describedby={error ? "unlock-error" : undefined}
        />
      </div>
      {#if error}
        <p id="unlock-error" class="problem" role="alert">{error}</p>
      {/if}
      <Dialog.Footer>
        <Dialog.Close>
          {#snippet child({ props })}
            <Button {...props}>Keep stopped</Button>
          {/snippet}
        </Dialog.Close>
        <Button type="submit" variant="primary" disabled={busy || phrase.trim().toLowerCase() !== "unlock"}>Unlock</Button>
      </Dialog.Footer>
    </form>
  </Dialog.Content>
</Dialog.Root>
