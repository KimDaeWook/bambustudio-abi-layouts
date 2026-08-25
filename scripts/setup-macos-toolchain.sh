#!/usr/bin/env bash

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly MODE=${1:?usage: setup-macos-toolchain.sh <deps|app>}
readonly CMAKE_VERSION=3.31.0
readonly TAP_NAME="${USER}/bambustudio-abi-layouts-cmake"

case "$MODE" in
    deps)
        brew install automake texinfo nasm yasm x264
        brew uninstall --ignore-dependencies zstd || true
        ;;
    app)
        brew install automake texinfo
        ;;
    *)
        echo "unsupported setup mode: $MODE" >&2
        exit 1
        ;;
esac

brew unlink cmake || true
if ! brew list --versions "${TAP_NAME}/cmake@${CMAKE_VERSION}" >/dev/null 2>&1; then
    brew tap-new "$TAP_NAME"
    brew extract --version="$CMAKE_VERSION" cmake "$TAP_NAME"
    brew install "${TAP_NAME}/cmake@${CMAKE_VERSION}"
fi
brew link --overwrite "cmake@${CMAKE_VERSION}"
brew pin "cmake@${CMAKE_VERSION}"

cmake_version=$(cmake --version | sed -n '1s/^cmake version //p')
if [[ "$cmake_version" != "$CMAKE_VERSION" ]]; then
    echo "expected CMake $CMAKE_VERSION, found $cmake_version" >&2
    exit 1
fi
