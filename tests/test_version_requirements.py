import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "resolve-version-requirements.py"


class VersionRequirementsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("resolve_version_requirements", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_numeric_version_order_is_not_lexicographic(self):
        self.assertGreater(
            self.module.version_key("02.10.00.00"),
            self.module.version_key("02.09.99.99"),
        )

    def test_non_numeric_release_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "numeric dot-separated"):
            self.module.version_key("latest")


if __name__ == "__main__":
    unittest.main()
