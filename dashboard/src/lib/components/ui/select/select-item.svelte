<script lang="ts">
	import { Select as SelectPrimitive } from "bits-ui";
	import { cn, type WithoutChild } from "$lib/utils.js";

	let {
		ref = $bindable(null),
		class: className,
		value,
		label,
		children: childrenProp,
		...restProps
	}: WithoutChild<SelectPrimitive.ItemProps> = $props();
</script>

<SelectPrimitive.Item
	bind:ref
	{value}
	{label}
	data-slot="select-item"
	class={cn(
		"relative flex min-h-8 w-full cursor-pointer items-center rounded-sm px-2 py-1 text-base text-foreground outline-none select-none data-highlighted:bg-muted data-selected:font-bold data-disabled:cursor-not-allowed data-disabled:text-muted-foreground",
		className
	)}
	{...restProps}
>
	{#snippet children({ selected, highlighted })}
		<span class="whitespace-nowrap">
			{#if childrenProp}
				{@render childrenProp({ selected, highlighted })}
			{:else}
				{label || value}
			{/if}
		</span>
	{/snippet}
</SelectPrimitive.Item>
