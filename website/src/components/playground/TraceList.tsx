import { Fragment, memo } from "react";
import type { Exchange } from "@/lib/playground/types";
import { arrowSvg, directionWord, payloadHtml, reasonLines, type TraceEntry } from "@/lib/trace";

function Line({ entry }: { entry: TraceEntry }) {
  if (entry.kind === "note") return null;
  return (
    <li className="enter">
      <span className="pg-arrow" dangerouslySetInnerHTML={{ __html: arrowSvg(entry.kind === "request" ? "out" : "in", entry.kind === "notification") }} />
      <span className="visually-hidden">{directionWord(entry)}</span>
      <div className="line">
        {entry.kind === "error" ? (
          <>
            <span className="head error-head">
              <span className="outcome-error">
                error {entry.code} {entry.name}
              </span>
            </span>
            {reasonLines(entry.reason).map((part, index) => (
              <Fragment key={index}>
                {index > 0 ? " " : null}
                <span className="reason">{part}</span>
              </Fragment>
            ))}
          </>
        ) : (
          <span className="head">
            {entry.kind === "result" ? <span className="outcome-result">result</span> : <span className="method">{entry.method}</span>}
            <span className="payload" dangerouslySetInnerHTML={{ __html: payloadHtml(entry.kind === "result" ? entry.result : entry.params) }} />
          </span>
        )}
      </div>
    </li>
  );
}

/**
 * The hub's responses as the site's message trace (docs/DESIGN.md, The message trace), newest
 * first, with each person's exchange on a solid rule and each agent's on a dashed rule. The arrows
 * and the payload's highlighting come from the same renderer as every other trace on the site.
 */
export const TraceList = memo(function TraceList({ exchanges }: { exchanges: Exchange[] }) {
  return (
    <div className="trace log" role="region" tabIndex={0} aria-label="Message log, newest first">
      {exchanges.length === 0 ? (
        <p className="empty">No messages are logged yet, so send a request to see the hub's response.</p>
      ) : (
        <ol className="exchanges">
          {exchanges.map((exchange) => (
            <li key={exchange.key} className={`exchange ${exchange.who}`}>
              <p className="who">
                {exchange.who === "person" ? "Person" : "Agent"} · {exchange.client}
              </p>
              <ol>
                {exchange.entries.map((entry, index) => (
                  <Line key={index} entry={entry} />
                ))}
              </ol>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
});
