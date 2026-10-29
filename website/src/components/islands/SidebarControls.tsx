import * as React from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { isShortcut } from "../../directives/intent";
import { isCollapsed, isPeeking, setCollapsed, setPeek, start, subscribe } from "../../lib/sidebar";
import { Button } from "@/components/ui/button";
import { Kbd } from "@/components/ui/kbd";
import { MotionRoot } from "@/components/ui/motion";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useIslandReady } from "./ready";

const DWELL = 150;
const AWAY = 120;
const EDGE = 400;

const ICON = "size-[18px]";

function Shortcut() {
  return (
    <Kbd>
      <span className="[:root[data-platform=mac]_&]:hidden">Ctrl</span>
      <span className="[:root:not([data-platform=mac])_&]:hidden">⌘</span>
      <span>B</span>
    </Kbd>
  );
}

/**
 * The button at the top of the documentation sidebar that hides it, shadcn/ui's Button and Tooltip.
 * Command or Control and B does the same anywhere on the page.
 */
export function SidebarHide() {
  const button = React.useRef<HTMLButtonElement>(null);
  useIslandReady(button);
  return (
    <MotionRoot>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              ref={button}
              variant="ghost"
              size="icon-sm"
              data-sidebar-hide=""
              aria-label="Hide sidebar"
              aria-controls="starlight__sidebar"
              aria-expanded="true"
              aria-keyshortcuts="Control+B Meta+B"
              onClick={() => setCollapsed(true, { handoff: true })}
            >
              <PanelLeftClose aria-hidden="true" strokeWidth={1.75} className={ICON} />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="right">
            Hide sidebar <Shortcut />
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </MotionRoot>
  );
}

/**
 * What stays of the sidebar while it is hidden: a button in the same place as the one that hid it,
 * and the window's left edge. A pointer resting on either for 150 ms brings the sidebar in as a
 * narrower panel, which leaves 120 ms after the pointer does, or 400 ms after the pointer leaves by
 * the window's edge. Touch never peeks, Escape sends the panel away, and the button brings the
 * sidebar back for good.
 */
export default function SidebarRail() {
  const button = React.useRef<HTMLButtonElement>(null);
  const timer = React.useRef(0);
  const [tip, setTip] = React.useState(false);
  const peeking = React.useSyncExternalStore(subscribe, isPeeking, () => false);
  useIslandReady(button);

  const enter = React.useCallback((event: PointerEvent | React.PointerEvent) => {
    if (event.pointerType === "touch" || !isCollapsed()) return;
    window.clearTimeout(timer.current);
    if (isPeeking() && !document.documentElement.hasAttribute("data-sidebar-leaving")) return;
    timer.current = window.setTimeout(() => setPeek(true), DWELL);
  }, []);

  const leave = React.useCallback((event: PointerEvent | React.PointerEvent) => {
    if (event.pointerType === "touch") return;
    window.clearTimeout(timer.current);
    const byEdge = event.clientX <= 24 || !event.relatedTarget;
    timer.current = window.setTimeout(() => setPeek(false), byEdge ? EDGE : AWAY);
  }, []);

  React.useEffect(() => {
    start();
    const pane = document.getElementById("starlight__sidebar");
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isPeeking()) {
        window.clearTimeout(timer.current);
        setPeek(false);
        return;
      }
      if (!isShortcut("mod+b", event)) return;
      event.preventDefault();
      window.clearTimeout(timer.current);
      setCollapsed(!isCollapsed());
    };
    document.addEventListener("keydown", onKey);
    pane?.addEventListener("pointerenter", enter);
    pane?.addEventListener("pointerleave", leave);
    return () => {
      document.removeEventListener("keydown", onKey);
      pane?.removeEventListener("pointerenter", enter);
      pane?.removeEventListener("pointerleave", leave);
      window.clearTimeout(timer.current);
    };
  }, [enter, leave]);

  return (
    <MotionRoot>
      <TooltipProvider>
        <div data-sidebar-rail="" className="hidden min-[50rem]:[:root[data-sidebar=collapsed]_&]:block">
          <div aria-hidden="true" data-sidebar-edge="" className="fixed top-(--sl-nav-height) bottom-0 left-0 z-6 w-[calc(var(--oh-gutter)+16px)]" onPointerEnter={enter} onPointerLeave={leave} />
          <Tooltip open={tip && !peeking} onOpenChange={setTip}>
            <TooltipTrigger asChild>
              <Button
                ref={button}
                variant="ghost"
                size="icon-sm"
                data-sidebar-show=""
                aria-label="Show sidebar"
                aria-controls="starlight__sidebar"
                aria-expanded="false"
                aria-keyshortcuts="Control+B Meta+B"
                className="fixed top-[calc(var(--sl-nav-height)+var(--oh-sidebar-head))] left-[calc(var(--oh-gutter)+var(--sl-sidebar-pad-x))] z-7"
                onClick={() => {
                  window.clearTimeout(timer.current);
                  setCollapsed(false, { handoff: true });
                }}
                onPointerEnter={enter}
                onPointerLeave={leave}
              >
                <PanelLeftOpen aria-hidden="true" strokeWidth={1.75} className={ICON} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">
              Show sidebar <Shortcut />
            </TooltipContent>
          </Tooltip>
        </div>
      </TooltipProvider>
    </MotionRoot>
  );
}
