#!/bin/sh
set -eu

DISTRIBUTION="halkit"
REPOSITORY="https://github.com/sohan-bhat/OpenHAL"
SITE="https://sohan-bhat.github.io/OpenHAL"
UV_VERSION="0.13.5"
PYTHON_VERSION="3.12"

say() {
  printf '%s\n' "$*"
}

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

case "$(uname -s)" in
  Darwin | Linux) ;;
  MINGW* | MSYS* | CYGWIN*) fail "On Windows, install OpenHAL from PowerShell with
  irm $SITE/install.ps1 | iex" ;;
  *) fail "The OpenHAL installer runs on macOS, Linux and Windows, and this system is $(uname -s)." ;;
esac

command -v curl >/dev/null 2>&1 || fail "The OpenHAL installer needs curl. Install curl, then run the installer again."

status() {
  curl -sSIL -o /dev/null -w '%{http_code}' "$1" 2>/dev/null || true
}

found() {
  case "$(status "$1")" in
    200) return 0 ;;
    404) return 1 ;;
    *) fail "The installer could not reach $1. Check the network connection, then run the installer again." ;;
  esac
}

uv_dir="${UV_INSTALL_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}"
uv="$(command -v uv 2>/dev/null || true)"
if [ -z "$uv" ] && [ -x "$uv_dir/uv" ]; then
  uv="$uv_dir/uv"
fi
if [ -z "$uv" ]; then
  say "Installing uv $UV_VERSION in $uv_dir"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  trap 'exit 130' INT TERM
  curl -fsSL -o "$tmp/uv-installer.sh" "https://astral.sh/uv/$UV_VERSION/install.sh" ||
    fail "The installer could not download uv $UV_VERSION from astral.sh, so uv and OpenHAL are not installed."
  UV_INSTALL_DIR="$uv_dir" UV_NO_MODIFY_PATH=1 sh "$tmp/uv-installer.sh" --quiet ||
    fail "The uv installer from astral.sh stopped with an error, so uv and OpenHAL are not installed."
  uv="$uv_dir/uv"
fi

bin="$("$uv" tool dir --bin 2>/dev/null)" ||
  fail "The uv at $uv has no tool command. Update that uv, or remove it so the installer puts uv $UV_VERSION in place."

version="${OPENHAL_VERSION:-}"
version="${version#v}"
source="${OPENHAL_SOURCE:-}"
if [ -n "$source" ]; then
  case "$source" in
    *://*) spec="$DISTRIBUTION @ $source" ;;
    *) spec="$source" ;;
  esac
  where="$source"
elif [ -n "$version" ]; then
  if found "https://pypi.org/pypi/$DISTRIBUTION/$version/json"; then
    spec="$DISTRIBUTION==$version"
    where="PyPI"
  elif found "$REPOSITORY/archive/refs/tags/v$version.tar.gz"; then
    spec="$DISTRIBUTION @ $REPOSITORY/archive/refs/tags/v$version.tar.gz"
    where="the tag v$version of $REPOSITORY"
  else
    fail "OpenHAL $version is neither on PyPI nor tagged v$version in $REPOSITORY. Leave OPENHAL_VERSION unset to install the newest OpenHAL."
  fi
elif found "https://pypi.org/pypi/$DISTRIBUTION/json"; then
  spec="$DISTRIBUTION"
  where="PyPI"
else
  spec="$DISTRIBUTION @ $REPOSITORY/archive/refs/heads/main.tar.gz"
  where="the main branch of $REPOSITORY"
fi

set -- --no-build
case "$spec" in
  "$DISTRIBUTION" | "$DISTRIBUTION=="* | *.whl) ;;
  *) set -- "$@" --no-binary-package "$DISTRIBUTION" ;;
esac

say "Installing OpenHAL from $where"
PATH="$bin:$PATH" "$uv" tool install --upgrade --compile-bytecode --python "$PYTHON_VERSION" "$@" "$spec" ||
  fail "uv stopped with the error above, so OpenHAL is not installed."

printed="$("$bin/openhal" --version 2>/dev/null || true)"
[ -n "$printed" ] || fail "uv finished, but $bin/openhal --version printed nothing."

say ""
say "OpenHAL ${printed#openhal } is now in $bin."
case ":$PATH:" in
  *":$bin:"*)
    other="$(command -v openhal 2>/dev/null || true)"
    if [ -n "$other" ] && [ "$other" != "$bin/openhal" ]; then
      say "Your shell runs the openhal at $other, because that folder comes before $bin on your PATH."
    fi
    ;;
  *)
    say ""
    say "$bin is not on your PATH yet. Add the folder for this terminal with"
    say "  export PATH=\"$bin:\$PATH\""
    say "and for every new terminal with"
    say "  $uv tool update-shell"
    ;;
esac
say ""
say "Set up your first device and your AI clients with"
say "  openhal init"
