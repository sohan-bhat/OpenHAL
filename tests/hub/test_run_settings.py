"""Run caps live in config.yaml with safe defaults, and one section is rewritten without touching the rest."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from pydantic import ValidationError

from openhal.cli.init_cmd import CONFIG_TEMPLATE
from openhal.hub.config import RunSettings, load_config, save_section


def test_the_defaults_are_safe_and_bounded() -> None:
    caps = RunSettings()
    assert (caps.max_steps, caps.max_seconds, caps.per_agent) == (200, 600.0, 2)
    for bad in ({"max_steps": 0}, {"max_seconds": 0.5}, {"per_agent": 21}, {"max_seconds": 10**9}, {"other": 1}):
        with pytest.raises(ValidationError):
            RunSettings.model_validate(bad)


def test_the_init_template_names_the_caps(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(CONFIG_TEMPLATE, encoding="utf-8")
    assert load_config(tmp_path).runs == RunSettings()


def test_a_section_is_replaced_and_every_other_line_stays(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    save_section(tmp_path, "runs", {"max_steps": 50, "max_seconds": 120.0, "per_agent": 1})
    text = path.read_text(encoding="utf-8")
    assert "# true accepts connections from other machines" in text
    assert "agent_enable_low_hazard: false" in text
    assert text.count("runs:") == 1
    assert load_config(tmp_path).runs == RunSettings(max_steps=50, max_seconds=120, per_agent=1)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_a_section_in_the_middle_keeps_the_sections_after_it(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("runs:\n  max_steps: 10\n\n  per_agent: 1\nconfirm:\n  ttl_s: 60\n", encoding="utf-8")
    save_section(tmp_path, "runs", {"max_steps": 20})
    config = load_config(tmp_path)
    assert (config.runs.max_steps, config.runs.per_agent, config.confirm.ttl_s) == (20, 2, 60)


def test_a_comment_after_the_section_stays_and_no_staged_file_is_left(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("runs:\n  max_steps: 10\n# stop_button: tune for the Pi\nstop_button:\n  pull_up: true\n")
    save_section(tmp_path, "runs", {"max_steps": 20})
    text = path.read_text(encoding="utf-8")
    assert "# stop_button: tune for the Pi\nstop_button:" in text
    assert load_config(tmp_path).runs.max_steps == 20
    assert list(tmp_path.iterdir()) == [path]


def test_a_missing_section_or_file_is_added(tmp_path: Path) -> None:
    save_section(tmp_path, "runs", {"per_agent": 3})
    assert load_config(tmp_path).runs.per_agent == 3
    (tmp_path / "config.yaml").write_text("api:\n  port: 7421\n", encoding="utf-8")
    save_section(tmp_path, "runs", {"max_steps": 5})
    config = load_config(tmp_path)
    assert (config.api.port, config.runs.max_steps) == (7421, 5)


def test_a_value_that_would_not_load_never_reaches_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    with pytest.raises(ValidationError):
        save_section(tmp_path, "runs", {"max_steps": -1})
    assert path.read_text(encoding="utf-8") == CONFIG_TEMPLATE
