import importlib.util
import struct
import tempfile
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract-macho-function-abi.py"


class MachoFunctionAbiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("extract_macho_function_abi", SCRIPT)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_extracts_arm64_uuid_and_reviewed_addresses(self):
        symbol = "_Z4testv"
        strings = b"\0" + symbol.encode() + b"\0"
        symbol_offset = 32 + 24 + 24
        string_offset = symbol_offset + 16
        header = b"\xcf\xfa\xed\xfe" + struct.pack(
            "<iiIIIII", 0x0100000C, 0, 2, 2, 48, 0, 0
        )
        expected_uuid = uuid.UUID("12345678-1234-5678-1234-567812345678")
        uuid_command = struct.pack("<II", 0x1B, 24) + expected_uuid.bytes
        symtab_command = struct.pack("<IIIIII", 0x2, 24, symbol_offset, 1, string_offset, len(strings))
        nlist = struct.pack("<IBBHQ", 1, 0x0F, 1, 0, 0x100004000)
        requirements = {
            "compatibility": {"required_symbols": ["Test"]},
            "symbols": [{"logical_name": "Test", "symbol": symbol}],
            "events": {
                "add_filter_symbol": symbol,
                "remove_filter_symbol": symbol,
                "entries": [{"symbol": symbol, "kind": "test", "reason": "fixture"}],
            },
        }
        with tempfile.TemporaryDirectory(prefix="bse-macho-test-") as temporary:
            binary = Path(temporary) / "fixture"
            binary.write_bytes(header + uuid_command + symtab_command + nlist + strings)
            result = self.module.resolve(binary, requirements, "arm64")
        self.assertEqual(result["binary"]["uuid"], str(expected_uuid))
        self.assertEqual(result["symbols"][0]["address"], "0x100004000")
        self.assertEqual(result["events"]["entries"][0]["address"], "0x100004000")

if __name__ == "__main__":
    unittest.main()
