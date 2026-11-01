<script lang="ts">
	import { NavigationMenu as NavigationMenuPrimitive } from "bits-ui";
	import { cn } from "$lib/utils.js";

	let {
		ref = $bindable(null),
		class: className,
		children,
		...restProps
	}: NavigationMenuPrimitive.RootProps = $props();
</script>

<NavigationMenuPrimitive.Root
	bind:ref
	data-slot="navigation-menu"
	class={cn("relative", className)}
	{...restProps}
>
	{@render children?.()}
</NavigationMenuPrimitive.Root>
