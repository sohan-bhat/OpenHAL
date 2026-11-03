import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { appliedRate, effectiveHazard, tier, type DeviceFile, type Kernel } from "@/lib/kernel";
import { formatG } from "@/lib/kernel/pyformat";
import { displayUnit } from "@/lib/playground/rpc";
import { show, tierWord, withUnit } from "@/lib/playground/session";

interface Props {
  file: DeviceFile | null;
  kernel: Kernel | null;
  id: string;
  missing: string[];
  story: boolean;
  companions: Array<{ id: string; path: string }>;
  drafts: Record<string, string>;
  onDraft: (key: string, draft: string) => void;
  onReading: (device: string, channel: string) => void;
}

function Status({ missing }: { missing: string[] }) {
  return missing.length ? <span className="status unverified">unconfirmed</span> : <span className="status ok">confirmed</span>;
}

/**
 * The simulated device: its id, driver and, outside the story, its hazard and limits, then its
 * channels as shadcn/ui Tables with each value as the kernel last read it. A person can set any
 * reading by hand, such as the laser's door, to see an interlock change the hub's response.
 */
export function SimulatedDevice({ file, kernel, id, missing, story, companions, drafts, onDraft, onReading }: Props) {
  if (!file || !kernel) return <p className="muted">Fix the device file to load its simulated device.</p>;
  const valueOf = (channel: string) => show(kernel.latestValue(id, channel) ?? null);
  const high = effectiveHazard(file) === "high";
  return (
    <>
      <dl className="facts">
        <div>
          <dt className="legend">Id</dt>
          <dd className="mono">{id}</dd>
        </div>
        <div>
          <dt className="legend">Driver</dt>
          <dd className="mono">{file.connect.driver}</dd>
        </div>
        {story ? null : (
          <>
            <div>
              <dt className="legend">Hazard</dt>
              <dd className="mono">{effectiveHazard(file)}</dd>
            </div>
            <div>
              <dt className="legend">Limits</dt>
              <dd>
                <Status missing={missing} />
              </dd>
            </div>
          </>
        )}
      </dl>
      {Object.keys(file.write).length ? (
        <div className="table-wrap stack">
          <Table className="pg-table">
            <TableCaption className="legend">Channels the device can change</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Channel</TableHead>
                <TableHead scope="col">Value</TableHead>
                <TableHead scope="col">Min</TableHead>
                <TableHead scope="col">Max</TableHead>
                <TableHead scope="col">Rate per s</TableHead>
                <TableHead scope="col">Confirm</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.entries(file.write).map(([name, spec]) => (
                <TableRow key={name}>
                  <TableCell data-label="Channel" className="mono">
                    {name}
                  </TableCell>
                  <TableCell data-label="Value" className="mono">
                    {withUnit(valueOf(name), displayUnit(spec.unit))}
                  </TableCell>
                  <TableCell data-label="Min" className="mono">
                    {spec.min === null ? (spec.type === "enum" ? spec.values.join(", ") : spec.type) : formatG(spec.min)}
                  </TableCell>
                  <TableCell data-label="Max" className="mono">
                    {spec.max === null ? "" : formatG(spec.max)}
                  </TableCell>
                  <TableCell data-label="Rate per s" className="mono">
                    {appliedRate(file, name) === null ? "" : formatG(appliedRate(file, name) as number)}
                  </TableCell>
                  <TableCell data-label="Confirm">{tierWord(tier(file, `write:${name}`, spec.confirm), high)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {Object.keys(file.read).length ? (
        <div className="table-wrap stack">
          <Table className="pg-table">
            <TableCaption className="legend">Read channels</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Channel</TableHead>
                <TableHead scope="col">Value</TableHead>
                <TableHead scope="col">Simulate a reading</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.entries(file.read).map(([name, spec]) => {
                const key = `${id}.${name}`;
                return (
                  <TableRow key={name}>
                    <TableCell data-label="Channel" className="mono">
                      {name}
                    </TableCell>
                    <TableCell data-label="Value" className="mono">
                      {withUnit(spec.type === "image" ? "frames" : valueOf(name), displayUnit(spec.unit))}
                    </TableCell>
                    <TableCell data-label="Simulate">
                      {spec.type === "image" ? null : (
                        <form
                          className="sim"
                          onSubmit={(event) => {
                            event.preventDefault();
                            onReading(id, name);
                          }}
                        >
                          <Label className="visually-hidden" htmlFor={`pg-read-${name}`}>
                            Simulated reading for {name}
                          </Label>
                          <Input id={`pg-read-${name}`} className="mono pg-field" value={drafts[key] ?? ""} onChange={(event) => onDraft(key, event.target.value)} />
                          <Button type="submit" variant="outline" size="sm" className="pg-small">
                            Set
                          </Button>
                        </form>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      ) : null}
      {companions.length ? (
        <p className="muted note">
          This file's interlocks name{" "}
          {companions.map((other, index) => (
            <span key={other.id}>
              {index ? ", " : ""}
              <code>{other.id}</code>
            </span>
          ))}
          , so the Playground loads those devices too.
        </p>
      ) : null}
    </>
  );
}
