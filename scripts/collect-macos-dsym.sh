#!/usr/bin/env bash

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
readonly SOURCE_DIR=${1:?usage: collect-macos-dsym.sh <BambuStudio-source> <output-dir>}
readonly OUTPUT_DIR=${2:?usage: collect-macos-dsym.sh <BambuStudio-source> <output-dir>}
readonly BINARY="$SOURCE_DIR/build/arm64/BambuStudio/BambuStudio.app/Contents/MacOS/BambuStudio"
readonly DSYM="$OUTPUT_DIR/BambuStudio.app.dSYM"
readonly DWARF="$DSYM/Contents/Resources/DWARF/BambuStudio"

: "${BAMBU_REF:?BAMBU_REF is required}"
: "${BAMBU_COMMIT:?BAMBU_COMMIT is required}"
: "${BAMBU_DEPS_TREE:?BAMBU_DEPS_TREE is required}"
: "${BAMBU_VERSION:?BAMBU_VERSION is required}"

if [[ ! -x "$BINARY" ]]; then
    echo "BambuStudio executable does not exist: $BINARY" >&2
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
xcrun dsymutil "$BINARY" -o "$DSYM"
cp "$SOURCE_DIR/LICENSE" "$OUTPUT_DIR/BambuStudio-LICENSE"

if [[ ! -s "$DWARF" ]]; then
    echo "dsymutil did not produce the expected DWARF file: $DWARF" >&2
    exit 1
fi

{
    printf 'requested_ref=%s\n' "$BAMBU_REF"
    printf 'commit=%s\n' "$BAMBU_COMMIT"
    printf 'deps_tree=%s\n' "$BAMBU_DEPS_TREE"
    printf 'upstream_version=%s\n' "$BAMBU_VERSION"
    printf 'runner_os=%s\n' "${RUNNER_OS:-unknown}"
    printf 'runner_arch=%s\n' "${RUNNER_ARCH:-unknown}"
    printf 'image_os=%s\n' "${ImageOS:-unknown}"
    printf 'image_version=%s\n' "${ImageVersion:-unknown}"
    printf 'configuration=Release\n'
    printf 'generator=Ninja\n'
    printf 'architectures=arm64\n'
    printf 'deployment_target=10.15\n'
    printf 'debug_flags=-g -fstandalone-debug\n'
    printf '\n[sw_vers]\n'
    sw_vers
    printf '\n[uname]\n'
    uname -a
    printf '\n[xcode]\n'
    xcodebuild -version
    printf '\n[sdk]\n'
    xcrun --sdk macosx --show-sdk-path
    xcrun --sdk macosx --show-sdk-version
    printf '\n[clang]\n'
    xcrun clang --version
    printf '\n[cmake]\n'
    cmake --version
    printf '\n[ninja]\n'
    ninja --version
} >"$OUTPUT_DIR/toolchain.txt"

python3 "$SCRIPT_DIR/create-macos-manifest.py" \
    --binary "$BINARY" \
    --dwarf "$DWARF" \
    --source-dir "$SOURCE_DIR" \
    --requested-ref "$BAMBU_REF" \
    --commit "$BAMBU_COMMIT" \
    --deps-tree "$BAMBU_DEPS_TREE" \
    --upstream-version "$BAMBU_VERSION" \
    --output-dir "$OUTPUT_DIR"
