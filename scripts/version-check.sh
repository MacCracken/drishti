#!/usr/bin/env bash
# Verify version consistency across VERSION, cyrius.cyml, CHANGELOG.md, README.md.
# `version = "${file:VERSION}"` in the manifest means VERSION is the single
# source of truth — the check below enforces that downstream references
# (CHANGELOG header, README badge) agree.
#
# Wired into `make test-all` so drift cannot escape CI.
# Adapted from chitra/scripts/version-check.sh.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

FILE_VERSION=$(tr -d '[:space:]' < VERSION)
fail=0

# Allow the manifest to either inline the version or template it from VERSION.
# The manifest's `version = "${file:VERSION}"` form is valid — so we only
# diff when the manifest has a literal version string.
if grep -qE '^version = "[0-9]' cyrius.cyml; then
    MANIFEST_VERSION=$(grep -E '^version = "' cyrius.cyml | head -1 | sed -E 's/version = "([^"]*)"/\1/')
    if [ "$FILE_VERSION" != "$MANIFEST_VERSION" ]; then
        echo "  FAIL: VERSION ($FILE_VERSION) != cyrius.cyml ($MANIFEST_VERSION)"
        fail=1
    fi
fi

if ! grep -q "^## \[$FILE_VERSION\]" CHANGELOG.md; then
    echo "  FAIL: version $FILE_VERSION missing from CHANGELOG.md"
    fail=1
fi

if [ -f README.md ] && grep -q "^Version:" README.md; then
    README_VERSION=$(grep '^Version:' README.md | head -1 | awk '{print $2}')
    if [ "$README_VERSION" != "$FILE_VERSION" ]; then
        echo "  FAIL: README.md Version ($README_VERSION) != VERSION ($FILE_VERSION)"
        fail=1
    fi
fi

# drishti_version() in src/drishti.cyr packs MAJOR*10000 + MINOR*100 + PATCH —
# keep it in lockstep with the VERSION file.
PACKED=$(echo "$FILE_VERSION" | awk -F. '{ print $1*10000 + $2*100 + $3 }')
CODE_PACKED=$(grep -A1 'fn drishti_version' src/drishti.cyr | grep -oE 'return [0-9]+' | awk '{print $2}')
if [ -n "$CODE_PACKED" ] && [ "$PACKED" != "$CODE_PACKED" ]; then
    echo "  FAIL: drishti_version() returns $CODE_PACKED but VERSION $FILE_VERSION packs to $PACKED"
    fail=1
fi

if [ $fail -eq 0 ]; then
    echo "  OK: version $FILE_VERSION consistent across VERSION, cyrius.cyml, CHANGELOG.md, drishti_version()"
fi

exit $fail
