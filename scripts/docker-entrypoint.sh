#!/bin/sh
set -eu

command="${1:-mcp}"
[ "$#" -gt 0 ] && shift

if [ "$command" != mcp ]; then
  exec openhal "$command" "$@"
fi

if [ -n "${OPENHAL_URL:-}" ]; then
  exec openhal mcp --no-start "$@"
fi

openhal init --no-discover --no-service < /dev/null > /dev/null 2>&1 || {
  echo "openhal init failed in the container." >&2
  exit 1
}
created="$(openhal token create --name container < /dev/null)" || {
  echo "openhal token create failed in the container." >&2
  exit 1
}
OPENHAL_TOKEN="$(printf '%s\n' "$created" | tail -n 1)"
export OPENHAL_TOKEN
exec openhal mcp "$@"
