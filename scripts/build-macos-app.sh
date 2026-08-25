#!/usr/bin/env bash

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly SOURCE_DIR=${1:?usage: build-macos-app.sh <BambuStudio-source>}

# Preserve the upstream Release configuration while asking Clang to emit complete
# standalone type information. CMake appends its normal Release flags after these.
export CFLAGS="${CFLAGS:+$CFLAGS }-g -fstandalone-debug"
export CXXFLAGS="${CXXFLAGS:+$CXXFLAGS }-g -fstandalone-debug"

cd "$SOURCE_DIR"
./BuildMac.sh -s -x -a arm64 -t 10.15 -1

readonly APP="$SOURCE_DIR/build/arm64/BambuStudio/BambuStudio.app"
readonly BINARY="$APP/Contents/MacOS/BambuStudio"

if [[ ! -x "$BINARY" ]]; then
    echo "BambuStudio executable was not produced at $BINARY" >&2
    exit 1
fi
