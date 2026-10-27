# http driver

The http driver talks to devices that expose a local HTTP API. Every request it sends comes from the device file. Read channels name a request and where the value sits in the response. Write channels and actions name a request and a body or query template. With an OpenAPI 3 document, `describe()` proposes the channels for you.

## What it supports

- Read channels of type number, bool, string, enum and image, from JSON bodies (with a JSON path) or plain text bodies.
- Write channels of type number, bool, string and enum, sent as a JSON body, a query string or a path segment, with GET, POST, PUT, PATCH or DELETE.
- Read-back for write channels through a `state` request. Without one, reading a write channel returns the last value the driver sent, or no value before the first write.
- Actions whose arguments fill the same templates.
- A bearer token or API key from an environment variable.
- `describe()` from an OpenAPI 3 JSON document.

## Setup

```sh
uv tool install --compile-bytecode "openhal-hub[http] @ git+https://github.com/sohan-bhat/OpenHAL"
```

httpx is also part of the hub extra, so a hub install already has it.

## Parameters

| Parameter | Default | Meaning |
|---|---|---|
| `base_url` | required | `http://` or `https://` URL of the device. The shorthand `http: "http://192.168.1.50"` sets it |
| `timeout` | `5 s` | Hard deadline for each request, enforced by the driver |
| `headers` | none | Extra request headers. Names that look like credentials are rejected |
| `token_env` | none | Name of an environment variable holding a token |
| `auth_header` | `Authorization` | Header that carries the token |
| `auth_scheme` | `Bearer` | Prefix before the token. Use `""` for a bare API key header |
| `verify_tls` | `true` | Check HTTPS certificates |
| `health` | `/` | Path fetched with GET for connect and the heartbeat. Any HTTP answer counts as alive |
| `identify` | none | Path fetched with GET by `identify()`. Scalar fields of the JSON reply become identity fields |
| `openapi` | none | Path of an OpenAPI 3 JSON document for `describe()` |
| `max_response_bytes` | `1048576` | Larger answers are refused |

## Channel maps

Read channels.

```yaml
read:
  power: { unit: W, map: { path: /api/status, json: $.power.w } }
  mode: { type: enum, values: [auto, eco], map: { path: /api/mode } }   # text body
  snapshot: { type: image, map: { path: /snapshot.jpg } }
```

| Key | Default | Meaning |
|---|---|---|
| `path` | required | Request path, starting with `/` |
| `method` | `GET` | `GET` or `POST` |
| `query` | none | Query parameters |
| `body` | none | JSON body, for POST reads such as JSON-RPC |
| `json` | none | JSON path to the value. A subset of RFC 9535 with keys and list indexes, such as `$.relays[0].on` |
| `format` | `json` with a path, else `text` | How to read the body |
| `on`, `off` | common words | Words that mean true and false for bool channels |
| `scale`, `offset` | `1`, `0` | channel value = device value × scale + offset |

Write channels.

```yaml
write:
  relay:
    type: bool
    map: { path: /api/relay, body: { on: "{value}" }, state: { path: /api/status, json: relay.on } }
  level:
    unit: percent
    min: 0
    max: 100
    map: { path: /api/dimmer, method: PUT, body: { level: "{value}" }, scale: 0.392157 }
```

| Key | Default | Meaning |
|---|---|---|
| `path` | required | Request path. `{value}` in the path is URL-encoded |
| `method` | `POST` | Any of GET, POST, PUT, PATCH, DELETE |
| `query`, `body` | none | Templates. A string that is exactly `"{value}"` keeps the value's JSON type |
| `on`, `off` | the boolean itself | What to send for true and false |
| `scale`, `offset` | `1`, `0` | Device value = (channel value - offset) / scale. Whole results are sent as integers |
| `state` | none | A read map used to read the channel back |

Actions use `path`, `method`, `query` and `body` the same way, with `{arg}` for each argument, and an optional `json` path that picks the result out of the reply.

## Example

`openhal/drivers/http/examples/smart-plug.hal.yaml` describes a Shelly Plus Plug S through its Gen2 RPC API. The plug's output relay is switched with `GET /rpc/Switch.Set?id=0&on=true`, which is how that API works.

## Describe from OpenAPI

With `openapi: /openapi.json`, `describe()` fetches the document and proposes

- read channels for the scalar properties of each GET operation's JSON reply, one nesting level deep,
- write channels for the scalar properties of each PUT, POST or PATCH JSON body, only when numbers carry `minimum` and `maximum`,
- actions for POST operations without a body.

Units come from an `x-unit` property where the document has one, otherwise `dimensionless`, and the notes list the channels that need a real unit. Every write channel and action is marked `suggested: true`, so the file stays read-only until a human confirms the limits. Paths with parameters, remote `$ref` pointers and YAML documents are skipped.

## Errors

- No answer within `timeout` raises `TimeoutError`.
- Connection failures, HTTP status 400 and above, bodies that are not JSON when JSON is expected, missing JSON fields, numbers that are not numbers and enum values outside the list raise `DriverError` with the request and what to check.

## Limitations

- No login flows (session cookies, digest auth, OAuth). Devices that need them are not supported yet.
- No streaming or server-sent events. Values are read on request or by polling with `every`.
- No discovery. mDNS discovery belongs to the hub.
- Each read channel sends its own request, so channels that share an endpoint fetch it once each.

## Hazard default and safe state

The default hazard is medium, because an HTTP API can switch anything. HTTP has no protocol-level emergency behavior, so `safe_state_support` is `file`. The hub applies the device file's `safe_state` through ordinary writes, and that only works while the device answers.

## Sources

- RFC 9110 HTTP Semantics, https://www.rfc-editor.org/rfc/rfc9110
- RFC 9535 JSONPath, https://www.rfc-editor.org/rfc/rfc9535
- OpenAPI Specification 3.1.0, https://spec.openapis.org/oas/v3.1.0
- httpx documentation, transports and timeouts, https://www.python-httpx.org/advanced/transports/
- Shelly Gen2 API, Switch component, https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Switch
