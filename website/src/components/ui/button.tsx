import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { Slot } from "radix-ui";

const buttonVariants = cva(
  "inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-md text-sm font-semibold whitespace-nowrap disabled:pointer-events-none disabled:opacity-55 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default:
          "border border-accent bg-accent-fill text-on-accent [box-shadow:var(--oh-control-ring)_var(--accent)] transition-[background-color,translate] duration-(--motion-status) hover:bg-accent-fill-hover motion-safe:hover:-translate-y-px",
        outline: "border border-input bg-background text-foreground [box-shadow:var(--oh-control-ring)_var(--oh-control-border)] hover:border-muted-foreground hover:[box-shadow:var(--oh-control-ring)_var(--text-2)]",
        ghost: "bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
        link: "text-accent underline underline-offset-[3px] hover:decoration-2",
      },
      size: {
        default: "h-10 px-4",
        sm: "h-9 px-3",
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
