import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract-clang-vtables.py"
FIXTURE = ROOT / "tests" / "fixtures" / "vtable"


class ClangVtableTests(unittest.TestCase):
    def test_virtual_indices_are_extracted(self):
        compiler = shutil.which("clang++")
        if not compiler:
            self.skipTest("clang++ is unavailable")
        with tempfile.TemporaryDirectory(prefix="bambu-vtable-test-") as temp_dir:
            output = Path(temp_dir) / "vtable.json"
            subprocess.run([
                "python3", str(SCRIPT), "--config", str(FIXTURE / "config.json"),
                "--source-dir", str(FIXTURE), "--output", str(output),
                "--compiler", compiler,
            ], check=True)
            indices = json.loads(output.read_text())["vtables"]["fixture"]["indices"]
        self.assertEqual(indices, {"alpha": 2, "beta": 3})


if __name__ == "__main__":
    unittest.main()
