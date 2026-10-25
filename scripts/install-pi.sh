#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Install the OpenHAL hub on a Raspberry Pi.

  scripts/install-pi.sh [--dry-run] [--source SPEC]

It installs uv if it is missing, the system packages the Pi drivers need and the hub with the Pi
extras. It adds you to the gpio, i2c, spi and dialout groups, installs the background service with
lingering so the hub runs without a login, and prints the command to run next.

  --dry-run      Print every command and run none.
  --source SPEC  Install from a wheel, a checkout or a git URL.
                 Default git+https://github.com/sohan-bhat/OpenHAL
EOF
}

DRY_RUN=0
SOURCE="git+https://github.com/sohan-bhat/OpenHAL"
EXTRAS="rpi-gpio,rpi-camera,pi-i2c-spi,serial,openhal-firmware"
WANTED_GROUPS="gpio i2c spi dialout"
VENV="$HOME/.local/share/openhal/venv"
BIN="$HOME/.local/bin"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --source)
      [ $# -ge 2 ] || { echo "--source needs a wheel, a folder or a URL." >&2; exit 2; }
      SOURCE="$2"
      shift
      ;;
    -h | --help) usage; exit 0 ;;
    *) echo "Unknown option $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

say() {
  printf '%s\n' "$*"
}

quote() {
  case "$1" in
    *[!A-Za-z0-9_@%+=:,./-]*)
      local escaped=${1//\'/\'\\\'\'}
      printf "'%s'" "$escaped"
      ;;
    *) printf '%s' "$1" ;;
  esac
}

run() {
  if [ "$DRY_RUN" -eq 1 ]; then
    local line="would run" word
    for word in "$@"; do
      line="$line $(quote "$word")"
    done
    say "$line"
  else
    "$@"
  fi
}

if [ "$DRY_RUN" -eq 0 ] && [ "$(uname -s)" != "Linux" ]; then
  say "This script sets up a Raspberry Pi running Linux. Add --dry-run to see what it would do." >&2
  exit 1
fi
if [ "$DRY_RUN" -eq 0 ] && [ "$(id -u)" -eq 0 ]; then
  say "Run this as your own user, not as root. It asks for sudo where it needs it." >&2
  exit 1
fi
USER_NAME="${USER:-$(id -un)}"

UV="$(command -v uv || true)"
if [ -z "$UV" ]; then
  say "Installing uv"
  run sh -c "curl -LsSf https://astral.sh/uv/install.sh | sh"
  UV="$HOME/.local/bin/uv"
fi

PYTHON="3.12"
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
  PYTHON="$(command -v python3)"
else
  say "The system Python is older than 3.12, so uv provides one. The camera driver needs Raspberry Pi OS with Python 3.12 or newer."
fi

if [ "$DRY_RUN" -eq 1 ] || command -v apt-get >/dev/null 2>&1; then
  say "Installing the system packages the Pi drivers build with and use"
  run sudo apt-get update
  if [ "$PYTHON" = "3.12" ]; then
    run sudo apt-get install -y --no-install-recommends build-essential
  else
    run sudo apt-get install -y --no-install-recommends build-essential python3-dev python3-lgpio python3-picamera2
  fi
fi

case "$SOURCE" in
  git+* | http://* | https://*) SPEC="openhal-hub[$EXTRAS] @ $SOURCE" ;;
  *) SPEC="${SOURCE}[$EXTRAS]" ;;
esac

say "Installing the hub in $VENV"
run "$UV" venv --allow-existing --system-site-packages --python "$PYTHON" "$VENV"
run "$UV" pip install --python "$VENV/bin/python" --compile-bytecode "$SPEC"
run mkdir -p "$BIN"
run ln -sf "$VENV/bin/openhal" "$BIN/openhal"
run ln -sf "$VENV/bin/openhald" "$BIN/openhald"

ADD=""
for group in $WANTED_GROUPS; do
  if ! command -v getent >/dev/null 2>&1 || getent group "$group" >/dev/null 2>&1; then
    ADD="${ADD:+$ADD,}$group"
  fi
done
if [ -n "$ADD" ]; then
  say "Adding $USER_NAME to $ADD"
  run sudo usermod -aG "$ADD" "$USER_NAME"
fi

say "Installing the background service"
run sudo loginctl enable-linger "$USER_NAME"
run "$BIN/openhal" service install

say ""
say "Done. Log out and back in so the new groups apply, then run"
say "  openhal init"
