import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "package-abi-layout.py"


class PackageAbiLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("package_abi_layout", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_values_are_nested_for_runtime_lookup(self):
        result = self.module.nested_values({
            "toolbar.data_size": 720,
            "events.event_type_offset": 24,
        })
        self.assertEqual(result, {
            "events": {"event_type_offset": 24},
            "toolbar": {"data_size": 720},
        })

    def test_invalid_or_deeper_names_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "one group separator"):
            self.module.nested_values({"toolbar.option.action": 1})
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            self.module.nested_values({"toolbar.data_size": -1})


if __name__ == "__main__":
    unittest.main()
