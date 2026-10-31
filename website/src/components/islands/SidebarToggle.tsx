import * as React from "react";
import { Kbd } from "@/components/ui/kbd";
import { MotionRoot } from "@/components/ui/motion";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useSidebarOpen } from "@/hooks/use-sidebar-open";
import { moveOver } from "@/lib/sidebar-move";
import { useIslandReady } from "./ready";

/**
 * The sidebar's button at the far left of the header, shadcn/ui's SidebarTrigger with its Tooltip,
 * which names what a press does and the Tab key that does the same after a pointer press on the
 * page. It shares the sidebar's state through the root, so the button and the sidebar's own island
 * agree whichever loads first, and the sidebar's island alone listens for Tab.
 */
export default function SidebarToggle() {
  const open = useSidebarOpen();
  const button = React.useRef<HTMLButtonElement>(null);
  useIslandReady(button);

  return (
    <MotionRoot>
      <SidebarProvider open={open} onOpenChange={moveOver} shortcut={false} className="contents">
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <SidebarTrigger ref={button} aria-expanded={open} aria-controls="oh-sidebar" />
            </TooltipTrigger>
            <TooltipContent side="bottom" align="start">
              {open ? "Hide sidebar" : "Show sidebar"}
              <Kbd>Tab</Kbd>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </SidebarProvider>
    </MotionRoot>
  );
}
