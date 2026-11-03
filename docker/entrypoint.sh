#!/bin/sh
set -eu

set_up() {
  openhal init --no-discover --no-service < /dev/null > /dev/null 2>&1 || {
    echo "openhal init failed in the container." >&2
    exit 1
  }
}

wait_for_hub() {
  tries=0
  until openhal status < /dev/null > /dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -ge 120 ]; then
      echo "The hub did not start within 60 s. The end of its log follows." >&2
      tail -n 20 "$OPENHAL_HOME/hub.log" >&2
      exit 1
    fi
    sleep 0.5
  done
}

command="${1:-mcp}"
[ "$#" -gt 0 ] && shift

case "$command" in
  mcp)
    if [ -n "${OPENHAL_URL:-}" ]; then
      exec openhal mcp --no-start "$@"
    fi
    set_up
    openhal start < /dev/null > "$OPENHAL_HOME/hub.log" 2>&1 &
    wait_for_hub
    created="$(openhal token create --name container < /dev/null)" || {
      echo "openhal token create failed in the container." >&2
      exit 1
    }
    OPENHAL_TOKEN="$(printf '%s\n' "$created" | tail -n 1)"
    export OPENHAL_TOKEN
    exec openhal mcp --no-start "$@"
    ;;
  *)
    exec openhal "$command" "$@"
    ;;
esac
