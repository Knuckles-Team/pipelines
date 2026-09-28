#!/usr/bin/env bash
# One-command contributor setup from a fresh clone (local or Claude Code on the web).
#
#   scripts/bootstrap.sh              uv, locked Python + test deps, git hooks
#   scripts/bootstrap.sh --scanners   also the pinned native scanners (cargo/npm builds)
#
# Idempotent and non-interactive. Afterwards:
#   uv run --frozen python -m pytest -q
#   uvx pre-commit run --config .config/pre-commit.yaml --all-files
set -euo pipefail

cd "$(dirname "$0")/.."

scanners=0
for arg in "$@"; do
  case "$arg" in
    --scanners) scanners=1 ;;
    -h | --help)
      sed -n '2,9p' "$0"
      exit 0
      ;;
    *)
      echo "unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# uv: releases before 0.9 cannot download current CPython patch releases.
# pip first, then (on an externally managed Python) astral's own self-updater;
# a piped network installer is refused by this repository's supply-chain gate.
uv_minor() { uv --version 2>/dev/null | awk '{split($2, v, "."); print v[1] * 1000 + v[2]}'; }
uv_current() { command -v uv >/dev/null 2>&1 && [[ "$(uv_minor)" -ge 9 ]]; }
if ! uv_current; then
  echo "bootstrap: installing a current uv"
  python3 -m pip install --quiet --user --upgrade "uv>=0.9" || true
  hash -r
  if ! uv_current && command -v uv >/dev/null 2>&1; then
    uv self update || true
  fi
  if ! uv_current; then
    python3 -m pip install --quiet --user --break-system-packages --upgrade "uv>=0.9"
  fi
  hash -r
  uv_current || { echo "bootstrap: could not install uv >= 0.9" >&2; exit 2; }
fi

echo "bootstrap: locked Python environment with test dependencies"
uv sync --frozen

echo "bootstrap: git hooks (pre-commit and pre-push)"
uvx pre-commit install --config .config/pre-commit.yaml --hook-type pre-commit --hook-type pre-push

if [[ "$scanners" == 1 ]]; then
  echo "bootstrap: native scanners"
  scanner_root="$HOME/.local/share/pipelines-scanners"
  bash scripts/install_scanners.sh "$scanner_root" >/dev/null
  echo "bootstrap: add the scanners to PATH:"
  bash scripts/install_scanners.sh "$scanner_root" | sed 's/^/  export PATH="/; s/$/:$PATH"/'
fi

echo "bootstrap: done"
