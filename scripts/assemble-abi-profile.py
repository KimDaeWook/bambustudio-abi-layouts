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


def canonical_layouts(probe: dict, requirements: dict) -> dict:
    result = {}
    extracted = probe.get("layouts", {})
    for cpp_type, specification in requirements["layouts"].items():
        record = extracted[cpp_type]
        result[cpp_type] = {"size": record["size"], "alignment": record["alignment"],
            "members": {name: record["members"][name] for name in specification.get("members", [])},
            "bases": {name: record["bases"][name] for name in specification.get("bases", [])}}
    return result


def canonical_vtables(probe: dict, requirements: dict) -> dict:
    result = {}
    extracted = probe.get("vtables", {})
    for cpp_type, specification in requirements["vtables"].items():
        table = extracted[cpp_type]
        result[cpp_type] = {"methods": {name: table["indices"][name] for name in specification["methods"]}}
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
    requirements = load(args.requirements)
    target_requirements = requirements["targets"]["macos-arm64"]
    expected_symbols = len(target_requirements.get("symbols", {}))
    analysis = functions.get("analysis", {})
    if analysis.get("resolved") != expected_symbols or len(functions.get("symbols", {})) != expected_symbols:
        raise ValueError("function ABI extraction is incomplete")

    layouts = canonical_layouts(layout, target_requirements)
    vtables = canonical_vtables(layout, target_requirements)
    symbols = functions["symbols"]
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
        "layouts": layouts,
        "vtables": vtables,
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
                "record_count": len(layouts),
                "vtable_count": len(vtables),
                "symbol_count": len(symbols),
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
