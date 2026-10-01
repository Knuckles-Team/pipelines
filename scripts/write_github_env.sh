#!/usr/bin/env bash
# Safely import KEY=VALUE pairs from a downloaded environment file (for
# example a build's CFLAGS) into the current shell and, when GITHUB_ENV is
# set, into the GitHub Actions step environment for later steps.
#
# A naive `source ./.env` misinterprets any multi-token value as a shell
# command: a line such as `CFLAGS=-O2 -march=native` sources as the prefix
# assignment `CFLAGS=-O2` applied to a command named `-march=native`, which
# does not exist. Reading the file ourselves and exporting each value as one
# quoted word -- and writing it to GITHUB_ENV with the delimited form GitHub
# Actions documents for values that may contain spaces -- keeps a multi-token
# value intact instead of letting the shell re-split it.
#
# Usage: write_github_env.sh <env-file>
# Source this script (rather than executing it) for the export to reach the
# invoking shell: `source write_github_env.sh ./.env`.
set -euo pipefail

env_file=${1:?usage: write_github_env.sh <env-file>}
delimiter="__PIPELINES_ENV_EOF_$$__"

while IFS='=' read -r key value || [ -n "${key:-}" ]; do
  key=${key%$'\r'}
  value=${value%$'\r'}
  case "$key" in
    '' | '#'*) continue ;;
  esac
  if [ -n "${GITHUB_ENV:-}" ]; then
    {
      printf '%s<<%s\n' "$key" "$delimiter"
      printf '%s\n' "$value"
      printf '%s\n' "$delimiter"
    } >> "$GITHUB_ENV"
  fi
  export "$key=$value"
done < "$env_file"
