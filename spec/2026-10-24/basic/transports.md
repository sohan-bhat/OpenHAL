# Transports

Every transport carries JSON-RPC 2.0 messages encoded as UTF-8 JSON. This version defines two transports. Both reach the same Hub functions, so a method behaves the same on either.

## WebSocket

1. The Hub serves the protocol at `ws://127.0.0.1:7420/rpc`. The port is configurable.
2. Each WebSocket text frame MUST carry exactly one JSON-RPC message.
3. Clients MUST NOT send binary frames.
4. The Hub applies the network rules in [Security](../security.md#network-exposure) before it accepts the connection.

## stdio

1. A Client that spawns a process runs `openhal rpc`. It bridges standard input and output to the Hub's WebSocket.
2. Each message is one line of UTF-8 JSON ending in `\n`. A message MUST NOT contain a raw newline.
3. The bridge writes nothing but messages to standard output. Diagnostics go to standard error.
4. When standard input closes, the bridge closes the WebSocket.

## Authentication

Every connection authenticates with a bearer token ([Security](../security.md#tokens)).

1. The Client sends the token in the `Authorization: Bearer <token>` header of the WebSocket handshake, or in the `token` param of `hal/initialize`.
2. A stdio Client sends the token in `hal/initialize`.
3. A missing, unknown or revoked token gets `UNAUTHORIZED` (-32002).
4. The Hub maps the token to one Principal for the life of the connection. `hal/initialize` reports it.
5. The Hub MUST NOT log tokens. The reference Hub redacts `token` from the `hal/initialize` params it records.

## Other front ends

The reference Hub also serves a REST API under `/v1` with the same tokens and network rules. It is a convenience for its dashboard and scripts and is not part of this specification.
