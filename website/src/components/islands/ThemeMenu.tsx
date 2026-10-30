import * as React from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { MotionRoot } from "@/components/ui/motion";
import { cn } from "@/lib/utils";
import { Chevron, PICKER, menuContainer } from "./picker";
import { useIslandReady } from "./ready";

type Theme = "auto" | "light" | "dark";

const CHOICES: Array<{ value: Theme; label: string; shown: string }> = [
  { value: "auto", label: "Auto", shown: "[:root[data-theme-choice=auto]_&]:visible" },
  { value: "light", label: "Light", shown: "[:root[data-theme-choice=light]_&]:visible" },
  { value: "dark", label: "Dark", shown: "[:root[data-theme-choice=dark]_&]:visible" },
];

const KEY = "starlight-theme";

function stored(): Theme {
  const value = typeof document === "undefined" ? "auto" : document.documentElement.dataset.themeChoice;
  return value === "light" || value === "dark" ? value : "auto";
}

/** Applies a theme the way Starlight's own picker does, and keeps the choice in this browser. */
function apply(theme: Theme): void {
  const root = document.documentElement;
  root.dataset.themeChoice = theme;
  root.dataset.theme = theme === "auto" ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark") : theme;
  try {
    localStorage.setItem(KEY, theme === "auto" ? "" : theme);
  } catch {}
}

/**
 * The theme picker, Auto, Light and Dark, on shadcn/ui's DropdownMenu (Radix) with Motion. The
 * button's word comes from the choice the page's head script read, so it is right before the island
 * loads, and Auto follows the system.
 */
export default function ThemeMenu({ place = "header" }: { place?: "header" | "menu" }) {
  const [choice, setChoice] = React.useState<Theme>("auto");
  const trigger = React.useRef<HTMLButtonElement>(null);
  useIslandReady(trigger);

  React.useEffect(() => setChoice(stored()), []);

  return (
    <MotionRoot>
      <DropdownMenu onOpenChange={(open) => open && setChoice(stored())}>
        <DropdownMenuTrigger asChild>
          <button ref={trigger} type="button" data-picker="theme" className={PICKER}>
            <span className="sr-only">Theme</span>
            <span className="grid text-start">
              {CHOICES.map((item) => (
                <span key={item.value} className={cn("invisible [grid-area:1/1]", item.shown)}>
                  {item.label}
                </span>
              ))}
            </span>
            <Chevron />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" aria-label="Theme" container={menuContainer(place)}>
          <DropdownMenuRadioGroup
            value={choice}
            onValueChange={(value) => {
              const next = value as Theme;
              setChoice(next);
              apply(next);
            }}
          >
            {CHOICES.map((item) => (
              <DropdownMenuRadioItem key={item.value} value={item.value}>
                {item.label}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </MotionRoot>
  );
}
