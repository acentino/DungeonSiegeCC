import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import asset_probe as ap

class AssetProbeTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)

    def test_ds2_tank_header(self):
        p=self.root/"Logic.ds2res"
        p.write_bytes(b"DSg2Tank"+struct.pack("<5I",1,32,48,32,28)+bytes(100))
        header=ap.tank_header(p)
        self.assertEqual(header["product"],"DSg2")
        self.assertTrue(header["valid_basic_header"])

    def test_archive_inventory(self):
        game=self.root/"Game"
        res=game/"Resources"
        res.mkdir(parents=True)
        for name in ("Logic.ds2res","Objects.ds2res"):
            (res/name).write_bytes(b"DSg2Tank"+struct.pack("<5I",1,32,48,32,28)+bytes(100))
        report=ap.scan_game_archives(game)
        self.assertEqual(report["archive_count"],2)
        self.assertTrue(report["core_logic_found"] and report["core_objects_found"])

    def test_bad_tank(self):
        p=self.root/"x.ds2res"
        p.write_bytes(b"ZIP!"+bytes(100))
        with self.assertRaises(ap.AssetProbeError):ap.tank_header(p)

    def test_zip_inventory_and_extraction(self):
        p=self.root/"mmd.zip"
        with zipfile.ZipFile(p,"w") as z:
            z.writestr("Dalvi/model.pmx",b"PMX "+bytes(10))
            z.writestr("Dalvi/tex.png",b"png")
            z.writestr("Dalvi/idle.vmd",b"Vocaloid Motion Data 0002"+bytes(100))
            z.writestr("Dalvi/readme.txt",b"credits")
        info=ap.scan_mmd_zip(p)
        self.assertEqual(info["model_count"],1)
        self.assertTrue(info["models"][0]["recognized_signature"])
        out=ap.extract_mmd_zip(p,self.root/"extracted")
        self.assertEqual(out["extracted_count"],4)
        self.assertTrue((self.root/"extracted"/"Dalvi"/"model.pmx").is_file())
        with self.assertRaises(FileExistsError):ap.extract_mmd_zip(p,self.root/"extracted")

    def test_zip_traversal_is_rejected_without_writing(self):
        p=self.root/"evil.zip"
        with zipfile.ZipFile(p,"w") as z:
            z.writestr("../bad.pmx",b"PMX ")
        with self.assertRaises(ap.AssetProbeError):ap.scan_mmd_zip(p)
        with self.assertRaises(ap.AssetProbeError):ap.extract_mmd_zip(p,self.root/"out")
        self.assertFalse((self.root/"bad.pmx").exists())
        self.assertFalse((self.root/"out").exists())

if __name__=="__main__":
    unittest.main()
