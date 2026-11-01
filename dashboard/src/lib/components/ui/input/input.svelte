<script lang="ts">
	import { cn, type WithElementRef } from "$lib/utils.js";
	import type { HTMLInputAttributes, HTMLInputTypeAttribute } from "svelte/elements";

	type Props = WithElementRef<
		Omit<HTMLInputAttributes, "type"> & { type?: Exclude<HTMLInputTypeAttribute, "file"> }
	>;

	let {
		ref = $bindable(null),
		value = $bindable(),
		type,
		class: className,
		"data-slot": dataSlot = "input",
		...restProps
	}: Props = $props();
</script>

<input
	bind:this={ref}
	data-slot={dataSlot}
	class={cn(
		"min-h-9 w-full min-w-0 rounded-md border border-input bg-background px-2 py-1 text-base text-foreground [box-shadow:var(--control-ring)_var(--control-border)] transition-[border-color,box-shadow] placeholder:text-muted-foreground not-disabled:hover:border-muted-foreground not-disabled:hover:[box-shadow:var(--control-ring)_var(--text-2)] disabled:cursor-not-allowed disabled:border-muted disabled:bg-muted disabled:text-muted-foreground disabled:[box-shadow:none]",
		className
	)}
	{type}
	bind:value
	{...restProps}
/>
