import * as m from "motion/react-m";
import { ChevronDown } from "lucide-react";
import { useMenuOpen } from "@/components/ui/dropdown-menu";
import { useTimings } from "@/components/ui/motion";

/**
 * What a picker's menu button, shadcn/ui's ghost Button at its small size, adds in the header and the
 * phone menu: a tighter fit around its word and chevron, never an icon, and the surface while open.
 */
export const PICKER = "gap-0.5 pr-1 pl-2 leading-[1.4] data-[state=open]:bg-muted data-[state=open]:text-foreground";

/** The chevron after a picker's word, which turns over in 200 ms while the list is open. */
export function Chevron() {
  const open = useMenuOpen();
  const { open: enter, close } = useTimings();
  return (
    <m.span aria-hidden="true" className="inline-flex" initial={false} animate={{ rotate: open ? 180 : 0 }} transition={open ? enter : close}>
      <ChevronDown strokeWidth={1.75} className="size-[18px]" />
    </m.span>
  );
}

/** Where a menu inside the phone menu renders its list: inside the menu, which sits in the top layer. */
export function menuContainer(place: "header" | "menu"): HTMLElement | undefined {
  if (place !== "menu" || typeof document === "undefined") return undefined;
  return document.getElementById("starlight__sidebar") ?? undefined;
}
