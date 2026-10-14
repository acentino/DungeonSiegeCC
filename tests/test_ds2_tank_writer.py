"""Round-trip and safety tests for the independent DS2 Tank raw packer."""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from ds2_tank import Tank
from ds2_tank_writer import TankBuildError, pack_directory


class TankWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.src=self.root/"overlay"
        self.src.mkdir()

    def test_roundtrip_nested_gas_skrit_and_binaries(self):
        data={
            "world/contentdb/templates/regular/actors/good/companion.gas":
                b"[t:template,n:dscc_test]\n{ specializes = base_npc; }\n",
            "world/ai/jobs/sample.skrit": b"// skrit \r\n",
            "art/meshes/model.asp": bytes(range(256))*16,
            "art/animations/run.prs": b"\0"*250,
        }
        for name,body in data.items():
            file=self.src/name
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes(body)
        archive=self.root/"dalvi.ds2res"
        result=pack_directory(self.src,archive)
        self.assertEqual(result["files"],4)
        self.assertEqual(result["verification"],"read_back_passed")
        self.assertFalse(result["gameplay_tested"])
        tank=Tank(archive)
        self.assertEqual(len(tank.entries),4)
        for name,body in data.items():
            self.assertEqual(tank.read_file(name),body)
        raw=archive.read_bytes()
        self.assertEqual(raw[:8],b"DSg2Tank")
        version,dir_off,file_off,idx_size,data_off=struct.unpack_from("<5I",raw,8)
        self.assertEqual(version,0x00010100)
        self.assertEqual(zlib.crc32(raw[dir_off:dir_off+idx_size]),
                         struct.unpack_from("<I",raw,80)[0])
        self.assertEqual(struct.unpack_from("<I",raw,84)[0],
                         zlib.crc32(b"".join(data[name] for name in sorted(data,key=str.lower))))
        with self.assertRaises(FileExistsError):
            pack_directory(self.src,archive)

    def test_no_input_or_bad_non_ascii_filename(self):
        with self.assertRaises(TankBuildError):
            pack_directory(self.src,self.root/"bad.ds2res")
        (self.src/"échantillon.gas").write_bytes(b"data")
        with self.assertRaises(TankBuildError):
            pack_directory(self.src,self.root/"bad.ds2res")
        self.assertFalse((self.root/"bad.ds2res").exists())

    def test_case_insensitive_name_collision(self):
        (self.src/"Actor.gas").write_bytes(b"a")
        (self.src/"actor.gas").write_bytes(b"b")
        if len(list(self.src.iterdir())) != 2:
            self.skipTest("Test requires case sensitive filesystem")
        with self.assertRaises(TankBuildError):
            pack_directory(self.src,self.root/"bad.ds2res")


if __name__=="__main__":
    unittest.main()
