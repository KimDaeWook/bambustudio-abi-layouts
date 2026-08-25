#!/usr/bin/env python3

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

"""Materialize one target's versioned requirements for existing focused extractors."""

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    document = json.loads(args.requirements.read_text(encoding="utf-8"))
    try:
        target = document["targets"][args.target]
        outputs = {
            "records.json": target["layout"]["records"],
            "vtables.json": target["layout"]["vtables"],
            "functions.json": target["functions"],
        }
    except (KeyError, TypeError) as error:
        raise SystemExit(f"requirements target is incomplete: {error}") from error
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in outputs.items():
        (args.output_dir / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    count = sum(len(unit.get("records", [])) for unit in outputs["records.json"].get("translation_units", []))
    symbols = len(outputs["functions.json"].get("symbols", []))
    print(f"materialized {args.target}: {count} layout values, {symbols} function symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
