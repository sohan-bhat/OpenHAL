<script lang="ts">
	import { Select as SelectPrimitive } from "bits-ui";
	import ChevronDownIcon from "@lucide/svelte/icons/chevron-down";
	import { cn, type WithoutChild } from "$lib/utils.js";

	let {
		ref = $bindable(null),
		class: className,
		children,
		size = "default",
		...restProps
	}: WithoutChild<SelectPrimitive.TriggerProps> & {
		size?: "sm" | "default";
	} = $props();
</script>

<SelectPrimitive.Trigger
	bind:ref
	data-slot="select-trigger"
	data-size={size}
	class={cn(
		"flex w-full min-w-0 cursor-pointer items-center justify-between gap-2 rounded-md border border-input bg-background pr-2 pl-2 text-left text-foreground whitespace-nowrap select-none [box-shadow:var(--control-ring)_var(--control-border)] transition-[border-color,box-shadow] data-[size=default]:min-h-9 data-[size=default]:text-base data-[size=sm]:min-h-8 data-[size=sm]:text-sm data-placeholder:text-muted-foreground not-disabled:hover:border-muted-foreground not-disabled:hover:[box-shadow:var(--control-ring)_var(--text-2)] disabled:cursor-not-allowed disabled:border-muted disabled:bg-muted disabled:text-muted-foreground disabled:[box-shadow:none] [&_svg]:pointer-events-none [&_svg]:shrink-0",
		className
	)}
	{...restProps}
>
	<span class="min-w-0 truncate">{@render children?.()}</span>
	<ChevronDownIcon class="size-4 text-muted-foreground" aria-hidden="true" />
</SelectPrimitive.Trigger>
