# Errors

The normative error registry is in [spec/v0.1/safety.md](v0.1/safety.md#error-registry), and this page summarizes the registry.

A blocked or failed command returns a JSON-RPC error. `error.code` is the number, `error.message` is the reason, and `error.data.name` is the registry name that Clients branch on. Numbers are stable across versions and never reused.

| Code | Name |
|---|---|
| -32700 | PARSE_ERROR |
| -32600 | INVALID_REQUEST |
| -32601 | METHOD_NOT_FOUND |
| -32602 | INVALID_PARAMS |
| -32603 | INTERNAL_ERROR |
| -32001 | NOT_INITIALIZED |
| -32002 | UNAUTHORIZED |
| -32003 | SCOPE_DENIED |
| -32004 | UNKNOWN_TARGET |
| -32005 | DEVICE_UNAVAILABLE |
| -32010 | LIMIT_EXCEEDED |
| -32011 | RATE_LIMITED |
| -32012 | INTERLOCK_BLOCKED |
| -32013 | CONFIRMATION_REQUIRED |
| -32014 | STOPPED |
| -32015 | UNVERIFIED_LIMITS |
| -32016 | INVALID_VALUE |
| -32017 | WATCHDOG_TRIPPED |
| -32018 | BUSY |
| -32019 | QUEUE_FULL |
| -32020 | DRIVER_ERROR |
| -32021 | MISCONFIGURED |
| -32022 | REQUEST_CLOSED |
| -32023 | UNIT_INVALID |

The kernel codes behind each name, the check order and the reason templates are in the [safety section](v0.1/safety.md) of v0.1. The error object's fields are in [messages](v0.1/basic/messages.md#errors).
