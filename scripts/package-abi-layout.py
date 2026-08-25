#!/usr/bin/env python3

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

"""Package a verbose probe result as a runtime layout and provenance manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$")
TARGET_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9_]+)*$")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def file_signature(path: Path) -> dict[str, str]:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha256_bytes(path.read_bytes())}


def nested_values(values: dict[str, int]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for dotted_name, value in sorted(values.items()):
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"ABI value must be a non-negative integer: {dotted_name}")
        group, separator, name = dotted_name.partition(".")
        if not separator or not group or not name or "." in name:
            raise ValueError(f"ABI value name must contain one group separator: {dotted_name}")
        result.setdefault(group, {})[name] = value
    return result


def write_json(path: Path, document: dict) -> str:
    content = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    return sha256_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--project-commit", required=True)
    parser.add_argument("--extractor-commit")
    parser.add_argument("--workflow-run-id")
    parser.add_argument("--workflow-run-url")
    args = parser.parse_args()

    target = f"{args.platform}-{args.architecture}"
    if not TARGET_RE.fullmatch(target):
        raise SystemExit(f"invalid platform target: {target}")

    probe = json.loads(args.input.read_text(encoding="utf-8"))
    upstream = probe.get("upstream", {})
    version = upstream.get("version", "")
    if not VERSION_RE.fullmatch(version):
        raise SystemExit(f"invalid or missing upstream version: {version!r}")
    values = probe.get("values", {})
    if len(values) != 34:
        raise SystemExit(f"expected 34 ABI values, found {len(values)}")

    version_dir = args.output_root / version
    layout_path = version_dir / f"{target}.json"
    layout_sha256 = write_json(layout_path, nested_values(values))
    manifest_path = version_dir / "manifest.json"

    manifest = {
        "schema_version": 1,
        "kind": "bambustudio_abi_layout_manifest",
        "version": version,
        "upstream": upstream,
        "targets": {},
    }
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key in ("schema_version", "kind", "version", "upstream"):
            if existing.get(key) != manifest[key]:
                raise SystemExit(f"existing manifest has incompatible {key}")
        manifest = existing
        manifest.pop("catalogs", None)

    extraction = probe.get("extraction", {})
    invocation = (extraction.get("layout_invocations") or [{}])[0]
    target_manifest = {
        "file": layout_path.name,
        "sha256": layout_sha256,
        "value_count": len(values),
        "compiler": probe.get("compiler", ""),
        "runner": probe.get("runner", {}),
        "source_slice": invocation.get("source_slice", {}),
        "catalogs": {
            "values": file_signature(ROOT / "config" / "bambustudio-abi-values.json"),
            "record_probes": file_signature(ROOT / "config" / "bambustudio-layout-probes.json"),
            "vtable_probes": file_signature(ROOT / "config" / "bambustudio-vtable-probes.json"),
        },
        "generator": {
            "extractor": "scripts/extract-bambustudio-abi.py",
            "extractor_commit": args.extractor_commit or args.project_commit,
            "packager": "scripts/package-abi-layout.py",
            "packager_commit": args.project_commit,
        },
    }
    if args.workflow_run_id or args.workflow_run_url:
        target_manifest["workflow"] = {
            "run_id": args.workflow_run_id or "",
            "url": args.workflow_run_url or "",
        }
    manifest.setdefault("targets", {})[target] = target_manifest
    write_json(manifest_path, manifest)
    print(f"packaged {len(values)} values at {layout_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
