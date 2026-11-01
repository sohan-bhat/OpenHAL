<script lang="ts">
	import { Slider as SliderPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";

	let {
		ref = $bindable(null),
		value = $bindable(0),
		id,
		label,
		valueText,
		min,
		max,
		step = 1,
		disabled = false,
		onValueChange,
		class: className,
	}: {
		ref?: HTMLElement | null;
		value?: number;
		id?: string;
		label: string;
		valueText?: string;
		min: number;
		max: number;
		step?: number;
		disabled?: boolean;
		onValueChange?: (value: number) => void;
		class?: string;
	} = $props();
</script>

<SliderPrimitive.Root
	bind:ref
	bind:value
	type="single"
	thumbPositioning="exact"
	{min}
	{max}
	{step}
	{disabled}
	{onValueChange}
	data-slot="slider"
	class={cn("relative flex h-7 w-full touch-none items-center select-none", className)}
>
	<span data-slot="slider-track" class="relative h-1 w-full grow rounded-xs bg-border"></span>
	<SliderPrimitive.Thumb
		data-slot="slider-thumb"
		index={0}
		{id}
		aria-label={label}
		aria-valuetext={valueText}
		class="block size-4 shrink-0 cursor-pointer rounded-full border-2 border-background bg-primary [box-shadow:0_0_0_1px_var(--accent)] data-disabled:cursor-not-allowed data-disabled:bg-muted-foreground data-disabled:[box-shadow:0_0_0_1px_var(--text-2)]"
	/>
</SliderPrimitive.Root>
