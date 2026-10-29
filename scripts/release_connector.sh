#!/usr/bin/env bash
# Cut a connector release as the owner, with the owner's gh login (reference/ci-standard.md).
# Usage: release_connector.sh [--dry-run] <owner/repo> <patch|minor|major>
#  a) refuses unless main's latest push run has a successful "CI required" job
#  b) next version from the latest v* tag (else pyproject [project].version)
#  c) opens a version-bump PR from a temporary clone, arms it (scripts/arm_auto_merge.sh)
#  d) waits for it to merge (RELEASE_WAIT_SECONDS, default 3600)
#  e) creates the annotated tag v<version> on the merge commit through the API; the owner's tag
#     push triggers the publish path
#  f) prints the publish run URL
set -euo pipefail

CHECK="CI required"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dry=0
args=()
for a in "$@"; do
  case "$a" in
    --dry-run) dry=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) args+=("$a") ;;
  esac
done
repo="${args[0]:-}"
level="${args[1]:-}"
usage="usage: $0 [--dry-run] <owner/repo> <patch|minor|major>"
[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || { echo "$usage" >&2; exit 64; }
case "$level" in patch|minor|major) ;; *) echo "$usage" >&2; exit 64 ;; esac

# a) main's latest push run must have a successful CI required job.
run_id="$(gh run list -R "$repo" --branch main --event push --limit 1 --json databaseId --jq '.[0].databaseId // empty')"
ok=""
if [[ -n "$run_id" ]]; then
  ok="$(gh run view "$run_id" -R "$repo" --json jobs --jq "[.jobs[] | select(.name==\"$CHECK\" and .conclusion==\"success\")] | length")"
fi
if [[ -z "$ok" || "$ok" -lt 1 ]]; then
  echo "refusing: the latest push run on main of $repo has no successful '$CHECK' job; nothing changed" >&2
  exit 2
fi

# b) next version.
latest="$(gh api "repos/$repo/git/matching-refs/tags/v" --jq '.[].ref' | sed 's#refs/tags/v##' \
  | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -n1 || true)"
pyproject="$(gh api "repos/$repo/contents/pyproject.toml" --jq .content | base64 -d)"
name="$(python3 -c 'import sys,tomllib; print(tomllib.loads(sys.stdin.read())["project"]["name"])' <<<"$pyproject")"
base="$latest"
[[ -n "$base" ]] || base="$(python3 -c 'import sys,tomllib; print(tomllib.loads(sys.stdin.read())["project"]["version"])' <<<"$pyproject")"
version="$(python3 - "$base" "$level" <<'PY'
import sys
major, minor, patch = (int(p) for p in sys.argv[1].split(".")[:3])
level = sys.argv[2]
if level == "major": major, minor, patch = major + 1, 0, 0
elif level == "minor": minor, patch = minor + 1, 0
else: patch += 1
print(f"{major}.{minor}.{patch}")
PY
)"
if gh api "repos/$repo/git/ref/tags/v$version" >/dev/null 2>&1; then
  echo "refusing: tag v$version already exists in $repo" >&2
  exit 2
fi
echo "release: $name $base -> $version ($level) on $repo"
if [[ "$dry" -eq 1 ]]; then
  echo "dry run: would open 'chore(release): bump $name to $version', arm it, wait, tag v$version; no changes made"
  exit 0
fi

# c) version-bump PR from a temporary clone.
dir="${XDG_STATE_HOME:-$HOME/.local/state}/repository-worktrees/${repo#*/}/release-$version"
[[ ! -e "$dir" ]] || { echo "refusing: $dir already exists" >&2; exit 2; }
mkdir -p "$(dirname "$dir")"
gh repo clone "$repo" "$dir" -- --quiet --depth 1
branch="release/bump-v$version"
git -C "$dir" checkout -q -b "$branch"
python3 - "$dir" "$name" "$version" <<'PY'
import pathlib, re, sys
root, name, version = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
py = root / "pyproject.toml"
text = py.read_text()
head, sep, rest = text.partition("[project]")
rest, n = re.subn(r'(?m)^version\s*=\s*"[^"]*"', f'version = "{version}"', rest, count=1)
if not sep or n != 1:
    sys.exit("could not set [project].version in pyproject.toml")
py.write_text(head + sep + rest)
lock = root / "uv.lock"
if lock.exists():
    pattern = re.compile(r'(\[\[package\]\]\nname = "' + re.escape(name) + r'"\nversion = ")[^"]*(")')
    lock.write_text(pattern.sub(lambda m: m.group(1) + version + m.group(2), lock.read_text(), count=1))
PY
files=(pyproject.toml)
if [[ -e "$dir/uv.lock" ]] && ! git -C "$dir" diff --quiet -- uv.lock; then files+=(uv.lock); fi
git -C "$dir" add -- "${files[@]}"
git -C "$dir" commit -q -m "chore(release): bump $name to $version" -m "Spec: none (release)
Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git -C "$dir" push -q origin "$branch"
pr_url="$(gh pr create -R "$repo" --base main --head "$branch" \
  --title "chore(release): bump $name to $version" \
  --body "Sets [project].version to $version. The owner tags v$version on the merge commit; the tag push publishes.")"
pr="${pr_url##*/}"
rm -rf "$dir"

# d) arm and wait for the merge.
"$here/arm_auto_merge.sh" "$repo" "$pr"
deadline=$(( $(date +%s) + ${RELEASE_WAIT_SECONDS:-3600} ))
merge_sha=""
while [[ -z "$merge_sha" ]]; do
  state="$(gh pr view "$pr" -R "$repo" --json state,mergeCommit --jq '.state + " " + (.mergeCommit.oid // "")')"
  case "$state" in
    MERGED\ *) merge_sha="${state#MERGED }" ;;
    CLOSED*) echo "pull request $pr_url was closed without merging; no tag created" >&2; exit 1 ;;
  esac
  [[ -n "$merge_sha" ]] && break
  [[ "$(date +%s)" -lt "$deadline" ]] || { echo "timed out waiting for $pr_url to merge; no tag created" >&2; exit 1; }
  sleep "${RELEASE_POLL_SECONDS:-20}"
done

# e) annotated tag on the merge commit, created by the owner's token.
tag_sha="$(gh api -X POST "repos/$repo/git/tags" -f tag="v$version" -f message="Release v$version" \
  -f object="$merge_sha" -f type=commit --jq .sha)"
gh api -X POST "repos/$repo/git/refs" -f ref="refs/tags/v$version" -f sha="$tag_sha" >/dev/null
echo "tagged v$version at $merge_sha"

# f) publish run URL.
for _ in $(seq 1 30); do
  url="$(gh run list -R "$repo" --workflow connector.yml --event push --branch "v$version" --limit 1 --json url --jq '.[0].url // empty')"
  if [[ -n "$url" ]]; then echo "$url"; exit 0; fi
  sleep 2
done
echo "tag pushed; run not visible yet: gh run list -R $repo --workflow connector.yml" >&2
