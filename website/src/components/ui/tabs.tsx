import * as React from "react";
import { cn } from "@/lib/utils";
import { Tabs as TabsPrimitive } from "radix-ui";

/**
 * shadcn/ui's Tabs on Radix, drawn the house way. The list is a row of words, each tab 32 px
 * tall, the chosen tab sits in the text color on the highlight and any other tab turns the
 * surface gray under the pointer. Keyboard focus draws the site's 2 px ring, and a panel keeps the ring too.
 * Radix focuses a tab from script on a mouse press, which browsers treat as keyboard focus, so a tab
 * pressed with a mouse, pen or finger carries data-pointer-focus until the next key or blur, and the
 * ring skips it.
 */
function Tabs({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return <TabsPrimitive.Root data-slot="tabs" className={cn("flex flex-col gap-2", className)} {...props} />;
}

function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List data-slot="tabs-list" className={cn("inline-flex w-fit items-center gap-1 text-muted-foreground", className)} {...props} />;
}

function TabsTrigger({ className, onPointerDown, onKeyDown, onBlur, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      onPointerDown={(event) => {
        event.currentTarget.dataset.pointerFocus = "";
        onPointerDown?.(event);
      }}
      onKeyDown={(event) => {
        delete event.currentTarget.dataset.pointerFocus;
        onKeyDown?.(event);
      }}
      onBlur={(event) => {
        delete event.currentTarget.dataset.pointerFocus;
        onBlur?.(event);
      }}
      className={cn(
        "inline-flex h-8 shrink-0 cursor-pointer items-center justify-center rounded-sm border-0 bg-transparent px-3 text-sm font-medium whitespace-nowrap text-muted-foreground transition-[background-color,color] duration-(--motion-status) hover:text-foreground disabled:pointer-events-none disabled:opacity-55 data-[state=active]:bg-highlight data-[state=active]:text-foreground data-[state=inactive]:hover:bg-muted",
        className,
      )}
      {...props}
    />
  );
}

function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content data-slot="tabs-content" className={cn("flex-1", className)} {...props} />;
}

export { Tabs, TabsContent, TabsList, TabsTrigger };
