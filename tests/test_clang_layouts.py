import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract-clang-layouts.py"
FIXTURE = ROOT / "tests" / "fixtures" / "layout"


class ClangLayoutTests(unittest.TestCase):
    def test_parser_rejects_missing_members(self):
        spec = importlib.util.spec_from_file_location("extract_clang_layouts", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        dump = """*** Dumping AST Record Layout
         0 | struct Example
         0 |   int present
           | [sizeof=4, dsize=4, align=4,
           |  nvsize=4, nvalign=4]
        """
        with self.assertRaisesRegex(ValueError, "missing fields"):
            module.parse_layout_dump(dump, {"Example": ["absent"]})

    def test_private_members_are_extracted_by_clang(self):
        compiler = shutil.which("clang++")
        if not compiler:
            self.skipTest("clang++ is unavailable")
        with tempfile.TemporaryDirectory(prefix="bambu-layout-test-") as temp_dir:
            output = Path(temp_dir) / "layout.json"
            subprocess.run([
                os.environ.get("PYTHON", "python3"), str(SCRIPT),
                "--config", str(FIXTURE / "config.json"),
                "--source-dir", str(FIXTURE),
                "--output", str(output),
                "--compiler", compiler,
            ], check=True)
            layout = json.loads(output.read_text())["layouts"]["fixture.probe"]
        self.assertEqual(layout["size"], 24)
        self.assertEqual(layout["alignment"], 8)
        self.assertEqual(layout["members"], {"enabled": 4, "ratio": 8, "marker": 16})
        self.assertEqual(layout["bases"], {"fixture_base": 0})


if __name__ == "__main__":
    unittest.main()
