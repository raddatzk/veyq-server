#!/usr/bin/env bash
# Refuses a commit that would put secret material into Git in plaintext. Run by .githooks/pre-commit
# (git config core.hooksPath .githooks) and by hand: scripts/check-secrets.sh [files…] (default: all tracked + staged).
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
files=("$@")
if [ "${#files[@]}" -eq 0 ]; then
  # A while-read loop, not mapfile: macOS still ships bash 3.2.
  while IFS= read -r f; do files+=("$f"); done < <( { git ls-files; git diff --cached --name-only --diff-filter=ACM; } | sort -u)
fi
fail=0
for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  case "$f" in
    .sops.yaml) ;;  # the rules file, not a secret
    *.sops.yaml)
      if ! grep -q '^sops:' "$f" || ! grep -q 'ENC\[' "$f" || ! grep -q '^    mac: ENC\[\|^  mac: ENC\[' "$f"; then
        echo "NOT ENCRYPTED: $f" >&2; fail=1
      fi ;;
  esac
  if grep -qE 'AGE-SECRET-KEY-1[0-9A-Z]{20,}' "$f"; then echo "AGE PRIVATE KEY in $f" >&2; fail=1; fi
  if grep -q -- '-----BEGIN [A-Z ]*PRIVATE KEY-----' "$f"; then echo "PRIVATE KEY in $f" >&2; fail=1; fi
done
exit "$fail"
