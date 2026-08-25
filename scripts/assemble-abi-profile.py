#!/usr/bin/env python3

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

"""Merge independently extracted layout and function ABI into a runtime profile."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def canonical(document: dict) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def nested_layouts(values: dict[str, int], bindings: list[dict]) -> dict[str, dict[str, dict]]:
    result: dict[str, dict[str, dict]] = {}
    by_name = {item["name"]: item for item in bindings}
    if len(by_name) != len(bindings) or set(by_name) != set(values):
        raise ValueError("layout bindings must match extracted values exactly")
    for dotted, value in sorted(values.items()):
        group, separator, member = dotted.partition(".")
        if not separator or "." in member or not isinstance(value, int) or value < 0:
            raise ValueError(f"invalid layout value: {dotted}")
        descriptor = {key: item for key, item in by_name[dotted].items() if key != "name"}
        result.setdefault(group, {})[member] = {"value": value, **descriptor}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--functions", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--project-commit", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-run-url", required=True)
    args = parser.parse_args()

    layout = load(args.layout)
    functions = load(args.functions)
    layout_upstream = layout.get("upstream", {})
    function_upstream = functions.get("upstream", {})
    version = layout_upstream.get("version")
    architecture = functions.get("architecture")
    if not version or version != function_upstream.get("version"):
        raise ValueError("layout and function ABI versions differ")
    if architecture != "arm64" or functions.get("platform") != "macos":
        raise ValueError("only the validated macos-arm64 profile target is supported")
    if layout_upstream.get("commit") != function_upstream.get("source_commit"):
        raise ValueError("layout source commit and release source commit differ")
    values = layout.get("values", {})
    requirements = load(args.requirements)
    target_requirements = requirements["targets"]["macos-arm64"]
    expected_layouts = len(target_requirements["layout"]["values"].get("values", []))
    expected_symbols = len(target_requirements["functions"].get("symbols", []))
    if len(values) != expected_layouts:
        raise ValueError(f"expected {expected_layouts} layout values, found {len(values)}")
    analysis = functions.get("analysis", {})
    if analysis.get("resolved") != expected_symbols or len(functions.get("symbols", [])) != expected_symbols:
        raise ValueError("function ABI extraction is incomplete")

    layouts = nested_layouts(values, target_requirements["layout"]["bindings"])
    for group, metadata in target_requirements.get("profile_metadata", {}).items():
        layouts.setdefault(group, {}).update(metadata)
    symbols = [
        item
        for item in functions["symbols"]
    ]
    raw_events = functions["events"]
    profile = {
        "schema_version": 1,
        "kind": "studio_generated_profile",
        "status": "generated_complete",
        "id": f"macos-{version}-arm64-{functions['binary']['sha256'][:12]}",
        "platform": "macos",
        "architecture": architecture,
        "binary": {
            "sha256": functions["binary"]["sha256"],
            "uuid": functions["binary"]["uuid"],
        },
        "release": {
            "tag": function_upstream["release_tag"],
            "source_commit_sha": function_upstream["source_commit"],
            "asset": function_upstream["release_asset"],
        },
        "symbols": symbols,
        "event_bindings": raw_events["entries"],
        "layouts": layouts,
    }
    version_dir = args.output_root / version
    version_dir.mkdir(parents=True, exist_ok=True)
    profile_path = version_dir / "macos-arm64.json"
    profile_content = canonical(profile)
    profile_path.write_bytes(profile_content)
    catalogs = {}
    root = Path(__file__).resolve().parents[1]
    catalogs["requirements.json"] = file_sha256(args.requirements)
    manifest = {
        "schema_version": 1,
        "kind": "bambustudio_abi_profile_manifest",
        "version": version,
        "upstream": {
            "repository": function_upstream["repository"],
            "commit": function_upstream["source_commit"],
            "deps_tree": layout_upstream["deps_tree"],
            "release_tag": function_upstream["release_tag"],
        },
        "targets": {
            "macos-arm64": {
                "file": profile_path.name,
                "sha256": sha256(profile_content),
                "binary_sha256": functions["binary"]["sha256"],
                "binary_uuid": functions["binary"]["uuid"],
                "layout_value_count": len(values),
                "symbol_count": len(symbols),
                "event_binding_count": len(raw_events["entries"]),
                "catalog_sha256": catalogs,
                "generator_commit": args.project_commit,
                "workflow": {"run_id": args.workflow_run_id, "url": args.workflow_run_url},
            }
        },
    }
    (version_dir / "manifest.json").write_bytes(canonical(manifest))
    print(f"assembled complete profile: {profile_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
