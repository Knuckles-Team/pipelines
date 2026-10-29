#!/usr/bin/env bash
# Cut a connector release with one dispatch (reference/ci-standard.md, "How to release a connector").
# Usage: release_connector.sh <owner/repo> <patch|minor|major>
# Dispatches connector.yml with release=<level>; the workflow bumps the version, commits it to main,
# pushes the v<version> tag, and the tag push publishes PyPI, Docker and Pages. Prints the run URL.
set -euo pipefail

repo="${1:-}"
level="${2:-}"
[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo "usage: $0 <owner/repo> <patch|minor|major>" >&2; exit 64; }
case "$level" in patch|minor|major) ;; *) echo "usage: $0 <owner/repo> <patch|minor|major>" >&2; exit 64 ;; esac

since="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
gh workflow run connector.yml -R "$repo" -f "release=$level"
for _ in $(seq 1 30); do
  url="$(gh run list -R "$repo" --workflow connector.yml --event workflow_dispatch --limit 5 \
    --json url,createdAt --jq "[.[] | select(.createdAt >= \"$since\")] | first | .url // empty")"
  if [[ -n "$url" ]]; then echo "$url"; exit 0; fi
  sleep 2
done
echo "dispatched; run not visible yet: gh run list -R $repo --workflow connector.yml" >&2
