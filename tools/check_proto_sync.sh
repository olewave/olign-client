#!/usr/bin/env bash
# Verify the vendored proto/ still matches the olign server release this client
# is pinned to (OLIGN_VERSION). The protos here are a COPY of olign's
# src/io/proto -- they are vendored on purpose so external developers can build
# stubs without access to the private server repo, which means nothing stops
# them drifting. This is the check that catches that.
#
#   ./tools/check_proto_sync.sh                 # shallow-clones olign at the pin
#   OLIGN_SRC=../olign ./tools/check_proto_sync.sh   # use a local olign checkout
#
# Exit 0 = in sync, 1 = drift (prints a diff).
set -euo pipefail
cd "$(dirname "$0")/.."

PIN="$(tr -d ' \r\n' < OLIGN_VERSION)"
OLIGN_REPO="${OLIGN_REPO:-git@git.olewave.com:speech-modeling/olign.git}"

if [ -n "${OLIGN_SRC:-}" ]; then
  SRC="$OLIGN_SRC/src/io/proto"
  echo "comparing against local checkout: $SRC"
else
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  echo "fetching olign $PIN ..."
  git -c advice.detachedHead=false clone --depth 1 -b "$PIN" -q "$OLIGN_REPO" "$tmp/olign"
  SRC="$tmp/olign/src/io/proto"
fi
[ -d "$SRC" ] || { echo "ERROR: $SRC not found (wrong pin or layout moved)"; exit 1; }

fail=0
# vendored copy differs from the server's?
while IFS= read -r f; do
  if ! diff -q "proto/$f" "$SRC/$f" >/dev/null 2>&1; then
    if [ -f "$SRC/$f" ]; then
      echo "DRIFT: proto/$f differs from olign $PIN"
      diff -u "$SRC/$f" "proto/$f" | head -20
    else
      echo "STALE: proto/$f no longer exists in olign $PIN"
    fi
    fail=1
  fi
done < <(cd proto && find . -name '*.proto' | sed 's|^\./||' | sort)

# server gained a proto we never vendored?
while IFS= read -r f; do
  [ -f "proto/$f" ] || { echo "MISSING: olign $PIN has $f, not vendored here"; fail=1; }
done < <(cd "$SRC" && find . -name '*.proto' | sed 's|^\./||' | sort)

if [ "$fail" = 0 ]; then
  echo "OK: proto/ matches olign $PIN"
else
  echo
  echo "To resync: copy olign's src/io/proto/* over proto/, re-run ./gen_stubs.sh,"
  echo "and bump OLIGN_VERSION if you are moving to a new olign release."
  exit 1
fi
