# Lifecycle

A connection between a Client and a Hub has three phases. Initialization, operation and shutdown.

## Initialization

1. The Client MUST send `hal/initialize` as its first request.
2. The Hub MUST answer with the negotiated protocol version, its own name and version, its Conformance Level, the Principal its token maps to, and the notifications it sends.
3. The Client MUST then send the notification `hal/initialized`.
4. The Hub MUST NOT send any notification before it receives `hal/initialized`.
5. The Hub MUST answer any other request received before `hal/initialize` with `NOT_INITIALIZED` (-32001).
6. If the token is missing or unknown, the Hub MUST answer `hal/initialize` with `UNAUTHORIZED` (-32002).

The token is the bearer token from the `Authorization` header of the transport, or the `token` param of `hal/initialize` ([Transports](transports.md#authentication)).

### Example

```json
→ {"jsonrpc": "2.0", "id": 1, "method": "hal/initialize",
   "params": {"protocolVersion": "2026-10-24", "clientInfo": {"name": "bench-agent", "version": "1.4.0"}}}
← {"jsonrpc": "2.0", "id": 1, "result": {
     "protocolVersion": "2026-10-24",
     "hubInfo": {"name": "openhal", "version": "0.1.0"},
     "conformance": "full",
     "principal": {"kind": "agent", "name": "bench-agent", "scope": "control_low"},
     "capabilities": {"notifications": ["hal/value", "hal/blocked", "hal/stopped", "hal/deviceAdded",
                                        "hal/deviceRemoved", "hal/confirmationRequested"]}}}
→ {"jsonrpc": "2.0", "method": "hal/initialized"}
```

In examples, `→` is a message from Client to Hub and `←` is a message from Hub to Client. The arrows are not part of the message.

## Version negotiation

Protocol versions are dates in the form `YYYY-MM-DD`. A later date is a newer version.

1. The Client MUST send the newest version it supports in `protocolVersion`.
2. If the Hub supports that version, it MUST answer with the same version.
3. Otherwise the Hub MUST answer with the newest version it supports.
4. If the Client cannot use the version in the answer, it MUST disconnect. It SHOULD tell its user which versions each side supports.

The reference Hub supports one version, `2026-10-24`.

## Operation

After `hal/initialized`, the Client MAY send any method at or below the Hub's Conformance Level ([Messages](messages.md)). The Hub sends notifications as events happen. Clients receive every notification the Hub lists in `capabilities.notifications`. A later version may add filters.

A method above the Hub's Conformance Level gets `METHOD_NOT_FOUND` (-32601).

## Shutdown

1. The Client SHOULD send the notification `hal/shutdown` and then close the transport.
2. The Hub MUST NOT change any Device because a Client disconnected. Devices belong to the Hub, not to a connection.
3. Confirmation Requests the Client created stay in the queue after it disconnects. They are approved, rejected or expire as usual.

Either side may close the transport at any time. Both sides MUST treat a closed transport as the end of the connection.

```json
→ {"jsonrpc": "2.0", "method": "hal/shutdown"}
```
