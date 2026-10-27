# Safety red team report

This is the record of trying to break the guarantees in docs/SAFETY.md through every interface. Each
attempt is a test in tests/redteam/. A test that an attack is blocked passes. An attack that got
through is a strict xfail carrying its finding id, and the finding is written up below with a
proposed fix. Every attempt used mocks and simulators. No code under openhal/ was changed.

The suite is 100 tests. 94 pass and 6 are strict xfails, for four findings (RT-01 has two proofs).

All four findings are fixed on main, and their proofs now run as ordinary tests that pass. RT-01 caps unit names at 40 characters and quantity text at 80 before pint parses them, on every path including routines. RT-02 wraps every string the driver writer detected as data, except the fields OpenHAL sets itself. RT-03 answers frames nested deeper than 32 levels, and any JSON the parser can't finish, with PARSE_ERROR. RT-04 scrubs tokens from the client and principal fields of the message log.

## How to read it

- One module per attack family in tests/redteam/.
- A passing test means the kernel refused the attempt and no mock transport saw a byte.
- A strict xfail (`pytest.mark.xfail(strict=True)`) is a real finding. The test fails against the current
  kernel on purpose, so the test turns green the moment the kernel is fixed.

## Findings, worst first

### RT-01 (high). The unit parser has no time budget or length cap, so one value freezes the hub

The safety kernel is single threaded. Check 6 converts a value to the channel unit with pint. pint's
unit parser is roughly quadratic in the length of a unit name, and nothing bounds it, unlike string
patterns, which run on the regex engine with a 50 ms budget (docs/SAFETY.md, "String patterns", and
threat T21). A value whose unit is a long run of letters makes `openhal.spec.units.parse_unit` run
for seconds while the whole event loop is blocked. During that time no stop, watchdog, heartbeat or
other command runs. This is the same class as review finding F07, through a path that has no budget.

- Over the wire the unit field is capped at 40 characters (ADR 0016), so the direct write path is
  not reachable. But routines carry quantity strings and are evaluated with `wire=False`, so an
  agent reaches the parser through a drafted routine's dry run, which any control-scope agent can
  call (`draft_routine` then `run_routine_dry`). One step with a 5000 character unit stalls the hub
  for about 1.4 s. The kernel's own `evaluate` is affected the same way.
- Proofs. tests/redteam/test_units.py::test_rt01_long_unit_name_does_not_stall_the_kernel (kernel
  API) and tests/redteam/test_routines.py::test_rt01_a_routine_dry_run_with_a_long_unit_stalls
  (agent reachable). Each uses a distinct unit so pint's cache can't hide the cost.
- Expected. The value is refused quickly (it is not a real unit), the way an over-budget pattern is.
- Actual. The decision is `bad_unit`, but only after a multi-second synchronous parse.
- Proposed fix. Cap the unit text before parsing (the wire already uses 40 characters, so apply the
  same cap in `parse_unit`, or in `normalize`, for every path including routines), and reject a unit
  longer than that with `bad_unit` without calling pint. A time budget around the parse is a weaker
  second line. Also cap the string length of a quantity value the kernel will parse.

### RT-02 (medium). The driver writer returns device and manual text outside a data block

docs/SAFETY.md says text from devices, manuals and sketches reaches agents only inside
`<device-data>` blocks. The writer session view wraps `sources`, but `detected` is returned raw.
`detected.manual_commands[].description`, `detected.identity` and `detected.sketch` carry text
straight from the manual, the device's identify output or the sketch, with no wrapper and with any
`</device-data>` left intact. An agent reading the session (`get_writer_session`, REST
`/v1/writer/sessions/{id}`) sees that text as plain structured facts.

- Proof. tests/redteam/test_injection.py::test_rt02_writer_detected_facts_are_wrapped_as_data.
- Expected. Every device or source string reaches the agent inside a data block, as readings and
  notes already do.
- Actual. `detected` facts are raw.
- Proposed fix. In `WriterEngine.view`, wrap the string fields of `detected` (manual command
  descriptions, identity values, sketch findings' text) with `views.data_block`, the same helper the
  sources already use, or build `detected` from already-wrapped values.

### RT-03 (medium). A deeply nested JSON frame crashes the connection instead of a PARSE_ERROR

ADR 0015 says invalid JSON is answered with PARSE_ERROR. `Dispatcher.parse` catches only
`(ValueError, UnicodeDecodeError)`. A deeply nested but syntactically valid JSON frame makes
`json.loads` raise `RecursionError`, which escapes `parse`, escapes `serve_rpc` (it catches only
`WebSocketDisconnect` and `RuntimeError`), and drops the connection. Nothing executes, so it is fail
safe, but it is a spec deviation and a per-connection denial of service from one frame.

- Proof. tests/redteam/test_protocol_edges.py::test_rt03_deeply_nested_json_frame_is_a_parse_error.
- Expected. The frame is answered with PARSE_ERROR and the connection stays up.
- Actual. `parse` raises RecursionError.
- Proposed fix. Catch `RecursionError` (or `Exception`) in `Dispatcher.parse` alongside the JSON
  errors and answer PARSE_ERROR. Optionally reject frames above a size or nesting depth before
  decoding.

### RT-04 (low). A token placed in clientInfo.name is stored in the message log unredacted

The message log promises tokens are never kept and any OpenHAL-shaped text is replaced wherever it
appears (openhal/protocol/log.py). `redact` scrubs the message body, but `MessageLog.record` stores
the `client` field verbatim. `clientInfo.name` becomes `session.client`, so a client that puts its
token in its name leaks it into the `client` column of every logged entry, which the Inspector shows
to a person at `/v1/rpc/log`.

- Proof. tests/redteam/test_protocol_edges.py::test_rt04_a_token_in_the_client_name_does_not_leak.
- Expected. No token text appears anywhere in the log, including the `client` field.
- Actual. The token appears in `client`.
- Proposed fix. Run the `client` and `principal` fields through the same `_TOKEN_TEXT` scrub in
  `MessageLog.record`, or scrub `session.client` when it is set.

## What held

Everything else the brief asked about was tried and blocked. The tests for these all pass.

- **Every interface refused the four forbidden moves** (a write above a limit, an approve, an unlock
  and a loosen) through REST, the JSON-RPC protocol on WebSocket and stdio, the MCP tools, the CLI
  and the Python client. Agents cannot approve, unlock, mint a session cookie, or run the human-only
  Inspector and writer routes. The MCP server refuses a human token. tests/redteam/test_interfaces.py.
- **Units.** Cross-unit tricks (degF against a degC max, mA against an A max, kelvin, kA, percent
  against a fraction channel) are all converted to the channel unit before the limit compares, so
  none widens a limit. Bare numbers, wrong types, NaN, infinity, huge exponents, unicode digits,
  lookalike unit letters and malformed unit expressions are refused or fail closed.
  tests/redteam/test_units.py.
- **The structured value format (ADR 0016).** A number sent as one string, a unit on a bool or enum
  channel, a Quantity holding a bool or a non-finite number, and an incompatible unit are all
  refused with `bad_unit` or rejected by the schema, over REST, the protocol and MCP. The action
  `max_runs` limit blocks the call past its count and survives a hub restart, because the window is
  seeded from the audit log. tests/redteam/test_wire_values.py.
- **Rate limits.** A single jump, a rapid burst, many small steps, alternating values and two
  clients racing one channel all stay within `max_change_per_s` measured from the newest known value.
  tests/redteam/test_rate.py.
- **Concurrency.** A write that lands during a stop is undone by the reapplied safe state, an unlock
  is refused while a stop is still applying, two humans approving one request run it once, and an
  expired or cancelled request cannot be approved. tests/redteam/test_concurrency.py.
- **Malicious drivers and the single path (ADR 0004).** A forged, reused, expired, revoked,
  cross-device or cross-value grant is refused before the transport. A driver cannot name another
  device through its verifier, cannot override the sealed methods, and cannot reattach to steal
  grants. A deliberately malicious in-process driver talking to its own transport stays the
  documented residual risk (threat T17). tests/redteam/test_drivers.py.
- **Routines.** A routine cannot drive a high hazard device without a signed approval bound to its
  content hash, editing a routine invalidates the approval, an agent cannot enable a routine on the
  default hub, a routine is blocked while the hub is stopped, a routine cannot create or enable
  routines, and a loop is throttled by the run interval. tests/redteam/test_routines.py.
- **Loosening.** Session limits only narrow, they are per principal (one agent's tightening never
  loosens another, who is still held to the file limit), and no interface widens a confirmed file
  limit. tests/redteam/test_loosen.py.
- **Confirmation spoofing.** A forged session cookie is rejected, a cookie session needs the
  anti-CSRF header, one principal cannot see or learn another's request ids (an unknown id and
  another principal's id give the same answer), an agent cannot approve any request, and a phrase
  piped to stdin does not unlock. tests/redteam/test_confirm_spoof.py.
- **Protocol edges.** Methods before initialize do nothing, a batch is refused, a method above the
  declared conformance level is METHOD_NOT_FOUND, duplicate ids are each answered, and a huge or
  deeply nested value is refused. A token sent in `initialize` params is redacted from the log body.
  tests/redteam/test_protocol_edges.py.
- **Fail safe.** A malformed unit that raises inside a check, and an injected exception inside a
  check, both block the command with `internal_error` and are logged. A driver that raises during a
  write yields a failed result, never done, and does not record the attempted value. An in-flight
  write holds the channel unknown so interlocks fail safe. tests/redteam/test_failsafe.py.

## Notes for the orchestrator

- The findings are kernel and hub bugs. This workstream owns only tests/redteam/ and this report, so
  the fixes above are proposals, not changes.
- RT-01 is the one with real safety weight, because a stalled kernel is a stalled stop path. The
  40 character unit cap already added for the wire is the right size to apply everywhere.
