#!/usr/bin/env python3

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

"""Run record and vtable probes concurrently and emit one ABI values document."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def child_arguments(args: argparse.Namespace, script: Path, config: Path, output: Path) -> list[str]:
    command = [
        sys.executable, str(script),
        "--config", str(config),
        "--source-dir", str(args.source_dir),
        "--output", str(output),
        "--compiler", args.compiler,
        "--std", args.std,
    ]
    command.extend(f"--compiler-arg={value}" for value in args.compiler_arg)
    return command


def run_child(name: str, command: list[str]) -> tuple[str, float]:
    started = time.perf_counter()
    completed = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    elapsed = time.perf_counter() - started
    if completed.returncode:
        raise RuntimeError(
            f"{name} extraction failed ({completed.returncode})\n{completed.stdout}"
        )
    return completed.stdout, elapsed


def atomic_value(term: dict, layouts: dict, vtables: dict) -> int:
    if "layout" in term:
        layout = layouts[term["layout"]]
        if "member" in term:
            return layout["members"][term["member"]]
        if "base" in term:
            return layout["bases"][term["base"]]
        attribute = term.get("attribute")
        if attribute not in {"size", "alignment"}:
            raise ValueError(f"layout term requires member, base, size, or alignment: {term}")
        return layout[attribute]
    if "vtable" in term and "method" in term:
        return vtables[term["vtable"]]["indices"][term["method"]]
    raise ValueError(f"unknown ABI value term: {term}")


def derive_values(config: dict, layouts: dict, vtables: dict) -> dict[str, int]:
    values: dict[str, int] = {}
    for specification in config["values"]:
        name = specification["name"]
        if name in values:
            raise ValueError(f"duplicate ABI value name: {name}")
        terms = specification.get("sum", [specification])
        values[name] = sum(atomic_value(term, layouts, vtables) for term in terms)
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--layout-config", type=Path,
        default=ROOT / "config" / "bambustudio-layout-probes.json",
    )
    parser.add_argument(
        "--vtable-config", type=Path,
        default=ROOT / "config" / "bambustudio-vtable-probes.json",
    )
    parser.add_argument(
        "--values-config", type=Path,
        default=None,
    )
    parser.add_argument("--compiler", default=os.environ.get("CXX", "clang++"))
    parser.add_argument("--std", default="c++20")
    parser.add_argument("--compiler-arg", action="append", default=[])
    args = parser.parse_args()

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="bambu-abi-combined-") as temp_dir:
        temp = Path(temp_dir)
        layout_output = temp / "layouts.json"
        vtable_output = temp / "vtables.json"
        tasks = {
            "record_layouts": child_arguments(
                args, ROOT / "scripts" / "extract-clang-layouts.py",
                args.layout_config, layout_output,
            ),
            "vtable_layouts": child_arguments(
                args, ROOT / "scripts" / "extract-clang-vtables.py",
                args.vtable_config, vtable_output,
            ),
        }
        timings = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                name: executor.submit(run_child, name, command)
                for name, command in tasks.items()
            }
            for name, future in futures.items():
                _, timings[name] = future.result()
        layout_document = json.loads(layout_output.read_text(encoding="utf-8"))
        vtable_document = json.loads(vtable_output.read_text(encoding="utf-8"))

    layouts = layout_document["layouts"]
    vtables = vtable_document["vtables"]
    values = {}
    if args.values_config is not None:
        values_config = json.loads(args.values_config.read_text(encoding="utf-8"))
        values = derive_values(values_config, layouts, vtables)
    wall_seconds = time.perf_counter() - started
    document = {
        "schema_version": 1,
        "generator": "extract-bambustudio-abi.py",
        "compiler": layout_document["compiler"],
        "source_dir": str(args.source_dir.resolve()),
        "extraction": {
            "parallel": True,
            "wall_seconds": round(wall_seconds, 3),
            "task_seconds": {name: round(value, 3) for name, value in timings.items()},
            "layout_invocations": layout_document["invocations"],
            "vtable_invocations": vtable_document["invocations"],
        },
        "layouts": layouts,
        "vtables": vtables,
        "values": values,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(
        f"extracted {len(layouts)} records and {len(vtables)} vtables in {wall_seconds:.3f}s "
        f"(records {timings['record_layouts']:.3f}s, vtables {timings['vtable_layouts']:.3f}s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
