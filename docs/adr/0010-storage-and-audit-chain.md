# 0010 SQLite for state, and an append-only audit log with a hash chain

## Context

The hub stores the device registry, routines, client tokens, the confirmation queue and the audit log. The audit log must be append-only and tamper-evident.

## Decision

- One SQLite database in the config directory (`~/.openhal/hub.db` by default), WAL mode, accessed from the hub only.
- The audit log is a table that the hub only inserts into. Each entry stores a canonical JSON body, the hash of the previous entry and its own SHA-256 over `previous_hash + body`. `openhal log --verify` recomputes the chain and reports the first broken entry.
- SQLite triggers reject UPDATE and DELETE on the audit table. This stops accidents, and the hash chain detects deliberate edits made outside the hub.
- Client tokens are stored as SHA-256 hashes, never in plain text.

## Consequences

A human with file access can still delete the whole database. The hash chain proves integrity of what remains. Exporting the chain head to somewhere else is on the roadmap.
