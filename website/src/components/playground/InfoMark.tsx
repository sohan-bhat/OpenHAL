import { useState } from "react";
import { AnimatePresence } from "motion/react";
import * as m from "motion/react-m";
import { Popover as PopoverPrimitive } from "radix-ui";
import { Button } from "@/components/ui/button";
import { useTimings } from "@/components/ui/motion";
import { Popover, PopoverTrigger } from "@/components/ui/popover";

interface Props {
  topic: string;
  text: string;
  href?: string;
}

/**
 * An information mark (docs/DESIGN.md, Information marks), a lowercase i in a 16 px circle that
 * opens a short note on shadcn/ui's Popover (Radix). A click, a tap, Enter or Space opens the note,
 * and Escape or a press outside closes the note with focus back on the mark. Motion fades the note
 * in over 200 ms and out over 150 ms, and with reduced motion the note opens and closes at once.
 */
export function InfoMark({ topic, text, href }: Props) {
  const [open, setOpen] = useState(false);
  const { open: enter, close } = useTimings();
  const name = `About ${topic}`;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="icon-xs" className="pg-info" aria-label={name}>
          i
        </Button>
      </PopoverTrigger>
      <AnimatePresence>
        {open && (
          <PopoverPrimitive.Portal forceMount>
            <PopoverPrimitive.Content forceMount asChild side="bottom" align="start" alignOffset={-8} sideOffset={8} collisionPadding={8} aria-label={name}>
              <m.div
                data-slot="popover-content"
                className="pg-info-pop"
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0, transition: enter }}
                exit={{ opacity: 0, y: -2, transition: close }}
              >
                {text}
                {href ? <a href={href}>Read more about {topic}</a> : null}
              </m.div>
            </PopoverPrimitive.Content>
          </PopoverPrimitive.Portal>
        )}
      </AnimatePresence>
    </Popover>
  );
}
