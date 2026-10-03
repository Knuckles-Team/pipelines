#!/usr/bin/env bash
# Install the pinned native scanners the shared hooks resolve (cccc, the kiss
# fork build, dupehound, jscpd). One definition shared by CI and
# `scripts/bootstrap.sh --scanners`; CI keys its cache on this file's hash.
# The pins must match pipelines_hooks/core/tools.py and core/kiss_fork.py
# (tests/hooks/test_install_scanners.py holds them in lockstep).
#
# Usage: scripts/install_scanners.sh [ROOT]   (default: ~/.local/share/pipelines-scanners)
# Prints the bin directories to put on PATH, one per line.
set -euo pipefail

root="${1:-$HOME/.local/share/pipelines-scanners}"
mkdir -p "$root"

install_crate() {
  local name="$1" bin="$2"
  shift 2
  if [[ -x "$root/$name/bin/$bin" ]]; then
    return
  fi
  cargo install --locked "$@" --root "$root/$name" >&2
}

install_crate cccc cccc --git https://github.com/moznion/cccc --rev d728759323be5d9977b7390a27133e8eaf481f26 cccc-cli
install_crate kiss kiss --git https://github.com/Knucklessg1/kiss --rev 7f1c6785697d3fe9a41ceb8b8e5d0f615fb1f3d9 kiss-ai
install_crate dupehound dupehound --version 0.1.2 dupehound
jscpd_bin_dir="$(python3 "$(dirname "$0")/install_jscpd.py" --root "$root/jscpd")"

for bin_dir in cccc/bin kiss/bin dupehound/bin; do
  echo "$root/$bin_dir"
done
echo "$jscpd_bin_dir"
