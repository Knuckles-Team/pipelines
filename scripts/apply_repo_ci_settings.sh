#!/usr/bin/env bash
# Apply the fleet CI repository settings (reference/ci-standard.md).
# Usage: apply_repo_ci_settings.sh [--dry-run] <owner/repo>
# Idempotent. Refuses (exit 2, no changes) unless the default branch already has a
# successful "CI required" job in its latest main-push run (PR runs never count).
set -euo pipefail

CHECK="CI required"
RULESET="Main integrity"
dry=0
repo=""
for a in "$@"; do
  case "$a" in
    --dry-run) dry=1 ;;
    -h|--help) sed -n '2,5p' "$0"; exit 0 ;;
    *) repo="$a" ;;
  esac
done
[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo "usage: $0 [--dry-run] <owner/repo>" >&2; exit 64; }

branch=$(gh api "repos/$repo" --jq .default_branch)
# Only a push run on the default branch counts: PR-run check runs on commits that
# a merge commit later brought into main must not satisfy this (they did, 2026-10-29,
# while tuig main itself was red). The latest main-push run that has a "CI required"
# job is the truth; it must have concluded success.
ok=0
for run in $(gh api "repos/$repo/actions/runs?branch=$branch&event=push&status=completed&per_page=20" --jq '.workflow_runs[].id'); do
  c=$(gh api "repos/$repo/actions/runs/$run/jobs?per_page=100" \
    --jq "[.jobs[] | select(.name==\"$CHECK\") | .conclusion] | first // empty")
  [[ -z "$c" ]] && continue
  [[ "$c" == success ]] && ok=1
  break
done
if [[ "$ok" -ne 1 ]]; then
  echo "refusing: the latest push run on $repo@$branch with a '$CHECK' job did not succeed (or none exists); no changes made" >&2
  exit 2
fi

rules=$(cat <<JSON
[{"type":"deletion"},{"type":"non_fast_forward"},
 {"type":"required_status_checks","parameters":{"strict_required_status_checks_policy":false,
  "required_status_checks":[{"context":"$CHECK"}]}}]
JSON
)
body=$(jq -n --arg name "$RULESET" --argjson rules "$rules" \
  '{name:$name,target:"branch",enforcement:"active",
    conditions:{ref_name:{include:["~DEFAULT_BRANCH"],exclude:[]}},rules:$rules}')

id=$(gh api "repos/$repo/rulesets" --jq ".[] | select(.name==\"$RULESET\") | .id" | head -n1)
echo "repo settings: allow_auto_merge=true delete_branch_on_merge=true"
if [[ -n "$id" ]]; then echo "ruleset: update '$RULESET' (id $id) -> required check '$CHECK'"
else echo "ruleset: create '$RULESET' -> required check '$CHECK'"; fi
if [[ "$dry" -eq 1 ]]; then echo "$body"; echo "dry run: no changes made"; exit 0; fi

gh api -X PATCH "repos/$repo" -F allow_auto_merge=true -F delete_branch_on_merge=true >/dev/null
if [[ -n "$id" ]]; then
  echo "$body" | gh api -X PUT "repos/$repo/rulesets/$id" --input - >/dev/null
else
  echo "$body" | gh api -X POST "repos/$repo/rulesets" --input - >/dev/null
fi
echo "applied to $repo"
