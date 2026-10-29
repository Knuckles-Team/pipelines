#!/usr/bin/env bash
# Arm native auto-merge on a pull request as the owner (reference/ci-standard.md).
# Usage: arm_auto_merge.sh <owner/repo> <pr-number>
# Refuses (exit 2, nothing armed) unless the repository's main requires the check "CI required"
# (repository rules and classic branch protection are unioned). Otherwise runs
# gh pr merge <pr> --auto --merge --match-head-commit <head sha> with the owner's gh login.
set -euo pipefail

CHECK="CI required"
repo="${1:-}"
pr="${2:-}"
[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ && "$pr" =~ ^[0-9]+$ ]] || { echo "usage: $0 <owner/repo> <pr-number>" >&2; exit 64; }

contexts="$(
  {
    gh api "repos/$repo/rules/branches/main" \
      --jq '.[] | select(.type=="required_status_checks") | .parameters.required_status_checks[].context' 2>/dev/null || true
    gh api "repos/$repo/branches/main/protection" \
      --jq '(.required_status_checks.contexts[]?), (.required_status_checks.checks[]?.context)' 2>/dev/null || true
  } | sort -u
)"
if ! grep -Fxq "$CHECK" <<<"$contexts"; then
  echo "refusing: main of $repo does not require the check '$CHECK'; nothing armed" >&2
  exit 2
fi

sha="$(gh pr view "$pr" -R "$repo" --json headRefOid --jq .headRefOid)"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "could not read the head sha of $repo#$pr" >&2; exit 1; }
gh pr merge "$pr" -R "$repo" --auto --merge --match-head-commit "$sha"
echo "armed $repo#$pr at $sha"
