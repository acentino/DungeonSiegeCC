import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import manager
import update_helper


class UpdatesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()
        (self.bundle / "README.txt").write_text("test framework", encoding="utf-8")
        checksum = hashlib.sha256(b"test framework").hexdigest()
        (self.bundle / "manifest.json").write_text(
            json.dumps({"version": "0.3.0", "files": {"README.txt": checksum}}), encoding="utf-8"
        )

    def test_release_versions(self):
        self.assertGreater(manager.version_tuple("v0.3.0"), manager.version_tuple("0.2.0"))
        self.assertEqual(manager.version_tuple("0.3.0"), manager.version_tuple("v0.3.0"))

    def test_archive_rejects_traversal(self):
        archive = self.root / "evil.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("../escape.py", "bad")
        with self.assertRaises(ValueError):
            manager.extract_update(archive, self.root / "unpack")
        self.assertFalse((self.root / "escape.py").exists())

    def test_archive_staging(self):
        archive = self.root / "good.zip"
        with zipfile.ZipFile(archive, "w") as z:
            for name in ("importer.py", "manager.py", "update_helper.py", "mmd_assets.py", "game_pipeline.py", "asset_probe.py", "ds2_tank.py", "START_WINDOWS.bat"):
                z.writestr(name, "placeholder")
            z.write(self.bundle / "README.txt", "framework_bundle/README.txt")
            z.write(self.bundle / "manifest.json", "framework_bundle/manifest.json")
        stage = manager.extract_update(archive, self.root / "stage")
        self.assertTrue((stage / "framework_bundle" / "README.txt").exists())

    def test_replace_owned_files_only(self):
        stage = self.root / "stage"
        target = self.root / "app"
        stage.mkdir()
        target.mkdir()
        for name in ("importer.py", "manager.py", "update_helper.py", "mmd_assets.py", "game_pipeline.py", "asset_probe.py", "ds2_tank.py"):
            (stage / name).write_text("new", encoding="utf-8")
            (target / name).write_text("old", encoding="utf-8")
        (stage / "framework_bundle").mkdir()
        for name in ("README.txt", "manifest.json"):
            (stage / "framework_bundle" / name).write_bytes((self.bundle / name).read_bytes())
        (target / "Characters").mkdir()
        (target / "Characters" / "miku.pmx").write_bytes(b"keep")
        (target / "user_project.json").write_text("keep")
        update_helper.apply_update(stage, target)
        self.assertEqual((target / "importer.py").read_text(), "new")
        self.assertEqual((target / "Characters" / "miku.pmx").read_bytes(), b"keep")
        self.assertEqual((target / "user_project.json").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
