#!/usr/bin/env python3

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve a version requirements file, cloning the nearest earlier version if absent."""

import argparse
import json
import re
import shutil
from pathlib import Path


VERSION = re.compile(r"^\d+(?:\.\d+)+$")


def version_key(value: str) -> tuple[int, ...]:
    if not VERSION.fullmatch(value):
        raise ValueError(f"version must contain numeric dot-separated components: {value}")
    return tuple(map(int, value.split(".")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    requested = version_key(args.version)
    destination = args.root / args.version / "requirements.json"
    inherited_from = ""
    if not destination.exists():
        candidates = []
        for path in args.root.glob("*/requirements.json"):
            try:
                key = version_key(path.parent.name)
            except ValueError:
                continue
            if key < requested:
                candidates.append((key, path))
        if not candidates:
            raise SystemExit(f"no requirements exist for {args.version} and no earlier version can be inherited")
        source = max(candidates)[1]
        document = json.loads(source.read_text(encoding="utf-8"))
        inherited_from = source.parent.name
        document["version"] = args.version
        document["inherited_from"] = inherited_from
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for override in source.parent.glob("requirements.*.json"):
            shutil.copyfile(override, destination.parent / override.name)
        print(f"created {destination} from {source}")
    document = json.loads(destination.read_text(encoding="utf-8"))
    if document.get("kind") != "bambustudio_abi_requirements" or document.get("version") != args.version:
        raise SystemExit(f"invalid requirements document: {destination}")
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"path={destination}\n")
            output.write(f"inherited_from={inherited_from}\n")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
