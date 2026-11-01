import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { Slot } from "radix-ui";

/**
 * shadcn/ui's Badge restyled for a status word. DESIGN.md keeps a status out of any box, tint or
 * shape, so the badge is the word alone in bold, in its status color.
 */
const badgeVariants = cva("inline text-sm leading-[1.4] font-bold whitespace-nowrap", {
  variants: {
    variant: {
      ok: "text-ok",
      confirm: "text-confirm",
      blocked: "text-blocked",
      unverified: "font-semibold text-unverified",
      neutral: "font-semibold text-muted-foreground",
    },
  },
  defaultVariants: {
    variant: "neutral",
  },
});

function Badge({ className, variant = "neutral", asChild = false, ...props }: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span";

  return <Comp data-slot="badge" data-variant={variant} className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
