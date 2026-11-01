<script lang="ts">
	import { Checkbox as CheckboxPrimitive } from "bits-ui";
	import CheckIcon from "@lucide/svelte/icons/check";
	import { cn, type WithoutChildrenOrChild } from "$lib/utils.js";

	let {
		ref = $bindable(null),
		checked = $bindable(false),
		class: className,
		...restProps
	}: WithoutChildrenOrChild<CheckboxPrimitive.RootProps> = $props();
</script>

<CheckboxPrimitive.Root
	bind:ref
	data-slot="checkbox"
	class={cn(
		"peer flex size-[18px] shrink-0 cursor-pointer items-center justify-center rounded-sm border-[1.5px] border-muted-foreground bg-background text-primary-foreground transition-colors not-disabled:hover:border-foreground data-[state=checked]:border-accent data-[state=checked]:bg-primary data-[state=checked]:not-disabled:hover:border-accent disabled:cursor-not-allowed disabled:border-border",
		className
	)}
	bind:checked
	{...restProps}
>
	{#snippet children({ checked })}
		{#if checked}
			<CheckIcon class="size-3" strokeWidth={3} aria-hidden="true" />
		{/if}
	{/snippet}
</CheckboxPrimitive.Root>
