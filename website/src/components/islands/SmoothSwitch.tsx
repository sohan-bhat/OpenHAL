import * as React from "react";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { choose, onReduceChange, smoothState } from "../landing/smooth-switch";

/**
 * The Smooth scrolling switch beside How it works' heading, shadcn/ui's Switch and Label on Radix.
 * The page's head script draws the stored choice before this island loads, and the island loads
 * when a person points at, focuses or presses the switch.
 */
export default function SmoothSwitch() {
  const id = React.useId();
  const root = React.useRef<HTMLButtonElement>(null);
  const [state, setState] = React.useState({ on: false, disabled: false });
  const [synced, setSynced] = React.useState(false);

  React.useEffect(() => {
    const sync = () => setState(smoothState());
    sync();
    setSynced(true);
    return onReduceChange(sync);
  }, []);

  React.useEffect(() => {
    if (synced) root.current?.dispatchEvent(new Event("oh:island-ready", { bubbles: true }));
  }, [synced]);

  return (
    <Label htmlFor={id} className="cursor-pointer font-normal text-muted-foreground has-disabled:cursor-default">
      <Switch
        ref={root}
        id={id}
        checked={state.on}
        disabled={state.disabled}
        onCheckedChange={(on) => {
          setState((now) => ({ ...now, on }));
          choose(on);
        }}
      />
      Smooth scrolling
    </Label>
  );
}
