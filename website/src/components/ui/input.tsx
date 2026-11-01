import * as React from "react";
import { cn } from "@/lib/utils";

/** shadcn/ui's Input on the site's tokens: a 40 px field with the 1.5 px control outline, no shadow and the accent focus ring. */
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 text-base text-foreground [box-shadow:var(--oh-control-ring)_var(--oh-control-border)] outline-offset-2 selection:bg-primary selection:text-primary-foreground placeholder:text-muted-foreground hover:border-muted-foreground hover:[box-shadow:var(--oh-control-ring)_var(--text-2)] focus-visible:outline-2 focus-visible:outline-accent disabled:pointer-events-none disabled:border-border disabled:bg-muted disabled:text-muted-foreground",
        "aria-invalid:border-destructive",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
