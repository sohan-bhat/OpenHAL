"""One daemon per config folder, and an audit chain two writers can't fork.

A second openhald on the same home used to write hub_start and hub_stop before it found the port
taken, and two writers each chained from their own memory of the last hash, which broke
`openhal log --verify`.
"""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from openhal.audit.log import AuditLog
from openhal.hub.config import ApiSettings, HubConfig
from openhal.hub.daemon import claim


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def config(home: Path, port: int) -> HubConfig:
    return HubConfig(home=home, api=ApiSettings(host="127.0.0.1", port=port))


def test_a_second_daemon_on_the_same_home_is_refused_before_it_logs(tmp_path: Path) -> None:
    first = claim(config(tmp_path, free_port()))
    try:
        with pytest.raises(SystemExit, match="already runs with the config folder"):
            claim(config(tmp_path, free_port()))
        assert not (tmp_path / "hub.db").exists()
    finally:
        first.release()
    claim(config(tmp_path, free_port())).release()


def test_a_taken_port_is_refused_and_the_home_stays_free(tmp_path: Path) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        taken = int(holder.getsockname()[1])
        with pytest.raises(SystemExit, match=f"Port {taken} on 127.0.0.1 is in use"):
            claim(config(tmp_path, taken))
    claim(config(tmp_path, free_port())).release()


def test_two_writers_on_one_file_extend_one_chain(tmp_path: Path) -> None:
    path = tmp_path / "hub.db"
    first, second = AuditLog(path), AuditLog(path)
    try:
        for index in range(6):
            (first if index % 2 == 0 else second).append("hub_start", "system", status="done", n=index)
        assert first.verify() == (True, None)
        assert second.verify() == (True, None)
    finally:
        first.close()
        second.close()
