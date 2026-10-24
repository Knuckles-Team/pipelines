#!/usr/bin/env bash
# Install the pinned native scanners the shared hooks resolve (cccc, the kiss
# fork build, dupehound, jscpd). One definition shared by CI and
# `scripts/bootstrap.sh --scanners`; CI keys its cache on this file's hash.
# The pins must match pipelines_hooks/core/tools.py and core/kiss_fork.py
# (tests/hooks/test_install_scanners.py holds them in lockstep).
#
# Usage: scripts/install_scanners.sh [ROOT [SCANNER ...]]   (default root: ~/.local/share/pipelines-scanners)
# With SCANNER names (cccc kiss dupehound jscpd) only those are installed and printed;
# the connector PR workflow installs just dupehound.
# Prints the bin directories to put on PATH, one per line.
set -euo pipefail

root="${1:-$HOME/.local/share/pipelines-scanners}"
shift || true
only=("$@")
mkdir -p "$root"

want() {
  [[ "${#only[@]}" -eq 0 ]] && return 0
  local name
  for name in "${only[@]}"; do [[ "$name" == "$1" ]] && return 0; done
  return 1
}

install_crate() {
  local name="$1" bin="$2"
  shift 2
  if [[ -x "$root/$name/bin/$bin" ]]; then
    return
  fi
  cargo install --locked "$@" --root "$root/$name" >&2
}

want cccc && install_crate cccc cccc --git https://github.com/moznion/cccc --rev d728759323be5d9977b7390a27133e8eaf481f26 cccc-cli
want kiss && install_crate kiss kiss --git https://github.com/Knucklessg1/kiss --rev 7f1c6785697d3fe9a41ceb8b8e5d0f615fb1f3d9 kiss-ai
want dupehound && install_crate dupehound dupehound --version 0.1.2 dupehound
jscpd_bin_dir=""
if want jscpd; then
  jscpd_bin_dir="$(python3 "$(dirname "$0")/install_jscpd.py" --root "$root/jscpd")"
fi

want cccc && echo "$root/cccc/bin"
want kiss && echo "$root/kiss/bin"
want dupehound && echo "$root/dupehound/bin"
[[ -z "$jscpd_bin_dir" ]] || echo "$jscpd_bin_dir"
