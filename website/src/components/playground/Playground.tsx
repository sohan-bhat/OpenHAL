import { Suspense, lazy, useCallback, useEffect, useReducer, useRef, useState, type FormEvent } from "react";
import { AnimatePresence } from "motion/react";
import * as m from "motion/react-m";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { MotionRoot, useTimings } from "@/components/ui/motion";
import { deviceId, effectiveHazard, unconfirmed } from "@/lib/kernel";
import {
  CLIENTS,
  LOG_SIZE,
  clientOf,
  decide,
  exampleFiles,
  hintFor,
  prepare,
  sendQuick,
  sendRequest,
  setReading,
  show,
  stopAll,
  targetsOf,
  tickAll,
  unlock,
  watchedChannels,
  withUnit,
  type Example,
  type Library,
  type Logged,
  type Quick,
  type Session,
  type Suggestion,
} from "@/lib/playground/session";
import type { Exchange } from "@/lib/playground/types";
import { InfoMark } from "./InfoMark";
import { Chevron, Held, Picker, StopArea } from "./parts";
import { SimulatedDevice } from "./SimulatedDevice";
import { TraceList } from "./TraceList";
import "./playground.css";
import "./controls.css";

const loadEditor = () => import("./DeviceEditor");
const DeviceEditor = lazy(loadEditor);

/** Starts loading the editor while a person points at or focuses the builder, so it opens ready. */
function warmEditor(): void {
  void loadEditor().catch(() => undefined);
}

const EXAMPLE_KEY = "example";

interface Props {
  examples: Example[];
  initial: string;
  suggestion?: Suggestion | null;
  quick?: Quick[];
  watch?: string[];
}

/**
 * The Playground, a React island on shadcn/ui and Radix. A TypeScript port of the safety kernel
 * runs in the browser against simulated devices, so a request from the story, or one a person
 * builds from a device file, gets the hub's response without any hardware.
 */
export default function Playground({ examples, initial, suggestion = null, quick = [], watch = [] }: Props) {
  const library = useRef<Library | null>(null);
  const libraryOf = useCallback(() => (library.current ??= exampleFiles(examples)), [examples]);
  const [start] = useState(() => examples.find((item) => item.name === initial) ?? examples[0]);
  const [exampleName, setExampleName] = useState(start.name);
  const [text, setText] = useState(start.text);
  const [session, setSession] = useState<Session>(() => prepare(start.text, { targetDevice: "", target: "", requestText: "" }, libraryOf, suggestion));
  const [clientKey, setClientKey] = useState(CLIENTS[0].key);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [unlockText, setUnlockText] = useState("");
  const [unlockError, setUnlockError] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [, bump] = useReducer((count: number) => count + 1, 0);
  const built = useRef(start.text);
  const counter = useRef(0);
  const live = useRef(session.kernel);
  live.current = session.kernel;

  const { checked, kernel, companions, targetDevice, target, requestText } = session;
  const file = checked.file;
  const id = file ? deviceId(file) : "";
  const missing = file ? unconfirmed(file) : [];
  const ready = quick.filter((item) => kernel?.devices.has(item.command.device));
  const story = ready.length > 0;
  const pending = kernel?.pending() ?? [];
  const [buildOpen, setBuildOpen] = useState(!story);
  const { open: enter, close } = useTimings();

  const rebuild = useCallback(
    (current: string) => {
      if (current === built.current) return;
      built.current = current;
      setSession((previous) => prepare(current, previous, libraryOf, suggestion));
      setDrafts({});
      bump();
    },
    [libraryOf, suggestion],
  );

  useEffect(() => {
    const timer = setTimeout(() => rebuild(text), 250);
    return () => clearTimeout(timer);
  }, [text, rebuild]);

  useEffect(() => {
    const chosen = examples.find((item) => item.name === new URL(window.location.href).searchParams.get(EXAMPLE_KEY));
    if (chosen && chosen.name !== start.name) {
      setExampleName(chosen.name);
      setText(chosen.text);
      rebuild(chosen.text);
    }
    const clock = setInterval(() => {
      if (!live.current) return;
      tickAll(live.current);
      bump();
    }, 1000);
    return () => clearInterval(clock);
  }, []);

  useEffect(() => setBuildOpen(!story), [story]);

  useEffect(() => {
    if (buildOpen) warmEditor();
  }, [buildOpen]);

  const log = (entry: Logged | null) => {
    if (!entry) return;
    counter.current += 1;
    const key = counter.current;
    setExchanges((list) => [{ key, ...entry }, ...list].slice(0, LOG_SIZE));
    bump();
  };

  const chooseExample = (name: string) => {
    const item = examples.find((example) => example.name === name);
    if (!item) return;
    setExampleName(name);
    setText(item.text);
    setExchanges([]);
    const url = new URL(window.location.href);
    url.searchParams.set(EXAMPLE_KEY, name);
    history.replaceState(null, "", url);
  };

  const update = (change: Partial<Session>) => setSession((previous) => ({ ...previous, ...change }));
  const send = (dry = false) => kernel && log(sendRequest(kernel, clientOf(clientKey), targetDevice, target, requestText, dry));
  const onDecide = (requestId: string, approve: boolean) => kernel && log(decide(kernel, requestId, approve));
  const onStop = () => {
    if (!kernel) return;
    log(stopAll(kernel));
    setUnlockText("");
    setUnlockError("");
  };
  const onUnlock = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!kernel) return;
    try {
      log(unlock(kernel, unlockText));
    } catch (error) {
      setUnlockError((error as Error).message);
    }
  };
  const onReading = (device: string, channel: string) => {
    if (kernel && setReading(kernel, device, channel, drafts[`${device}.${channel}`] ?? "")) bump();
  };
  const onDraft = (key: string, draft: string) => setDrafts((all) => ({ ...all, [key]: draft }));
  const stopProps = { stopped: kernel?.stopped ?? false, ready: Boolean(kernel), unlockText, unlockError, onUnlockText: setUnlockText, onStop, onUnlock };

  return (
    <MotionRoot>
      <div className="pg frame">
        {story ? (
          <section className="try" aria-labelledby="pg-try-title">
            <h2 id="pg-try-title">
              Try a request from the story
              <InfoMark topic="this demo" text="This demo runs in your browser, so a TypeScript port of the safety kernel checks each request here and sends nothing to hardware." />
            </h2>
            <div className="try-grid">
              <ul className="quick">
                {ready.map((item) => (
                  <li key={item.label}>
                    <Button type="button" variant="outline" className="pg-quick" onClick={() => kernel && log(sendQuick(kernel, item))}>
                      {item.label}
                    </Button>
                  </li>
                ))}
              </ul>
              <aside className="printer" aria-labelledby="pg-printer-title">
                <h3 id="pg-printer-title" className="small-head">
                  {file ? file.device.name : "Device"}
                </h3>
                <dl className="readout">
                  {watchedChannels(kernel, ready, watch).map((item) => (
                    <div key={item.name}>
                      <dt className="mono">{item.name}</dt>
                      <dd className="mono">{withUnit(show(kernel?.latestValue(item.device, item.name) ?? null), item.unit)}</dd>
                    </div>
                  ))}
                  {file ? (
                    <>
                      <div>
                        <dt>
                          Hazard
                          <InfoMark
                            topic="hazard"
                            text="The hazard class states how much harm the device can do, so a medium hazard device needs a control_medium token and the device's riskiest actions need a person's approval."
                            href="/docs/safety/"
                          />
                        </dt>
                        <dd className="mono">{effectiveHazard(file)}</dd>
                      </div>
                      <div>
                        <dt>
                          Limits
                          <InfoMark topic="confirmed limits" text="A person read this device file and confirmed the file's limits. The kernel checks every command against the confirmed limits." href="/docs/concepts/" />
                        </dt>
                        <dd>{missing.length ? <span className="status unverified">unconfirmed</span> : <span className="status ok">confirmed</span>}</dd>
                      </div>
                    </>
                  ) : null}
                </dl>
                {pending.length ? (
                  <Held
                    pending={pending}
                    onDecide={onDecide}
                    heading={
                      <>
                        Held for a person
                        <InfoMark topic="pending" text="A request such as a cancel can't be undone, so the hub returned pending and holds the request here until a person approves or rejects the request." />
                      </>
                    }
                  />
                ) : null}
                <StopArea inputId="pg-unlock" {...stopProps} />
              </aside>
              <div className="answers">
                <h3 className="small-head">The hub's responses</h3>
                <TraceList exchanges={exchanges} />
              </div>
            </div>
          </section>
        ) : null}

        <Collapsible open={buildOpen} onOpenChange={setBuildOpen} className="build">
          <CollapsibleTrigger asChild>
            <Button type="button" variant="ghost" className="pg-build-trigger" onPointerEnter={warmEditor} onFocus={warmEditor}>
              <Chevron open={buildOpen} />
              Build your own request
            </Button>
          </CollapsibleTrigger>
          <AnimatePresence initial={false}>
            {buildOpen ? (
              <CollapsibleContent forceMount asChild>
                <m.div
                  className="build-body"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1, transition: enter }}
                  exit={{ height: 0, opacity: 0, transition: close }}
                >
                  <div className="playground">
                    <section className="panel editor" aria-labelledby="pg-editor-title">
                      <div className="panel-head">
                        <h2 id="pg-editor-title">Device file</h2>
                        <div className="example">
                          <Label htmlFor="pg-example" className="legend">
                            Start from
                          </Label>
                          <Picker id="pg-example" value={exampleName} onChange={chooseExample} items={examples.map((item) => ({ value: item.name, label: item.path }))} />
                        </div>
                      </div>
                      <Suspense
                        fallback={
                          <pre className="pg-editor-wait" aria-hidden="true">
                            {text}
                          </pre>
                        }
                      >
                        <DeviceEditor id="pg-text" label="Device file YAML" describedBy="pg-problems" value={text} onChange={setText} />
                      </Suspense>
                      <div id="pg-problems" className="problems" aria-live="polite">
                        {checked.problems.length ? (
                          <>
                            <p className="status blocked">invalid</p>
                            <ul>
                              {checked.problems.map((problem, index) => (
                                <li key={index}>
                                  <code>{problem.where}</code>
                                  {problem.line ? <span className="muted"> line {problem.line}</span> : null}
                                  <span>{problem.message}</span>
                                  <span className="legend">{problem.source === "schema" ? "JSON Schema" : problem.source === "yaml" ? "YAML" : "Specification"}</span>
                                </li>
                              ))}
                            </ul>
                          </>
                        ) : missing.length ? (
                          <>
                            <p className="status unverified">valid, limits unconfirmed</p>
                            <p className="muted">Changes are blocked with UNVERIFIED_LIMITS until a person confirms {missing.join(", ")}.</p>
                          </>
                        ) : (
                          <p className="status ok">valid</p>
                        )}
                      </div>
                    </section>

                    <div className="side">
                      <section className="panel" aria-labelledby="pg-request-title">
                        <div className="panel-head">
                          <h2 id="pg-request-title">Send a request</h2>
                        </div>
                        {kernel ? (
                          <form
                            className="request"
                            onSubmit={(event) => {
                              event.preventDefault();
                              send();
                            }}
                          >
                            <div className="fields">
                              <div className="field">
                                <span className="legend as-label">
                                  <Label htmlFor="pg-as">As</Label>
                                  <InfoMark
                                    topic="tokens"
                                    text="Each client signs in with a token, and an agent's token sets which hazard classes the agent may control. Approving a request or lifting a stop takes a person's token."
                                    href="/docs/concepts/"
                                  />
                                </span>
                                <Picker id="pg-as" value={clientKey} onChange={setClientKey} items={CLIENTS.map((item) => ({ value: item.key, label: item.label }))} />
                              </div>
                              <div className="field">
                                <Label htmlFor="pg-device" className="legend">
                                  Device
                                </Label>
                                <Picker id="pg-device" value={targetDevice} onChange={(value) => update({ targetDevice: value })} items={[...kernel.devices.keys()].map((device) => ({ value: device, label: device }))} />
                              </div>
                              <div className="field">
                                <Label htmlFor="pg-target" className="legend">
                                  Channel or action
                                </Label>
                                <Picker
                                  id="pg-target"
                                  value={target}
                                  onChange={(value) => update({ target: value })}
                                  items={targetsOf(kernel, targetDevice).map((item) => ({ value: item.name, label: item.kind === "write" ? item.name : `${item.name} (action)` }))}
                                />
                              </div>
                            </div>
                            <div className="field">
                              <Label htmlFor="pg-value" className="legend">
                                Value
                              </Label>
                              <Input
                                id="pg-value"
                                className="mono pg-field"
                                value={requestText}
                                onChange={(event) => update({ requestText: event.target.value })}
                                autoComplete="off"
                                spellCheck={false}
                                aria-describedby="pg-hint"
                              />
                            </div>
                            <p id="pg-hint" className="muted">
                              {hintFor(kernel, targetDevice, target)}
                            </p>
                            <div className="buttons">
                              <Button type="submit" disabled={!target}>
                                Send {kernel.devices.get(targetDevice)?.file.actions[target] ? "hal/action" : "hal/write"}
                              </Button>
                              <Button type="button" variant="outline" disabled={!target} onClick={() => send(true)}>
                                Dry run
                              </Button>
                            </div>
                          </form>
                        ) : null}
                        {story ? null : (
                          <>
                            <StopArea inputId="pg-unlock-build" {...stopProps} />
                            {pending.length ? <Held pending={pending} onDecide={onDecide} heading="Waiting for a person" /> : null}
                          </>
                        )}
                      </section>

                      <section className="panel" aria-labelledby="pg-device-title">
                        <div className="panel-head">
                          <h2 id="pg-device-title">Simulated device</h2>
                        </div>
                        <SimulatedDevice
                          file={file}
                          kernel={kernel}
                          id={id}
                          missing={missing}
                          story={story}
                          companions={companions}
                          drafts={drafts}
                          onDraft={onDraft}
                          onReading={onReading}
                        />
                      </section>

                      {story ? null : (
                        <section className="panel" aria-labelledby="pg-log-title">
                          <div className="panel-head">
                            <h2 id="pg-log-title">Message log</h2>
                          </div>
                          <TraceList exchanges={exchanges} />
                        </section>
                      )}
                    </div>
                  </div>
                </m.div>
              </CollapsibleContent>
            ) : null}
          </AnimatePresence>
        </Collapsible>
      </div>
    </MotionRoot>
  );
}
