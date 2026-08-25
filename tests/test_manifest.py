# Copyright 2026 BambuStudio ABI Layouts contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
import pathlib
import unittest


MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts"
    / "create-macos-manifest.py"
)
SPEC = importlib.util.spec_from_file_location("create_macos_manifest", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ParseUuidLinesTest(unittest.TestCase):
    def test_parses_and_sorts_dwarfdump_output(self) -> None:
        result = MODULE.parse_uuid_lines(
            [
                "UUID: AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE (x86_64) /tmp/BambuStudio",
                "unrelated warning",
                "UUID: 11111111-2222-3333-4444-555555555555 (arm64) /tmp/BambuStudio",
            ]
        )

        self.assertEqual(
            result,
            [
                {
                    "uuid": "11111111-2222-3333-4444-555555555555",
                    "architecture": "arm64",
                },
                {
                    "uuid": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
                    "architecture": "x86_64",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
