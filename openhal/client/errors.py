"""Exceptions raised by the OpenHAL client.

A blocked write is not an exception. The kernel answers it with a `Decision` whose status is
`blocked`, and the client returns that decision. Exceptions are for calls the hub could not
answer or refused to take at all.
"""

from __future__ import annotations

from typing import Any


class OpenHALError(Exception):
    """Base class for every client error. `status_code` is the HTTP status when there was one."""

    def __init__(self, message: str, *, status_code: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail

    def __str__(self) -> str:
        return self.message


class HubNotRunning(OpenHALError):  # noqa: N818 (public name fixed by the brief)
    """Nothing answered at the hub address."""


class Unauthorized(OpenHALError):  # noqa: N818
    """The hub did not accept the token, or no token was found."""


class NotFound(OpenHALError):  # noqa: N818
    """The device, channel, request, routine or session does not exist."""


class NotSupported(NotFound):
    """The hub is older than this client and does not have the route at all."""


class Refused(OpenHALError):  # noqa: N818
    """The hub understood the call and refused it, for example an agent asking to approve."""


class BadRequest(OpenHALError):  # noqa: N818
    """The hub could not read the request. `detail` holds the validation problems."""


class HubError(OpenHALError):
    """The hub failed while answering. Check the hub log."""
