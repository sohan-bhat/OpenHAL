# http driver

The http driver connects to devices with a local HTTP API through httpx, and every request comes from the device file. Read maps name a request and where the value sits in the reply. Write maps and actions name a request with a body or query template.

## Supports

- Number, bool, string, enum and image reads from JSON through a JSON path, or from plain text.
- Number, bool, string and enum writes as a JSON body, query string or path segment, read back through a `state` request or else the last value sent.
- A bearer token or API key from an environment variable.

## Setup

```sh
uv tool install --compile-bytecode "halkit[http] @ git+https://github.com/sohan-bhat/OpenHAL"
```

| Parameter | Default | Meaning |
|---|---|---|
| `base_url` | required | `http://` or `https://` device URL. `http: "http://192.168.1.50"` is shorthand |
| `timeout` | `5 s` | Hard deadline per request |
| `headers` | none | Extra headers. Names that look like credentials fail validation |
| `token_env` | none | Variable holding a token |
| `auth_header` | `Authorization` | Header carrying the token |
| `auth_scheme` | `Bearer` | Token prefix. `""` for a bare API key |
| `verify_tls` | `true` | Check HTTPS certificates |
| `health` | `/` | GET path for connect and heartbeat. Any HTTP response counts as alive |
| `identify` | none | GET path for `identify()`. Scalar JSON fields become identity fields |
| `openapi` | none | OpenAPI 3 JSON path for `describe()` |
| `max_response_bytes` | `1048576` | Larger responses raise `DriverError` |

## Channel maps

```yaml
read:
  power: { unit: W, map: { path: /api/status, json: $.power.w } }
  mode: { type: enum, values: [auto, eco], map: { path: /api/mode } }   # text body
  snapshot: { type: image, map: { path: /snapshot.jpg } }
```

| Read key | Default | Meaning |
|---|---|---|
| `path` | required | Request path, starting with `/` |
| `method` | `GET` | `GET` or `POST` |
| `query` | none | Query parameters |
| `body` | none | JSON body for POST reads such as JSON-RPC |
| `json` | none | JSON path, an RFC 9535 subset with keys and list indexes such as `$.relays[0].on` |
| `format` | `json` with a path, else `text` | Body format |
| `on`, `off` | common words | True and false words for bools |
| `scale`, `offset` | `1`, `0` | value = device value × scale + offset |

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

| Write key | Default | Meaning |
|---|---|---|
| `path` | required | Request path. `{value}` in the path is URL-encoded |
| `method` | `POST` | GET, POST, PUT, PATCH or DELETE |
| `query`, `body` | none | Templates. A string of exactly `"{value}"` keeps the JSON type |
| `on`, `off` | the boolean | What to send for true and false |
| `scale`, `offset` | `1`, `0` | `device value = (value - offset) / scale`, whole results sent as integers |
| `state` | none | Read map for read-back |

Actions take `path`, `method`, `query` and `body` with `{arg}` per argument, and an optional `json` path for the result.

## Example

`openhal/drivers/http/examples/smart-plug.hal.yaml` drives a Shelly Plus Plug S through the Gen2 RPC API, which switches the relay with `GET /rpc/Switch.Set?id=0&on=true`.

## Describe from OpenAPI

With `openapi: /openapi.json`, `describe()` suggests reads for scalar GET reply fields one level deep, writes for scalar body fields whose numbers carry `minimum` and `maximum`, and actions for POST operations without a body. Units come from `x-unit`, else `dimensionless`. Writes and actions are marked `suggested: true`, so high risk entries stay read-only until a person confirms the limits, and lower risk entries run within the document's ranges. Paths with parameters, remote `$ref` pointers and YAML documents are skipped.

## Errors

`TimeoutError` past `timeout`. `DriverError` with the request and what to check for connection failures, HTTP 400 and above, bad or missing JSON, non-numbers and enum values outside the list.

## Limitations

- No login flows such as session cookies, digest auth or OAuth.
- No streaming or server-sent events. Poll with `every`.
- No discovery.
- Each read channel sends a separate request, even on a shared endpoint.

## Hazard default and safe state

Medium. `safe_state_support` is `file`, applied through ordinary writes while the device responds.

## Sources

- RFC 9110 HTTP Semantics, https://www.rfc-editor.org/rfc/rfc9110
- RFC 9535 JSONPath, https://www.rfc-editor.org/rfc/rfc9535
- OpenAPI Specification 3.1.0, https://spec.openapis.org/oas/v3.1.0
- httpx documentation, transports and timeouts, https://www.python-httpx.org/advanced/transports/
- Shelly Gen2 API, Switch component, https://shelly-api-docs.shelly.cloud/gen2/ComponentsAndServices/Switch
