#!/usr/bin/env bash
# myst --strict exits 0 on unresolved cross-references, so fail on that warning here.
# The grep string matches mystmd 1.12.0 output; re-check it when bumping the pin in package.json.
set -euo pipefail
log=$(mktemp)
trap 'rm -f "$log"' EXIT
myst build --html --strict --ci 2>&1 </dev/null | tee "$log"
if grep -q "Cross reference target was not found" "$log"; then
  echo "ERROR: unresolved cross-reference(s), see warnings above" >&2
  exit 1
fi
