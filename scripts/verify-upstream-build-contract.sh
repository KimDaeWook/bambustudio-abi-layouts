#!/usr/bin/env bash

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly SOURCE_DIR=${1:?usage: verify-upstream-build-contract.sh <BambuStudio-source>}

require_literal() {
    local file=$1
    local literal=$2
    if ! grep -F -- "$literal" "$SOURCE_DIR/$file" >/dev/null; then
        echo "unsupported upstream build contract: $file does not contain: $literal" >&2
        exit 1
    fi
}

required_files=(
    BuildMac.sh
    LICENSE
    .github/workflows/build_all.yml
    .github/workflows/build_bambu.yml
    .github/workflows/build_deps.yml
)

for file in "${required_files[@]}"; do
    if [[ ! -f "$SOURCE_DIR/$file" ]]; then
        echo "unsupported upstream build contract: missing $file" >&2
        exit 1
    fi
done

require_literal .github/workflows/build_all.yml "os: macos-15"
require_literal .github/workflows/build_bambu.yml "brew extract --version=3.31.0 cmake"
require_literal .github/workflows/build_bambu.yml "./BuildMac.sh -s -x -a universal -t 10.15 -1"
require_literal .github/workflows/build_deps.yml "brew extract --version=3.31.0 cmake"
require_literal .github/workflows/build_deps.yml "./BuildMac.sh -d -x -a universal -t 10.15 -1"
require_literal BuildMac.sh '-DCMAKE_BUILD_TYPE="$BUILD_CONFIG"'
require_literal BuildMac.sh '-DCMAKE_OSX_ARCHITECTURES="${_ARCH}"'
require_literal BuildMac.sh '-DCMAKE_OSX_DEPLOYMENT_TARGET="${OSX_DEPLOYMENT_TARGET}"'

echo "upstream macOS build contract is supported"
