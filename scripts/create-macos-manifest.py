#!/usr/bin/env python3

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
from typing import Iterable


UUID_RE = re.compile(r"^UUID: ([0-9A-Fa-f-]+) \(([^)]+)\) (.+)$")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_uuid_lines(lines: Iterable[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for raw_line in lines:
        line = raw_line.strip()
        match = UUID_RE.match(line)
        if not match:
            continue
        parsed.append(
            {
                "uuid": match.group(1).upper(),
                "architecture": match.group(2),
            }
        )
    return sorted(parsed, key=lambda item: (item["architecture"], item["uuid"]))


def dwarfdump_uuids(path: pathlib.Path) -> tuple[list[dict[str, str]], str]:
    result = subprocess.run(
        ["xcrun", "dwarfdump", "--uuid", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_uuid_lines(result.stdout.splitlines()), result.stdout


def require_debug_info(dwarf: pathlib.Path) -> None:
    result = subprocess.run(
        ["otool", "-l", str(dwarf)],
        check=True,
        capture_output=True,
        text=True,
    )
    if "sectname __debug_info" not in result.stdout:
        raise RuntimeError(f"dSYM has no __debug_info section: {dwarf}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=pathlib.Path, required=True)
    parser.add_argument("--dwarf", type=pathlib.Path, required=True)
    parser.add_argument("--source-dir", type=pathlib.Path, required=True)
    parser.add_argument("--requested-ref", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--deps-tree", required=True)
    parser.add_argument("--upstream-version", required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()

    require_debug_info(args.dwarf)
    binary_uuids, binary_uuid_text = dwarfdump_uuids(args.binary)
    dsym_uuids, dsym_uuid_text = dwarfdump_uuids(args.dwarf)
    if not binary_uuids or binary_uuids != dsym_uuids:
        raise RuntimeError(
            "binary and dSYM UUID sets differ: "
            f"binary={binary_uuids}, dSYM={dsym_uuids}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "binary-uuids.txt").write_text(binary_uuid_text, encoding="utf-8")
    (args.output_dir / "dsym-uuids.txt").write_text(dsym_uuid_text, encoding="utf-8")

    contract_paths = [
        pathlib.Path("BuildMac.sh"),
        pathlib.Path(".github/workflows/build_all.yml"),
        pathlib.Path(".github/workflows/build_bambu.yml"),
        pathlib.Path(".github/workflows/build_deps.yml"),
    ]
    build_contract = [
        {
            "path": str(relative_path),
            "sha256": sha256(args.source_dir / relative_path),
        }
        for relative_path in contract_paths
    ]

    manifest = {
        "schema_version": 1,
        "kind": "bambustudio.macos.rebuilt-dsym",
        "source": {
            "repository": "https://github.com/bambulab/BambuStudio.git",
            "requested_ref": args.requested_ref,
            "commit": args.commit,
            "deps_tree": args.deps_tree,
            "upstream_version": args.upstream_version,
        },
        "build": {
            "configuration": "Release",
            "generator": "Ninja",
            "architecture": "arm64",
            "deployment_target": "10.15",
            "debug_flags": ["-g", "-fstandalone-debug"],
            "upstream_workflow_deviation": {
                "field": "BuildMac.sh architecture",
                "upstream": "universal",
                "selected": "arm64",
                "reason": "Stage 1 targets Apple Silicon ABI layouts only",
            },
            "upstream_contract_files": build_contract,
            "runner": {
                "os": os.environ.get("RUNNER_OS", "unknown"),
                "architecture": os.environ.get("RUNNER_ARCH", "unknown"),
                "image_os": os.environ.get("ImageOS", "unknown"),
                "image_version": os.environ.get("ImageVersion", "unknown"),
            },
        },
        "binary": {
            "name": "BambuStudio.app/Contents/MacOS/BambuStudio",
            "sha256": sha256(args.binary),
            "uuids": binary_uuids,
        },
        "dsym": {
            "name": "BambuStudio.app.dSYM",
            "dwarf_sha256": sha256(args.dwarf),
            "uuids": dsym_uuids,
            "release_binary_symbolication_compatible": False,
        },
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
