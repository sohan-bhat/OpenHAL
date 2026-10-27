"""Every public name in one place.

A rename of the product is a change to this module, pyproject.toml and the website config
(ADR 0002). Nothing else in the package hard-codes these strings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

PRODUCT_NAME: Final = "OpenHAL"
PRODUCT_LONG_NAME: Final = "Open Hardware Agent Layer"
PACKAGE_NAME: Final = "openhal"
DISTRIBUTION_NAME: Final = "openhal-hub"
CLI_NAME: Final = "openhal"
DAEMON_NAME: Final = "openhald"
ARDUINO_LIBRARY_NAME: Final = "OpenHAL"
DEVICE_FILE_SUFFIX: Final = ".hal.yaml"
ROUTINE_FILE_SUFFIX: Final = ".routine.yaml"
SPEC_VERSION: Final = "0.1"
API_VERSION: Final = "v1"
DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 7420
CONFIG_DIR_ENV: Final = "OPENHAL_HOME"
DEFAULT_CONFIG_DIR: Final = Path.home() / ".openhal"
DATA_BLOCK_TAG: Final = "device-data"


def config_dir() -> Path:
    """Return the hub's config directory, honoring the OPENHAL_HOME environment variable."""
    import os

    override = os.environ.get(CONFIG_DIR_ENV)
    return Path(override).expanduser() if override else DEFAULT_CONFIG_DIR
