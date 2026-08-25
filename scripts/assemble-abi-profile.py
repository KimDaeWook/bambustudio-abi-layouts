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


def nested_layouts(values: dict[str, int]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for dotted, value in sorted(values.items()):
        group, separator, member = dotted.partition(".")
        if not separator or "." in member or not isinstance(value, int) or value < 0:
            raise ValueError(f"invalid layout value: {dotted}")
        result.setdefault(group, {})[member] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout", required=True, type=Path)
    parser.add_argument("--functions", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
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
    if len(values) != 34:
        raise ValueError(f"expected 34 layout values, found {len(values)}")
    analysis = functions.get("analysis", {})
    if analysis.get("resolved") != analysis.get("reviewed") or not functions.get("symbols"):
        raise ValueError("function ABI extraction is incomplete")

    layouts = nested_layouts(values)
    address_map = lambda value: {architecture: value}
    symbols = [
        {**{k: v for k, v in item.items() if k != "address"}, "addresses": address_map(item["address"])}
        for item in functions["symbols"]
    ]
    raw_events = functions["events"]
    events = {
        "add_filter_symbol": raw_events["add_filter_symbol"],
        "remove_filter_symbol": raw_events["remove_filter_symbol"],
        "add_filter_addresses": address_map(raw_events["add_filter_address"]),
        "remove_filter_addresses": address_map(raw_events["remove_filter_address"]),
        "expected_counts": {architecture: len(raw_events["entries"])},
        "event_type_offset": layouts["events"]["event_type_offset"],
        "filter_next_offset": layouts["events"]["filter_next_offset"],
        "event_object_offset": layouts["events"]["event_object_offset"],
        "entries": [
            {**{k: v for k, v in item.items() if k != "address"}, "addresses": address_map(item["address"])}
            for item in raw_events["entries"]
        ],
    }
    profile = {
        "schema_version": 1,
        "kind": "studio_generated_profile",
        "status": "generated_complete",
        "id": f"macos-{version}-arm64-{functions['binary']['sha256'][:12]}",
        "platform": "macos",
        "architecture": architecture,
        "binary": {
            "sha256": functions["binary"]["sha256"],
            "uuids": {architecture: functions["binary"]["uuid"]},
        },
        "release": {
            "tag": function_upstream["release_tag"],
            "source_commit_sha": function_upstream["source_commit"],
            "asset": function_upstream["release_asset"],
        },
        "symbols": symbols,
        "events": events,
        "layouts": layouts,
    }
    version_dir = args.output_root / version
    version_dir.mkdir(parents=True, exist_ok=True)
    profile_path = version_dir / "macos-arm64.json"
    profile_content = canonical(profile)
    profile_path.write_bytes(profile_content)
    catalogs = {}
    root = Path(__file__).resolve().parents[1]
    for name in ("bambustudio-function-abi.json", "bambustudio-abi-values.json", "bambustudio-layout-probes.json", "bambustudio-vtable-probes.json"):
        path = root / "config" / name
        catalogs[name] = file_sha256(path)
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
                "event_count": len(events["entries"]),
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
