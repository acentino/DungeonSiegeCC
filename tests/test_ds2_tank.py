import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from ds2_tank import Tank, TankError


def nstring(value):
    data = value.encode("ascii")
    padding = 4 - ((len(data) + 2) % 4)
    return struct.pack("<H", len(data)) + data + b"\0" * padding


def synthetic_tank(path):
    """Make a small indexed DS2 tank with raw, zlib and chunked-zlib GAS."""
    data0 = b"[t:template,n:test]\n{}\n"
    data1 = b"model-asp-binary-contents"
    data2 = b"animation-prs-contents"
    zip1 = zlib.compress(data1)
    zip2 = zlib.compress(data2)
    entries = [
        (0, data0, 0, b"", 0),
        (1, data1, len(data0), zip1, 0),
        (1, data2, len(data0) + len(zip1), zip2, 1),
    ]
    payload = data0 + zip1 + zip2
    file_entries = []
    for index, (fmt, unpacked, offset, compressed, chunked) in enumerate(entries):
        name = ("mycompanion.gas", "hero.asp", "run.prs")[index]
        header = struct.pack("<4I", 0, len(unpacked), offset, 0) + b"\0"*8
        header += struct.pack("<HH", fmt, 0) + nstring(name)
        if fmt:
            if chunked:
                header += struct.pack("<II", len(compressed), len(unpacked))
                header += struct.pack("<4I", len(unpacked), len(compressed), 0, 0)
            else:
                header += struct.pack("<II", len(compressed), 0)
        file_entries.append(header)
    offsets = []
    position = 4 + len(file_entries) * 4
    for entry in file_entries:
        offsets.append(position)
        position += len(entry)
    file_set = struct.pack("<I", len(file_entries))
    file_set += struct.pack("<" + "I"*len(offsets), *offsets) + b"".join(file_entries)
    ds=128
    fs=256
    data_offset=1024
    assert len(file_set) < data_offset - fs
    output = bytearray(b"\0" * data_offset)
    struct.pack_into("<8s5I", output, 0, b"DSg2Tank", 2, ds, fs, 0, data_offset)
    output[ds:ds+4] = struct.pack("<I", 0)
    output[fs:fs+len(file_set)] = file_set
    path.write_bytes(output + payload)
    return data0, data1, data2


class TankTests(unittest.TestCase):
    def test_index_and_zlib_extraction(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            archive = root/"Logic.ds2res"
            raw, zlib_file, chunked = synthetic_tank(archive)
            tank = Tank(archive)
            self.assertEqual(len(tank.list_files()), 3)
            self.assertEqual(tank.read_file("mycompanion.gas"), raw)
            self.assertEqual(tank.read_file("hero.asp"), zlib_file)
            self.assertEqual(tank.read_file("run.prs"), chunked)
            index=tank.inventory()
            self.assertEqual(index["extensions"][".gas"],1)
            destination=root/"extracted"
            report=tank.extract(destination,(".gas", ".prs"))
            self.assertEqual(report["written"],2)
            self.assertEqual((destination/"run.prs").read_bytes(),chunked)
            self.assertFalse((destination/"hero.asp").exists())
            with self.assertRaises(FileExistsError):
                tank.extract(destination, (".asp",))

    def test_corrupt_magic(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/"bad.ds2res"
            file.write_bytes(b"NotATank"+b"\0"*300)
            with self.assertRaises(TankError):
                Tank(file)

    def test_out_of_range_data(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/"too_short.ds2res"
            synthetic_tank(file)
            content=bytearray(file.read_bytes())
            struct.pack_into("<I",content,24,50_000_000)
            file.write_bytes(content)
            with self.assertRaises(TankError):
                Tank(file)

    def test_safe_read_rejects_corrupt_length(self):
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/"badsize.ds2res"
            synthetic_tank(file)
            content=bytearray(file.read_bytes())
            # First file record begins at FileSetOffset + 4 + 3*4
            struct.pack_into("<I",content,256+16+4,999_999_999)
            file.write_bytes(content)
            with self.assertRaises(TankError):
                Tank(file).read_file("mycompanion.gas")


if __name__ == "__main__":
    unittest.main()
