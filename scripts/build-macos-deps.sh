#!/usr/bin/env bash

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly SOURCE_DIR=${1:?usage: build-macos-deps.sh <BambuStudio-source>}

cd "$SOURCE_DIR"
./BuildMac.sh -d -x -a universal -t 10.15 -1

# Match the upstream workflow: retain only the installed dependency prefix.
for arch in arm64 x86_64; do
    build_dir="$SOURCE_DIR/deps/build/$arch"
    if [[ ! -d "$build_dir/BambuStudio_deps" ]]; then
        echo "dependency prefix was not produced for $arch" >&2
        exit 1
    fi
    find "$build_dir" -mindepth 1 -maxdepth 1 ! -name BambuStudio_deps -exec rm -rf -- {} +
done

brew install zstd
