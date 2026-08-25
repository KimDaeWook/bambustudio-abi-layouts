#!/usr/bin/env bash

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

validate_bambu_ref() {
    local value=${1:-}

    if [[ -z "$value" || ${#value} -gt 128 ]]; then
        echo "bambu_ref must contain between 1 and 128 characters" >&2
        return 1
    fi
    if [[ ! "$value" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]]; then
        echo "bambu_ref contains unsupported characters: $value" >&2
        return 1
    fi
    if [[ "$value" == *".."* || "$value" == *"@{"* || "$value" == */ || "$value" == *//* ]]; then
        echo "bambu_ref is not a safe Git ref: $value" >&2
        return 1
    fi
}

sanitize_cache_component() {
    local value=${1:-unknown}
    value=${value//[^A-Za-z0-9._-]/-}
    printf '%s\n' "${value:-unknown}"
}
