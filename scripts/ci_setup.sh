#!/usr/bin/env bash
# CI setup for this repository's own PR gate: the operator-owned identity catalog for
# tracked-privacy, then the locked environment (PIPE-GATES-R016.42).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# The prohibited-identity catalog arrives through the organization's PROHIBITED_IDENTITY_CATALOG
# Actions variable. A missing catalog fails closed, except on a fork pull request, which cannot read it.
if [ -n "${PROHIBITED_IDENTITY_CATALOG:-}" ]; then
  mkdir -p "$HOME/.config/arbora/governance"
  printf '%s' "$PROHIBITED_IDENTITY_CATALOG" > "$HOME/.config/arbora/governance/prohibited-identities.json"
elif [ "${FORK_PULL_REQUEST:-false}" != "true" ]; then
  echo "tracked-privacy: CANNOT RUN: the PROHIBITED_IDENTITY_CATALOG Actions variable is not available to this repository" >&2
  exit 2
fi

uv sync --frozen
