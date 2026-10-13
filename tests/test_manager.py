import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import manager

class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.game=self.root/"Game"
        self.game.mkdir()
        (self.game/"DungeonSiege2.exe").write_bytes(b"game")
        self.bundle=self.root/"bundle"
        self.bundle.mkdir()
        (self.bundle/"core.txt").write_text("alpha")
        (self.bundle/"manifest.json").write_text(json.dumps({"version":"0.2.0","files":{"core.txt":hashlib.sha256(b"alpha").hexdigest()}}))
    def test_install_and_repair(self):
        self.assertEqual(manager.framework_status(self.game,self.bundle),"missing")
        manager.install_framework(self.game,self.bundle)
        self.assertEqual(manager.framework_status(self.game,self.bundle),"installed")
        (self.game/manager.FRAMEWORK_DIR/"core.txt").write_text("damage")
        self.assertEqual(manager.framework_status(self.game,self.bundle),"repair")
        manager.install_framework(self.game,self.bundle)
        self.assertEqual(manager.framework_status(self.game,self.bundle),"installed")
    def test_preserves_other_files(self):
        chars=self.game/manager.FRAMEWORK_DIR/"Characters"
        chars.mkdir(parents=True)
        (chars/"custom.txt").write_text("keep")
        manager.install_framework(self.game,self.bundle)
        self.assertEqual((chars/"custom.txt").read_text(),"keep")
    def test_invalid_game(self):
        with self.assertRaises(ValueError):manager.install_framework(self.root,self.bundle)
    def test_bad_bundle_hash(self):
        (self.bundle/"core.txt").write_text("tampered")
        with self.assertRaises(ValueError):manager.install_framework(self.game,self.bundle)
    def test_settings(self):
        config=self.root/"settings.json"
        manager.save_settings({"game_path":"X"},config)
        self.assertEqual(manager.load_settings(config)["game_path"],"X")

if __name__=="__main__":unittest.main()
