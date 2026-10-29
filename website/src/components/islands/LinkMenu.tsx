import * as React from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { MotionRoot } from "@/components/ui/motion";
import { cn } from "@/lib/utils";
import { Chevron, PICKER, menuContainer } from "./picker";
import { useIslandReady, withBase } from "./ready";

export interface LinkItem {
  label: string;
  href: string;
  current: boolean;
  page: boolean;
}

interface Props {
  kind: "section" | "version";
  label: string;
  items: LinkItem[];
  placeholder?: string;
  align?: "start" | "end";
  place?: "header" | "menu";
}

/**
 * A picker whose choices are pages, the header's Section picker on a tablet and the specification's
 * version picker once spec/versions.json lists more than one version, on shadcn/ui's DropdownMenu.
 */
export default function LinkMenu({ kind, label, items, placeholder, align = "end", place = "header" }: Props) {
  const trigger = React.useRef<HTMLButtonElement>(null);
  useIslandReady(trigger);
  const current = items.find((item) => item.current);

  return (
    <MotionRoot>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button ref={trigger} type="button" data-picker={kind} className={PICKER}>
            {(current || !placeholder) && <span className="sr-only">{label} </span>}
            <span className="grid text-start">
              {items.map((item) => (
                <span key={item.href} className={cn("[grid-area:1/1]", !item.current && "invisible")}>
                  {item.label}
                </span>
              ))}
              {placeholder && <span className={cn("[grid-area:1/1]", current && "invisible")}>{placeholder}</span>}
            </span>
            <Chevron />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align={align} aria-label={label} container={menuContainer(place)}>
          {items.map((item) => (
            <DropdownMenuItem key={item.href} asChild>
              <a href={withBase(item.href)} aria-current={item.current ? (item.page ? "page" : "true") : undefined}>
                {item.label}
              </a>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </MotionRoot>
  );
}
