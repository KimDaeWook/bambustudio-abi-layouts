#!/usr/bin/env python3

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

"""Extract selected Itanium virtual-function indices from Clang output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


def parse_vtable_indices(output: str, cpp_type: str, methods: dict[str, str]) -> dict[str, int]:
    marker = f"VTable indices for '{cpp_type}'"
    sections = output.split(marker)
    if len(sections) != 2:
        raise ValueError(f"expected exactly one vtable index block for {cpp_type}")
    block = sections[1].split("\n\n", 1)[0]
    entries = []
    for line in block.splitlines():
        match = re.match(r"^\s*(\d+) \| (.+)$", line)
        if match:
            entries.append((int(match.group(1)), match.group(2)))

    result = {}
    for logical_name, signature_fragment in methods.items():
        candidates = [index for index, signature in entries if signature_fragment in signature]
        if len(candidates) != 1:
            raise ValueError(
                f"expected one vtable entry for {cpp_type}::{logical_name}, found {len(candidates)}"
            )
        result[logical_name] = candidates[0]
    return result


def compiler_version(compiler: str) -> str:
    return subprocess.run(
        [compiler, "--version"], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--compiler", default=os.environ.get("CXX", "clang++"))
    parser.add_argument("--std", default="c++20")
    parser.add_argument("--compiler-arg", action="append", default=[])
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    results = {}
    invocations = []
    for unit in config["translation_units"]:
        source = "\n".join(f'#include "{header}"' for header in unit["headers"])
        source += "\n\n" + unit["probe_code"] + "\n"
        with tempfile.TemporaryDirectory(prefix="bambu-abi-vtable-") as temp_dir:
            source_path = Path(temp_dir) / "probe.cpp"
            object_path = Path(temp_dir) / "probe.o"
            source_path.write_text(source, encoding="utf-8")
            command = [
                args.compiler, "-w", f"-std={args.std}", "-c",
                "-Xclang", "-fdump-vtable-layouts", "-I", str(args.source_dir),
                *unit.get("compiler_args", []), *args.compiler_arg,
                str(source_path), "-o", str(object_path),
            ]
            completed = subprocess.run(
                command, cwd=args.source_dir, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        if completed.returncode:
            raise SystemExit(f"vtable probe {unit['name']} failed\n{completed.stdout}")
        for record in unit["records"]:
            results[record["name"]] = {
                "cpp_type": record["type"],
                "indices": parse_vtable_indices(
                    completed.stdout, record.get("dump_type", record["type"]), record["methods"]
                ),
            }
        invocations.append({
            "name": unit["name"],
            "probe_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "arguments": command[1:-3],
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({
        "schema_version": 1,
        "generator": "extract-clang-vtables.py",
        "compiler": compiler_version(args.compiler),
        "source_dir": str(args.source_dir.resolve()),
        "invocations": invocations,
        "vtables": results,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
