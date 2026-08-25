#!/usr/bin/env bash

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

tag=${1:?release tag is required}
output_dir=${2:?output directory is required}
mkdir -p "$output_dir"

asset=$(gh release view "$tag" --repo bambulab/BambuStudio --json assets \
  --jq '[.assets[].name | select(test("^Bambu_Studio_mac-.*\\.dmg$"))] | if length == 1 then .[0] else error("expected exactly one macOS DMG") end')
if [[ ! -f "$output_dir/$asset" ]]; then
  gh release download "$tag" --repo bambulab/BambuStudio --pattern "$asset" --dir "$output_dir"
fi
printf '%s\n' "$asset"
