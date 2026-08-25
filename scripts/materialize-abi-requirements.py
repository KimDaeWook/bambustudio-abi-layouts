#!/usr/bin/env python3

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

"""Merge common/platform requirements and materialize focused extractor inputs."""

import argparse
import json
from pathlib import Path


def merge(base, override):
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for key, value in override.items():
            result[key] = merge(result[key], value) if key in result else value
        return result
    return override


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    document = json.loads(args.requirements.read_text(encoding="utf-8"))
    platform_path = args.requirements.with_name(f"requirements.{args.target}.json")
    if platform_path.exists():
        document = merge(document, json.loads(platform_path.read_text(encoding="utf-8")))
    try:
        record_probe = document["record_probe"]
        records = []
        for cpp_type, layout in document["layouts"].items():
            records.append({
                "name": cpp_type,
                "type": cpp_type,
                "members": {name: name for name in layout.get("members", [])},
                "bases": {name: name for name in layout.get("bases", [])},
            })
        vtable_probe = document["vtable_probe"]
        vtable_records = []
        for cpp_type, table in document["vtables"].items():
            vtable_records.append({
                "name": cpp_type,
                "type": cpp_type,
                "dump_type": table["dump_type"],
                "methods": table["methods"],
            })
        outputs = {
            "records.json": {"schema_version": 1, "translation_units": [{**record_probe, "name": "version-records", "records": records}]},
            "vtables.json": {"schema_version": 1, "translation_units": [{**vtable_probe, "name": "version-vtables", "records": vtable_records}]},
            "functions.json": {
                "schema_version": 1,
                "symbols": document["symbols"],
                "symbol_overrides": document.get("symbol_overrides", {}),
            },
        }
    except (KeyError, TypeError) as error:
        raise SystemExit(f"requirements target is incomplete: {error}") from error
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in outputs.items():
        (args.output_dir / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    count = sum(len(unit.get("records", [])) for unit in outputs["records.json"].get("translation_units", []))
    symbols = len(outputs["functions.json"].get("symbols", {}))
    print(f"materialized {args.target}: {count} layout values, {symbols} function symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
