"""The OpenHAL hub protocol, JSON-RPC 2.0 with numbered versions such as 0.1 (ADR 0015, ADR 0017).

`messages` holds the Pydantic models for every message, `errors` the error registry, `dispatch`
the one dispatcher both transports use, and `version` the supported versions.
"""
