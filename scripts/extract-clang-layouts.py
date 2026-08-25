#!/usr/bin/env python3

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

"""Extract selected C++ record layouts from Clang's own ABI layout output."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


LAYOUT_MARKER = "*** Dumping AST Record Layout"
RECORD_RE = re.compile(r"^\s*0 \| (?:struct|class|union) (.+?)\s*$", re.MULTILINE)
SUMMARY_RE = re.compile(r"\[sizeof=(\d+),.*?align=(\d+),", re.DOTALL)
FIELD_RE = re.compile(r"^\s*(\d+)(?::\d+-\d+)? \|( +)(.+?)\s*$", re.MULTILINE)
NAME_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^]]*\])?\s*$")


def parse_layout_dump(output: str, requested: dict[str, list[str]]) -> dict[str, dict]:
    """Parse exact requested records and direct fields, failing on ambiguity."""
    found: dict[str, list[dict]] = {name: [] for name in requested}
    for section in output.split(LAYOUT_MARKER)[1:]:
        record_match = RECORD_RE.search(section)
        if not record_match:
            continue
        record = re.sub(r"\s+\((?:empty|anonymous[^)]*)\)$", "", record_match.group(1))
        if record not in requested:
            continue
        summary = SUMMARY_RE.search(section)
        if not summary:
            raise ValueError(f"missing size/alignment summary for {record}")

        fields: dict[str, int] = {}
        for match in FIELD_RE.finditer(section):
            if len(match.group(2)) != 3:
                continue
            description = match.group(3)
            if "(base)" in description or "vtable pointer" in description:
                continue
            name_match = NAME_RE.search(description)
            if name_match and name_match.group(1) in requested[record]:
                field = name_match.group(1)
                if field in fields:
                    raise ValueError(f"duplicate direct field {record}::{field}")
                fields[field] = int(match.group(1))

        missing = sorted(set(requested[record]) - fields.keys())
        if missing:
            raise ValueError(f"missing fields for {record}: {', '.join(missing)}")
        found[record].append({
            "size": int(summary.group(1)),
            "alignment": int(summary.group(2)),
            "members": fields,
        })

    result: dict[str, dict] = {}
    for record, candidates in found.items():
        if len(candidates) != 1:
            raise ValueError(f"expected exactly one layout for {record}, found {len(candidates)}")
        result[record] = candidates[0]
    return result


def build_probe(headers: list[str], records: list[dict]) -> str:
    lines = [f'#include "{header}"' for header in headers]
    lines.append("")
    for index, record in enumerate(records):
        lines.append(
            f"static_assert(sizeof({record['type']}) > 0, \"layout probe {index}\");"
        )
    return "\n".join(lines) + "\n"


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
    parser.add_argument(
        "--compiler-arg", action="append", default=[],
        help="additional compiler argument; repeat for multiple arguments",
    )
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    all_layouts: dict[str, dict] = {}
    invocations: list[dict] = []

    for unit in config["translation_units"]:
        requested = {item["type"]: list(item["members"].values()) for item in unit["records"]}
        probe = build_probe(unit["headers"], unit["records"])
        with tempfile.TemporaryDirectory(prefix="bambu-abi-layout-") as temp_dir:
            probe_path = Path(temp_dir) / "probe.cpp"
            probe_path.write_text(probe, encoding="utf-8")
            command = [
                args.compiler, "-std=c++20", "-fsyntax-only",
                "-Xclang", "-fdump-record-layouts",
                "-I", str(args.source_dir),
                *unit.get("compiler_args", []), *args.compiler_arg, str(probe_path),
            ]
            completed = subprocess.run(
                command, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, cwd=args.source_dir,
            )
        if completed.returncode:
            diagnostics = [
                line for line in completed.stdout.splitlines()
                if re.search(r"(?:fatal )?error:|warning:|note:", line)
            ]
            raise SystemExit(
                f"layout probe {unit['name']} failed ({completed.returncode})\n"
                + "\n".join(diagnostics[:40])
            )
        parsed = parse_layout_dump(completed.stdout, requested)
        for record in unit["records"]:
            logical_name = record["name"]
            if logical_name in all_layouts:
                raise SystemExit(f"duplicate logical layout name: {logical_name}")
            raw = parsed[record["type"]]
            all_layouts[logical_name] = {
                "cpp_type": record["type"],
                "size": raw["size"],
                "alignment": raw["alignment"],
                "members": {
                    logical: raw["members"][cpp_name]
                    for logical, cpp_name in record["members"].items()
                },
            }
        invocations.append({
            "name": unit["name"],
            "probe_sha256": hashlib.sha256(probe.encode()).hexdigest(),
            "arguments": command[1:-1],
        })

    document = {
        "schema_version": 1,
        "generator": "extract-clang-layouts.py",
        "compiler": compiler_version(args.compiler),
        "source_dir": str(args.source_dir.resolve()),
        "invocations": invocations,
        "layouts": all_layouts,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
