#!/usr/bin/env bash
set -euo pipefail

usage="Usage: bash docs/hardware-tests/hub.sh start|stop|restart|kill|status"
home="${OPENHAL_HOME:?Set OPENHAL_HOME to the test home first, for example export OPENHAL_HOME=\"\$PWD/openhal-test\".}"
daemon=".venv/bin/openhald"
pidfile="$home/hub.pid"
logfile="$home/hub.log"

running() {
  [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

start() {
  if running; then
    echo "hub already running, pid $(cat "$pidfile")"
    return
  fi
  if [[ ! -x "$daemon" ]]; then
    echo "No $daemon here. Run this from the checkout's root after uv sync." >&2
    exit 1
  fi
  "$daemon" --verbose >> "$logfile" 2>&1 &
  echo $! > "$pidfile"
  for _ in $(seq 120); do
    if uv run openhal status > /dev/null 2>&1; then
      echo "hub running, pid $(cat "$pidfile"), log $logfile"
      return
    fi
    if ! running; then
      echo "The hub exited. The end of $logfile says why." >&2
      exit 1
    fi
    sleep 0.5
  done
  echo "The hub sent no reply within 60 s. See $logfile." >&2
  exit 1
}

stop() {
  local signal="$1"
  if ! running; then
    echo "hub not running"
    rm -f "$pidfile"
    return
  fi
  local pid
  pid="$(cat "$pidfile")"
  kill "-$signal" "$pid"
  while kill -0 "$pid" 2>/dev/null; do
    sleep 0.2
  done
  rm -f "$pidfile"
  echo "hub stopped with SIG$signal"
}

case "${1:-}" in
  start) start ;;
  stop) stop TERM ;;
  restart) stop TERM; start ;;
  kill) stop KILL ;;
  status) if running; then echo "hub running, pid $(cat "$pidfile")"; else echo "hub not running"; fi ;;
  *) echo "$usage" >&2; exit 2 ;;
esac
