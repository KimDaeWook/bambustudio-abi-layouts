import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract-bambustudio-abi.py"


class CombinedExtractorTests(unittest.TestCase):
    def test_production_catalog_is_complete_and_unique(self):
        config = json.loads(
            (ROOT / "config" / "bambustudio-abi-values.json").read_text()
        )
        names = [value["name"] for value in config["values"]]
        self.assertTrue(names)
        self.assertEqual(len(set(names)), len(names))

    def test_record_and_vtable_results_are_merged(self):
        compiler = shutil.which("clang++")
        if not compiler:
            self.skipTest("clang++ is unavailable")
        with tempfile.TemporaryDirectory(prefix="bambu-combined-test-") as temp_dir:
            temp = Path(temp_dir)
            values_config = temp / "values.json"
            values_config.write_text(json.dumps({"values": [
                {"name": "fixture.marker", "layout": "fixture.probe", "member": "marker"},
                {"name": "fixture.beta", "vtable": "fixture", "method": "beta"},
                {"name": "fixture.sum", "sum": [
                    {"layout": "fixture.probe", "member": "enabled"},
                    {"vtable": "fixture", "method": "alpha"},
                ]},
            ]}))
            output = temp / "abi.json"
            subprocess.run([
                "python3", str(SCRIPT),
                "--source-dir", str(ROOT / "tests" / "fixtures" / "layout"),
                "--layout-config", str(ROOT / "tests" / "fixtures" / "layout" / "config.json"),
                "--vtable-config", str(ROOT / "tests" / "fixtures" / "layout" / "vtable-config.json"),
                "--values-config", str(values_config),
                "--output", str(output),
                "--compiler", compiler,
            ], check=True)
            document = json.loads(output.read_text())
        self.assertEqual(document["values"], {
            "fixture.marker": 16,
            "fixture.beta": 3,
            "fixture.sum": 6,
        })
        self.assertTrue(document["extraction"]["parallel"])


if __name__ == "__main__":
    unittest.main()
