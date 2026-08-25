#!/usr/bin/env bash

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly SOURCE_DIR=${1:?usage: extract-macos-abi.sh <BambuStudio-source> <dependency-prefix> <output-json>}
readonly DEPENDENCY_PREFIX=${2:?usage: extract-macos-abi.sh <BambuStudio-source> <dependency-prefix> <output-json>}
readonly OUTPUT_JSON=${3:?usage: extract-macos-abi.sh <BambuStudio-source> <dependency-prefix> <output-json>}
readonly SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
readonly TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/bambu-abi-generated.XXXXXX")
trap 'rm -rf -- "$TEMP_DIR"' EXIT

if [[ ! -d "$SOURCE_DIR/src" ]]; then
    echo "BambuStudio source directory is incomplete: $SOURCE_DIR" >&2
    exit 1
fi
if [[ ! -d "$DEPENDENCY_PREFIX/include" ]]; then
    echo "dependency include prefix is missing: $DEPENDENCY_PREFIX/include" >&2
    exit 1
fi

version=$(sed -n 's/^[[:space:]]*set(SLIC3R_VERSION[[:space:]]*"\([^"]*\)".*/\1/p' "$SOURCE_DIR/version.inc" | head -n 1)
commit=$(git -C "$SOURCE_DIR" rev-parse HEAD)
cat >"$TEMP_DIR/libslic3r_version.h" <<EOF
#ifndef __SLIC3R_VERSION_H
#define __SLIC3R_VERSION_H
#define SLIC3R_APP_NAME "BambuStudio"
#define SLIC3R_APP_KEY "BambuStudio"
#define SLIC3R_VERSION "$version"
#define SLIC3R_BUILD_ID "v$version"
#define SLIC3R_BUILD_TIME "abi-layout-probe"
#define SLIC3R_COMPILE_VERSION "$commit"
#define BBL_RELEASE_TO_PUBLIC 1
#define BBL_INTERNAL_TESTING 0
#endif
EOF

compiler_args=(
    -w
    -arch arm64
    -mmacosx-version-min=10.15
    -D__WXOSX_COCOA__
    -D__WXMAC__
    -D__WXOSX__
    -pthread
    -I"$TEMP_DIR"
    -I"$DEPENDENCY_PREFIX/include"
    -I"$SOURCE_DIR/src"
    -I"$SOURCE_DIR/src/eigen"
    -I"$SOURCE_DIR/src/admesh"
    -I"$SOURCE_DIR/src/hidapi/include"
    -I"$SOURCE_DIR/src/miniz"
    -I"$SOURCE_DIR/src/slic3r/GUI"
    -I"$SOURCE_DIR/src/slic3r/Utils"
)

for include_dir in \
    "$DEPENDENCY_PREFIX/include/opencv4" \
    "$DEPENDENCY_PREFIX/include/opencascade"; do
    if [[ -d "$include_dir" ]]; then
        compiler_args+=( -I"$include_dir" )
    fi
done

wx_public_count=0
for include_dir in "$DEPENDENCY_PREFIX"/include/wx-*; do
    [[ -d "$include_dir/wx" ]] || continue
    compiler_args+=( -I"$include_dir" )
    wx_public_count=$((wx_public_count + 1))
done
if [[ $wx_public_count -ne 1 ]]; then
    echo "expected exactly one wxWidgets public include directory, found $wx_public_count" >&2
    exit 1
fi

if [[ -d "$DEPENDENCY_PREFIX/lib/wx/include" ]]; then
    wx_config_count=0
    for include_dir in "$DEPENDENCY_PREFIX"/lib/wx/include/*; do
        [[ -d "$include_dir" ]] || continue
        compiler_args+=( -I"$include_dir" )
        wx_config_count=$((wx_config_count + 1))
    done
    if [[ $wx_config_count -ne 1 ]]; then
        echo "expected exactly one wxWidgets generated include directory, found $wx_config_count" >&2
        exit 1
    fi
else
    echo "wxWidgets generated include root is missing" >&2
    exit 1
fi

command=(
    python3 "$SCRIPT_DIR/extract-bambustudio-abi.py"
    --source-dir "$SOURCE_DIR"
    --output "$OUTPUT_JSON"
    --compiler "$(xcrun --find clang++)"
    --std c++17
)
for argument in "${compiler_args[@]}"; do
    command+=( "--compiler-arg=$argument" )
done

"${command[@]}"

python3 - "$OUTPUT_JSON" <<'PY'
import json
import sys

path = sys.argv[1]
document = json.load(open(path, encoding="utf-8"))
values = document.get("values", {})
if len(values) != 34:
    raise SystemExit(f"expected 34 ABI values, found {len(values)}")
print(f"validated {len(values)} ABI values")
PY
