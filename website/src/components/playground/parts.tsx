import type { FormEvent, ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import * as m from "motion/react-m";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useTimings } from "@/components/ui/motion";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { Request } from "@/lib/kernel";
import { heldWhat } from "@/lib/playground/session";

export interface StopProps {
  stopped: boolean;
  ready: boolean;
  inputId: string;
  unlockText: string;
  unlockError: string;
  onUnlockText: (text: string) => void;
  onStop: () => void;
  onUnlock: (event: FormEvent<HTMLFormElement>) => void;
}

/** The stop, which any client may send, and once stopped the field where a person types unlock. */
export function StopArea({ stopped, ready, inputId, unlockText, unlockError, onUnlockText, onStop, onUnlock }: StopProps) {
  return (
    <div className={stopped ? "stop-area is-stopped" : "stop-area"}>
      {stopped ? (
        <form className="stopped-row" onSubmit={onUnlock}>
          <p className="status blocked">stopped</p>
          <Label className="visually-hidden" htmlFor={inputId}>
            Type unlock to lift the stop
          </Label>
          <Input id={inputId} className="mono pg-field" placeholder="type unlock" value={unlockText} onChange={(event) => onUnlockText(event.target.value)} autoComplete="off" />
          <Button type="submit" variant="outline" className="pg-person">
            Unlock
          </Button>
          {unlockError ? (
            <p className="unlock-error" aria-live="polite">
              {unlockError}
            </p>
          ) : null}
        </form>
      ) : (
        <>
          <Button type="button" variant="outline" className="stop" onClick={onStop} disabled={!ready}>
            Stop
          </Button>
          <p className="muted">Any client may send a stop, but lifting the stop takes a person's token.</p>
        </>
      )}
    </div>
  );
}

/** The requests the hub holds for a person, each with Approve and Reject. */
export function Held({ pending, heading, onDecide }: { pending: Request[]; heading: ReactNode; onDecide: (requestId: string, approve: boolean) => void }) {
  return (
    <div className="waiting">
      <p className="waiting-head">{heading}</p>
      <ul>
        {pending.map((request) => (
          <li key={request.requestId}>
            <span className="mono">{heldWhat(request)}</span>
            <span className="decide">
              <Button type="button" variant="outline" className="pg-person" onClick={() => onDecide(request.requestId, true)}>
                Approve
              </Button>
              <Button type="button" variant="outline" onClick={() => onDecide(request.requestId, false)}>
                Reject
              </Button>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface PickerProps {
  id: string;
  value: string;
  onChange: (value: string) => void;
  items: Array<{ value: string; label: string }>;
}

/**
 * One of the request form's choices on shadcn/ui's Select (Radix). The list opens 4 px under its
 * button, words only, with the current choice in bold on the surface highlight.
 */
export function Picker({ id, value, onChange, items }: PickerProps) {
  const shown = items.find((item) => item.value === value)?.label;
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id} className="pg-select">
        <SelectValue>{shown}</SelectValue>
      </SelectTrigger>
      <SelectContent position="popper" sideOffset={4} className="pg-list">
        {items.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

/** The builder's chevron, which turns a quarter turn on the site's ease while the builder is open. */
export function Chevron({ open }: { open: boolean }) {
  const { open: enter, close } = useTimings();
  return (
    <m.span aria-hidden="true" className="pg-chevron" initial={false} animate={{ rotate: open ? 90 : 0 }} transition={open ? enter : close}>
      <ChevronRight strokeWidth={2} />
    </m.span>
  );
}
