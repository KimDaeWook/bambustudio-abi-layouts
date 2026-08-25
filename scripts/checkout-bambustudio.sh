#!/usr/bin/env bash

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

readonly UPSTREAM_URL="https://github.com/bambulab/BambuStudio.git"
readonly BAMBU_REF=${1:?usage: checkout-bambustudio.sh <ref-or-commit> <destination>}
readonly DESTINATION=${2:?usage: checkout-bambustudio.sh <ref-or-commit> <destination>}

validate_bambu_ref "$BAMBU_REF"

if [[ -e "$DESTINATION" ]]; then
    echo "destination already exists: $DESTINATION" >&2
    exit 1
fi

mkdir -p "$(dirname -- "$DESTINATION")"
git init --quiet "$DESTINATION"
git -C "$DESTINATION" remote add origin "$UPSTREAM_URL"

export GIT_LFS_SKIP_SMUDGE=1

if [[ "$BAMBU_REF" =~ ^[0-9A-Fa-f]{40}$ ]]; then
    git -C "$DESTINATION" fetch --no-tags --depth=1 origin "$BAMBU_REF"
else
    tag_ref="refs/tags/$BAMBU_REF"
    branch_ref="refs/heads/$BAMBU_REF"

    if git -C "$DESTINATION" ls-remote --exit-code --refs origin "$tag_ref" >/dev/null 2>&1; then
        git -C "$DESTINATION" fetch --no-tags --depth=1 origin "$tag_ref"
    elif git -C "$DESTINATION" ls-remote --exit-code --refs origin "$branch_ref" >/dev/null 2>&1; then
        git -C "$DESTINATION" fetch --no-tags --depth=1 origin "$branch_ref"
    else
        echo "ref does not exist in $UPSTREAM_URL: $BAMBU_REF" >&2
        exit 1
    fi
fi

git -C "$DESTINATION" checkout --quiet --detach FETCH_HEAD
commit=$(git -C "$DESTINATION" rev-parse HEAD)
deps_tree=$(git -C "$DESTINATION" rev-parse "$commit:deps")
version=$(sed -n 's/^[[:space:]]*set(SLIC3R_VERSION[[:space:]]*"\([^"]*\)".*/\1/p' "$DESTINATION/version.inc" | head -n 1)

if [[ ! "$version" =~ ^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$ ]]; then
    echo "upstream version.inc contains an unsupported version value" >&2
    exit 1
fi

if [[ ${BAMBU_REQUIRE_GIT_LFS:-0} == 1 ]]; then
    git -C "$DESTINATION" lfs install --local
    git -C "$DESTINATION" lfs pull
fi

if [[ ${BAMBU_SKIP_SUBMODULES:-0} != 1 ]]; then
    git -C "$DESTINATION" submodule update --init --recursive --depth=1
fi

printf 'Resolved BambuStudio %s to %s (deps tree %s)\n' "$BAMBU_REF" "$commit" "$deps_tree"

if [[ -n ${GITHUB_OUTPUT:-} ]]; then
    {
        printf 'commit=%s\n' "$commit"
        printf 'short_commit=%s\n' "${commit:0:12}"
        printf 'deps_tree=%s\n' "$deps_tree"
        printf 'version=%s\n' "$version"
    } >>"$GITHUB_OUTPUT"
fi
