#!/usr/bin/env python3

# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

"""Extract reviewed function/event symbol VM addresses from a release Mach-O."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import uuid
from pathlib import Path


CPU_NAMES = {0x0100000C: "arm64", 0x01000007: "x86_64"}
LC_SYMTAB = 0x2
LC_UUID = 0x1B


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def macho_slices(data: bytes):
    magic = data[:4]
    if magic in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
        is_64 = magic == b"\xca\xfe\xba\xbf"
        count = struct.unpack_from(">I", data, 4)[0]
        size = 32 if is_64 else 20
        for index in range(count):
            fields = struct.unpack_from(">IIQQII" if is_64 else ">IIIII", data, 8 + index * size)
            offset, length = fields[2], fields[3]
            if offset + length > len(data):
                raise ValueError("fat Mach-O slice exceeds file bounds")
            yield data[offset : offset + length]
        return
    yield data


def parse_slice(data: bytes) -> dict:
    if data[:4] == b"\xcf\xfa\xed\xfe":
        endian = "<"
    elif data[:4] == b"\xfe\xed\xfa\xcf":
        endian = ">"
    else:
        raise ValueError("unsupported or non-64-bit Mach-O slice")
    if len(data) < 32:
        raise ValueError("truncated Mach-O header")
    cpu_type, ncmds, sizeofcmds = struct.unpack_from(endian + "I8xII", data, 4)
    architecture = CPU_NAMES.get(cpu_type)
    if not architecture:
        raise ValueError(f"unsupported Mach-O CPU type: 0x{cpu_type:x}")
    if 32 + sizeofcmds > len(data):
        raise ValueError("Mach-O load commands exceed file bounds")
    cursor = 32
    symtab = None
    slice_uuid = None
    for _ in range(ncmds):
        if cursor + 8 > len(data):
            raise ValueError("truncated Mach-O load command")
        command, command_size = struct.unpack_from(endian + "II", data, cursor)
        if command_size < 8 or cursor + command_size > len(data):
            raise ValueError("invalid Mach-O load command size")
        if command == LC_SYMTAB:
            symtab = struct.unpack_from(endian + "IIII", data, cursor + 8)
        elif command == LC_UUID and command_size >= 24:
            slice_uuid = str(uuid.UUID(bytes=bytes(data[cursor + 8 : cursor + 24])))
        cursor += command_size
    if not symtab:
        raise ValueError(f"{architecture} Mach-O has no symbol table")
    if not slice_uuid:
        raise ValueError(f"{architecture} Mach-O has no UUID")
    symbol_offset, symbol_count, string_offset, string_size = symtab
    if symbol_offset + symbol_count * 16 > len(data) or string_offset + string_size > len(data):
        raise ValueError("Mach-O symbol or string table exceeds file bounds")
    strings = data[string_offset : string_offset + string_size]
    symbols: dict[str, int] = {}
    for index in range(symbol_count):
        string_index, symbol_type, _section, _description, value = struct.unpack_from(
            endian + "IBBHQ", data, symbol_offset + index * 16
        )
        if value == 0 or string_index == 0 or string_index >= len(strings) or symbol_type & 0xE0:
            continue
        end = strings.find(b"\0", string_index)
        if end < 0:
            continue
        name = strings[string_index:end].decode("utf-8", errors="surrogateescape")
        symbols.setdefault(name, value)
    return {"architecture": architecture, "uuid": slice_uuid, "symbols": symbols}


def find_symbol(table: dict[str, int], requested: str) -> int | None:
    return table.get(requested) or table.get("_" + requested)


def demangled_index(table: dict[str, int]) -> dict[str, list[str]]:
    llvm_candidates = ["llvm-cxxfilt"] + [f"llvm-cxxfilt-{version}" for version in range(22, 13, -1)]
    executable = next((path for name in llvm_candidates if (path := shutil.which(name))), None)
    if not executable:
        executable = next((str(path) for path in sorted(Path("/usr/bin").glob("llvm-cxxfilt-*"), reverse=True)), None)
    if not executable and sys.platform == "darwin" and shutil.which("xcrun"):
        lookup = subprocess.run(["xcrun", "--find", "llvm-cxxfilt"], text=True, capture_output=True)
        executable = lookup.stdout.strip() if lookup.returncode == 0 else None
    if not executable:
        raise ValueError("LLVM llvm-cxxfilt is required to resolve Apple libc++ C++ names")
    raw_names = list(table)
    # Mach-O adds one leading underscore to external Itanium symbols.
    inputs = [name[1:] if name.startswith("__Z") else name for name in raw_names]
    result = subprocess.run(
        [executable, "-n"], input="\n".join(inputs) + "\n", text=True,
        capture_output=True, check=True,
    )
    index: dict[str, list[str]] = {}
    demangled = result.stdout.splitlines()
    if len(demangled) != len(raw_names):
        raise ValueError("C++ demangler returned an unexpected number of names")
    for raw_name, cpp_name in zip(raw_names, demangled):
        index.setdefault(cpp_name, []).append(raw_name)
        if raw_name.startswith("_") and not raw_name.startswith("__Z"):
            index.setdefault(raw_name[1:], []).append(raw_name)
    return index


def resolve(binary: Path, requirements: dict, architecture: str) -> dict:
    parsed = {item["architecture"]: item for item in map(parse_slice, macho_slices(binary.read_bytes()))}
    if architecture not in parsed:
        raise ValueError(f"release binary has no {architecture} Mach-O slice")
    selected = parsed[architecture]
    table = selected["symbols"]
    methods = {}
    index = demangled_index(table)
    overrides = requirements.get("symbol_overrides", {})
    for cpp_name in requirements["symbols"]:
        requested = overrides.get(cpp_name)
        candidates = [] if requested else index.get(cpp_name, [])
        if requested:
            address = find_symbol(table, requested)
        elif len(candidates) == 1:
            address = table[candidates[0]]
        elif len(candidates) > 1:
            raise ValueError(
                f"C++ symbol is ambiguous and needs a platform override: {cpp_name}: "
                + ", ".join(candidates)
            )
        else:
            address = None
        if address is not None:
            methods[cpp_name] = address
    if len(methods) != len(requirements["symbols"]):
        missing = [name for name in requirements["symbols"] if name not in methods]
        raise ValueError("reviewed function ABI symbols are unavailable: " + ", ".join(missing))
    return {
        "schema_version": 1,
        "kind": "bambustudio_function_abi",
        "platform": "macos",
        "architecture": architecture,
        "binary": {"sha256": sha256_file(binary), "uuid": selected["uuid"]},
        "symbols": methods,
        "analysis": {
            "reviewed": len(requirements["symbols"]),
            "resolved": len(methods),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--architecture", default="arm64", choices=sorted(CPU_NAMES.values()))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--release-asset", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    requirements = json.loads(args.requirements.read_text(encoding="utf-8"))
    document = resolve(args.binary, requirements, args.architecture)
    document["upstream"] = {
        "repository": "https://github.com/bambulab/BambuStudio.git",
        "version": args.version,
        "release_tag": args.release_tag,
        "source_commit": args.source_commit,
        "release_asset": args.release_asset,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"resolved {document['analysis']['resolved']}/{document['analysis']['reviewed']} reviewed symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
