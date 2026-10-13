import sys
import struct
import tempfile
import unittest
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mmd_assets as m


def txt(s):
    b=s.encode('utf-8')
    return struct.pack('<i',len(b))+b


def pmx_fixture():
    b=bytearray(b'PMX '+struct.pack('<fB',2.0,8)+bytes([1,0,1,1,1,1,1,1]))
    for t in ('Miku','Miku','description','description'):
        b+=txt(t)
    b+=struct.pack('<i',3)
    for x,y,z in ((0,0,0),(1,0,0),(0,1,0)):
        b+=struct.pack('<3f3f2f',x,y,z,0,0,1,x,y)
        b+=bytes([0,0])+struct.pack('<f',1)
    b+=struct.pack('<i3B',3,0,1,2)
    b+=struct.pack('<i',1)+txt('test.png')
    b+=struct.pack('<i',1)+txt('Material')+txt('Material')
    b+=bytes(16+12+4+12+1+16+4)+bytes([0,255,0,1,0])+txt('')+struct.pack('<i',3)
    b+=struct.pack('<i',1)+txt('センター')+txt('Center')+struct.pack('<3f',0,0,0)
    b+=bytes([255])+struct.pack('<iH3f',0,0,0,0,0)
    return bytes(b)


def vmd_fixture():
    b=bytearray(b'Vocaloid Motion Data 0002'.ljust(30,b'\x00'))
    b+=b'Miku'.ljust(20,b'\0')+struct.pack('<I',1)
    b+=b'Center'.ljust(15,b'\0')+struct.pack('<I3f4f',30,1,2,3,0,0,0,1)+bytes(64)
    return bytes(b)


class MmdTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)

    def test_pmx_obj_export(self):
        path=self.root/'source.pmx';path.write_bytes(pmx_fixture())
        info=m.read_pmx(path)
        self.assertEqual(len(info['bones']),1)
        self.assertEqual(len(info['vertices']),3)
        export=m.export_obj(path,self.root/'out.obj')
        self.assertEqual(export['triangle_count'],1)
        self.assertIn('f 1/1 2/2 3/3',(self.root/'out.obj').read_text())

    def test_motion(self):
        path=self.root/'source.vmd';path.write_bytes(vmd_fixture())
        self.assertEqual(m.read_vmd(path)['frame_count'],31)
        p=self.root/'motion.json'
        data=m.export_motion(path,p,{'Center':'Root'})
        self.assertEqual(data['track_count'],1)
        self.assertIn('Root',json.loads(p.read_text())['tracks'])

    def test_truncated(self):
        path=self.root/'source.pmx';path.write_bytes(pmx_fixture()[:-5])
        with self.assertRaises(m.MmdFormatError):m.read_pmx(path)

    def test_nonfinite(self):
        raw=bytearray(vmd_fixture())
        raw[30+20+4+15+4:30+20+4+15+8]=struct.pack('<f',float('nan'))
        path=self.root/'bad.vmd';path.write_bytes(raw)
        with self.assertRaises(m.MmdFormatError):m.read_vmd(path)

    def test_invalid_pmd(self):
        path=self.root/'bad.pmd';path.write_bytes(b'Not a PMD')
        with self.assertRaises(m.MmdFormatError):m.inspect_pmd(path)


if __name__=='__main__':unittest.main()
