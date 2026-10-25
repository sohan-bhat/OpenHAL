"""Setting up a machine for the hub. The background service, MCP client configs and found devices.

`openhal init` and `openhal service` use these modules. Every command and file change they make
goes through `openhal.service.runner.Runner`, so `--dry-run` and tests change nothing.
"""
