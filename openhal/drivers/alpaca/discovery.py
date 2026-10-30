"""Alpaca discovery. A UDP broadcast of `alpacadiscovery1` to port 32227.

Every Alpaca server that receives it replies with `{"AlpacaPort": <http port>}` from its own
address (Alpaca API reference, "Alpaca Discovery"). Discovery only listens and changes nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any, Final

DISCOVERY_PORT: Final = 32227
MESSAGE: Final = b"alpacadiscovery1"
BROADCAST: Final = ("255.255.255.255", DISCOVERY_PORT)
ANY_ADDRESS: Final = "0.0.0.0"  # noqa: S104


class _Collector(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.found: set[tuple[str, int]] = set()

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        try:
            reply = json.loads(data[:512])
        except ValueError:
            return
        port = reply.get("AlpacaPort") if isinstance(reply, dict) else None
        if isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536:
            self.found.add((str(addr[0]), port))

    def error_received(self, exc: Exception) -> None:
        return None


async def probe(targets: list[tuple[str, int]], wait: float) -> list[tuple[str, int]]:
    """Send the discovery message to each target and collect (host, port) replies for `wait` seconds."""
    loop = asyncio.get_running_loop()
    try:
        transport, protocol = await loop.create_datagram_endpoint(
            _Collector,
            local_addr=(ANY_ADDRESS, 0),
            allow_broadcast=True,
        )
    except OSError:
        return []
    try:
        for target in targets:
            with contextlib.suppress(OSError):
                transport.sendto(MESSAGE, target)
        await asyncio.sleep(wait)
    finally:
        transport.close()
    return sorted(protocol.found)
