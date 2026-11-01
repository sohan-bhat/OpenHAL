<script lang="ts">
  import { Label } from "$lib/components/ui/label/index.js";
  import * as Select from "$lib/components/ui/select/index.js";
  import { cn } from "$lib/utils";

  interface Option {
    value: string;
    label: string;
  }

  let {
    id,
    label,
    value = $bindable(""),
    options,
    disabled = false,
    size = "default",
    class: className = "",
    triggerClass = "",
    labelClass = "",
    describedby,
    onchange,
  }: {
    id: string;
    label: string;
    value?: string;
    options: Option[];
    disabled?: boolean;
    size?: "default" | "sm";
    class?: string;
    triggerClass?: string;
    labelClass?: string;
    describedby?: string;
    onchange?: (value: string) => void;
  } = $props();

  const shown = $derived(options.find((option) => option.value === value)?.label ?? "");
</script>

<div class={cn("field", className)}>
  <Label id="{id}-label" for={id} class={labelClass}>{label}</Label>
  <Select.Root type="single" bind:value {disabled} items={options} onValueChange={(next) => onchange?.(next)}>
    <Select.Trigger {id} {size} class={triggerClass} aria-labelledby="{id}-label" aria-describedby={describedby}>{shown}</Select.Trigger>
    <Select.Content>
      {#each options as option (option.value)}
        <Select.Item value={option.value} label={option.label} />
      {/each}
    </Select.Content>
  </Select.Root>
</div>
