#!/usr/bin/env bash
# Write k3s_checksums for the k3s_version in the Ansible inventory, from that release's own sha256sum-<arch>.txt.
#   bash scripts/update-k3s-checksums.sh
# Run by Renovate as a post-upgrade task right after it raised k3s_version (renovate.json, the "k3s" rule), so the
# PR carries version and checksums together; runnable by hand the same way. Changes nothing when they already match.
#
# What it guarantees: the checksums in Git are the ones the release published, so the playbook's download refuses
# any other binary. What it cannot: tell a genuine release from one replaced wholesale (binary and sums together).
set -euo pipefail
cd "$(dirname "$0")/.."
file=ansible/inventory/group_vars/server/main.yml

version=$(awk '/^k3s_version:/ { print $2; exit }' "$file")
if [[ ! $version =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-rc[0-9]+)?\+k3s[0-9]+$ ]]; then
  echo "k3s_version in $file is '${version}', not v<x.y.z>+k3s<n>" >&2
  exit 1
fi
base="https://github.com/k3s-io/k3s/releases/download/${version/+/%2B}"

sum() {  # arch asset
  local s
  s=$(curl -fsSL --retry 3 "$base/sha256sum-$1.txt" | awk -v a="$2" '$2 == a { print $1 }')
  if [[ ! $s =~ ^[0-9a-f]{64}$ ]]; then
    echo "no sha256 for $2 in $base/sha256sum-$1.txt" >&2
    exit 1
  fi
  printf '%s' "$s"
}
amd64=$(sum amd64 k3s)
arm64=$(sum arm64 k3s-arm64)

# Replace the two values inside the k3s_checksums block only; every other line stays byte for byte.
tmp=$(mktemp)
awk -v amd64="$amd64" -v arm64="$arm64" '
  /^k3s_checksums:/ { inblock = 1; print; next }
  inblock && /^  amd64: / { print "  amd64: " amd64; n++; next }
  inblock && /^  arm64: / { print "  arm64: " arm64; n++; next }
  inblock && !/^  / { inblock = 0 }
  { print }
  END { if (n != 2) exit 3 }
' "$file" > "$tmp" || { rm -f "$tmp"; echo "k3s_checksums block with amd64/arm64 not found in $file" >&2; exit 1; }
if cmp -s "$tmp" "$file"; then
  rm -f "$tmp"
  echo "k3s $version: checksums already current"
else
  cat "$tmp" > "$file"
  rm -f "$tmp"
  echo "k3s $version: checksums written (amd64 ${amd64:0:12}…, arm64 ${arm64:0:12}…)"
fi
