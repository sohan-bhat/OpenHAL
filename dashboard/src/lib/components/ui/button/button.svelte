<script lang="ts" module>
	import { type VariantProps, tv } from "tailwind-variants";
	import { cn, type WithElementRef } from "$lib/utils.js";
	import type { HTMLAnchorAttributes, HTMLButtonAttributes } from "svelte/elements";

	export const buttonVariants = tv({
		base: "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-md border font-semibold no-underline select-none transition-[background-color,border-color,color,box-shadow,translate] disabled:cursor-not-allowed [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
		variants: {
			variant: {
				primary:
					"border-accent bg-primary text-primary-foreground [box-shadow:var(--control-ring)_var(--accent)] not-disabled:hover:bg-accent-fill-hover motion-safe:not-disabled:hover:-translate-y-px disabled:border-muted disabled:bg-muted disabled:text-muted-foreground disabled:[box-shadow:none]",
				outline:
					"border-input bg-background text-foreground [box-shadow:var(--control-ring)_var(--control-border)] not-disabled:hover:border-muted-foreground not-disabled:hover:[box-shadow:var(--control-ring)_var(--text-2)] disabled:border-muted disabled:bg-muted disabled:text-muted-foreground disabled:[box-shadow:none]",
				ghost:
					"border-transparent bg-transparent text-muted-foreground not-disabled:hover:bg-muted not-disabled:hover:text-foreground",
				link: "border-0 bg-transparent font-normal text-accent underline underline-offset-2 not-disabled:hover:decoration-2",
				stop: "border-2 border-blocked bg-blocked text-background [box-shadow:inset_0_0_0_2px_var(--bg)] not-disabled:hover:[box-shadow:inset_0_0_0_3px_var(--bg)] disabled:cursor-progress focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-foreground",
			},
			size: {
				default: "min-h-9 px-4 text-base",
				sm: "min-h-[30px] px-3 text-sm",
				inline: "h-auto p-0 text-sm",
				stop: "min-h-12 min-w-28 px-4 text-xl font-extrabold tracking-[0.08em] md:min-h-[52px] md:min-w-[148px] md:px-6 md:text-2xl",
			},
		},
		defaultVariants: {
			variant: "outline",
			size: "default",
		},
	});

	export type ButtonVariant = VariantProps<typeof buttonVariants>["variant"];
	export type ButtonSize = VariantProps<typeof buttonVariants>["size"];

	export type ButtonProps = WithElementRef<HTMLButtonAttributes> &
		WithElementRef<HTMLAnchorAttributes> & {
			variant?: ButtonVariant;
			size?: ButtonSize;
		};
</script>

<script lang="ts">
	let {
		class: className,
		variant = "outline",
		size = "default",
		ref = $bindable(null),
		href = undefined,
		type = "button",
		disabled,
		children,
		...restProps
	}: ButtonProps = $props();
</script>

{#if href}
	<a
		bind:this={ref}
		data-slot="button"
		data-variant={variant}
		class={cn(buttonVariants({ variant, size }), className)}
		href={disabled ? undefined : href}
		aria-disabled={disabled}
		role={disabled ? "link" : undefined}
		tabindex={disabled ? -1 : undefined}
		{...restProps}
	>
		{@render children?.()}
	</a>
{:else}
	<button
		bind:this={ref}
		data-slot="button"
		data-variant={variant}
		class={cn(buttonVariants({ variant, size }), className)}
		{type}
		{disabled}
		{...restProps}
	>
		{@render children?.()}
	</button>
{/if}
