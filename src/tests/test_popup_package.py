"""Safety checks for the popup hotfix packer, with tiny synthetic inventories."""

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import package_popup_hotfix as pack


class PopupPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def inventory(self, special="safe.txt", count=4921, symlink=False):
        path = self.root / "base.zip"
        with ZipFile(path, "w") as z:
            first = ZipInfo(special)
            if symlink:
                first.create_system = 3
                first.external_attr = 0o120777 << 16
            z.writestr(first, b"")
            for i in range(count - 1):
                z.writestr("fixture/{}.txt".format(i), b"")
        data = path.read_bytes()
        # Pin only this synthetic fixture in memory; never alter published pins.
        self.enterContext(patch.object(pack, "BASE_BYTES", len(data)))
        self.enterContext(patch.object(pack, "BASE_SHA256", hashlib.sha256(data).hexdigest()))
        return path

    def test_wrong_base_rejected_before_extraction(self):
        path = self.root / "wrong.zip"
        path.write_bytes(b"not the published archive")
        with self.assertRaisesRegex(ValueError, "published"):
            pack.inspect_base(path)

    def test_existing_artifacts_not_overwritten(self):
        output, report = self.root / "out.zip", self.root / "report.json"
        output.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            pack.build(self.root / "missing.zip", self.root, output, report)
        self.assertEqual(output.read_bytes(), b"keep")
        output.unlink()
        report.write_bytes(b"keep-report")
        with self.assertRaises(FileExistsError):
            pack.build(self.root / "missing.zip", self.root, output, report)
        self.assertEqual(report.read_bytes(), b"keep-report")

    def test_safe_inventory_accepted(self):
        self.assertEqual(len(pack.inspect_base(self.inventory())), 4921)

    def test_inventory_count_is_pinned(self):
        with self.assertRaisesRegex(ValueError, "entries"):
            pack.inspect_base(self.inventory(count=4920))

    def test_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            pack.inspect_base(self.inventory("../outside.txt"))

    def test_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, "symlink"):
            pack.inspect_base(self.inventory(symlink=True))

    def test_windows_case_collision_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            pack.inspect_base(self.inventory("FIXTURE/0.TXT"))

    def test_private_configuration_rejected(self):
        with self.assertRaisesRegex(ValueError, "Private"):
            pack.inspect_base(self.inventory("userconfig/config.json"))

    def test_unfinished_translation_model_rejected(self):
        with self.assertRaisesRegex(ValueError, "unfinished"):
            pack.inspect_base(self.inventory("LunaTranslator/translator/local_hymt.py"))

    def test_generator_weights_rejected(self):
        with self.assertRaisesRegex(ValueError, "unfinished"):
            pack.inspect_base(self.inventory("files/model.gguf"))


if __name__ == "__main__":
    unittest.main()
