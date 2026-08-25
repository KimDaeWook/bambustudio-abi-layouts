#!/usr/bin/env bash

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=../scripts/lib/common.sh
source "$ROOT_DIR/scripts/lib/common.sh"

valid_refs=(
    "v02.08.02.60"
    "master"
    "feature/layout-test"
    "0123456789abcdef0123456789abcdef01234567"
)
invalid_refs=(
    ""
    "-main"
    "refs/../main"
    "main@{1}"
    "main;echo"
    "main branch"
    "main//nested"
    "main/"
)

for ref in "${valid_refs[@]}"; do
    validate_bambu_ref "$ref"
done

for ref in "${invalid_refs[@]}"; do
    if validate_bambu_ref "$ref" >/dev/null 2>&1; then
        echo "unsafe ref passed validation: $ref" >&2
        exit 1
    fi
done

[[ $(sanitize_cache_component 'macOS 15/ARM64') == "macOS-15-ARM64" ]]

python3 -m unittest discover -s "$ROOT_DIR/tests" -p 'test_*.py'

for script in "$ROOT_DIR"/scripts/*.sh "$ROOT_DIR"/scripts/lib/*.sh; do
    bash -n "$script"
done

echo "script tests passed"
