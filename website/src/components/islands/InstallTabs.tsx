import * as React from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { commandPieces, type InstallChannel } from "@/lib/install";

interface Props {
  channels: InstallChannel[];
  /** The tab list's name, such as "Install OpenHAL". */
  label: string;
}

/**
 * The hero's install box, shadcn/ui's Tabs on Radix with one command line per channel. Every
 * panel is rendered, so a page without a script still shows every command. The script right
 * after the box picks the visitor's system before this island loads, and the island loads when
 * a person points at, focuses or presses a tab, takes the same choice and says it is ready, so
 * the directive replays the first press. The Copy button beside the line is the site's own.
 */
export default function InstallTabs({ channels, label }: Props) {
  const root = React.useRef<HTMLDivElement>(null);
  const [value, setValue] = React.useState(channels[0]?.id ?? "");
  const [synced, setSynced] = React.useState(false);

  React.useEffect(() => {
    const chosen = root.current?.closest<HTMLElement>("[data-install]")?.dataset.default;
    if (chosen && channels.some((channel) => channel.id === chosen)) setValue(chosen);
    for (const tab of root.current?.querySelectorAll<HTMLElement>("[role=tab]") ?? []) tab.tabIndex = -1;
    setSynced(true);
  }, [channels]);

  React.useEffect(() => {
    if (synced) root.current?.dispatchEvent(new Event("oh:island-ready", { bubbles: true }));
  }, [synced]);

  return (
    <Tabs ref={root} value={value} onValueChange={setValue} className="contents">
      <TabsList aria-label={label}>
        {channels.map((channel) => (
          <TabsTrigger key={channel.id} value={channel.id} data-channel={channel.id} data-platform={channel.platform} onClick={() => setValue(channel.id)}>
            {channel.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {channels.map((channel) => (
        <TabsContent key={channel.id} value={channel.id} forceMount data-channel={channel.id}>
          <p className="install-name">{channel.label}</p>
          <p className="install-line" translate="no">
            <span className="install-prompt" aria-hidden="true">
              {channel.prompt}
            </span>
            <code data-command={channel.command}>
              {commandPieces(channel.command).map((word, index) => (
                <React.Fragment key={index}>
                  {index > 0 && " "}
                  <span>
                    {word.map((piece, at) => (
                      <React.Fragment key={at}>
                        {at > 0 && <wbr />}
                        <span className="install-piece">{piece}</span>
                      </React.Fragment>
                    ))}
                  </span>
                </React.Fragment>
              ))}
            </code>
          </p>
        </TabsContent>
      ))}
    </Tabs>
  );
}
