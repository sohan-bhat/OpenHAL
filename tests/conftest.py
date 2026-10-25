"""Settings for the whole test session.

Typer forces a color terminal when GITHUB_ACTIONS, FORCE_COLOR or PY_COLORS is set, so CLI output in
CI carried escape codes that tests comparing text don't expect. Tests run with a plain terminal on
every machine, and so do the CLI processes they start.
"""

from __future__ import annotations

import os

for variable in ("GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS"):
    os.environ.pop(variable, None)
