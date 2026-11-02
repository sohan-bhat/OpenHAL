import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { Slot } from "radix-ui";

const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-md text-sm font-semibold whitespace-nowrap no-underline disabled:pointer-events-none disabled:opacity-55 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "border border-accent bg-accent-fill text-on-accent [box-shadow:var(--oh-control-ring)_var(--accent)] transition-[background-color,transform] duration-(--motion-status) hover:bg-accent-fill-hover motion-safe:hover:[transform:translateY(-1px)]",
        outline:
          "border border-input bg-background text-foreground [box-shadow:var(--oh-control-ring)_var(--oh-control-border)] hover:border-muted-foreground hover:[box-shadow:var(--oh-control-ring)_var(--text-2)] aria-disabled:cursor-default aria-disabled:text-muted-foreground aria-disabled:hover:border-input aria-disabled:hover:[box-shadow:var(--oh-control-ring)_var(--oh-control-border)]",
        ghost: "bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
        link: "font-bold text-neutral underline decoration-1 underline-offset-[3px] hover:decoration-2",
      },
      size: {
        default: "h-10 px-4",
        lg: "h-12 px-4 text-base md:px-6",
        sm: "h-9 px-3",
        inline: "h-auto p-0",
        icon: "size-10",
        "icon-sm": "size-8",
        "icon-xs": "size-6 rounded-sm",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

/** shadcn/ui's Button on the site's tokens: the house primary on the pink fill with near-black text, outline, ghost and link buttons. */
function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot.Root : "button";

  return <Comp data-slot="button" data-variant={variant} data-size={size} className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}

export { Button, buttonVariants };
