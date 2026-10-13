"""Read-only Dungeon Siege II Tank index and selective resource extractor.

Supported: DSg2/DSig index browsing, raw and zlib (deflate) file payloads.
LZO content fails explicitly. Never modifies original .ds2res archives.

Format references: TankArchive (Xentax); TankEditor by Partakithware (MIT).
This is an independent Python implementation, not a binary redistribution.
"""
from __future__ import annotations

import argparse
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

MAX_ITEMS = 1_000_000
MAX_FILE_SIZE = 256 * 1024 * 1024
MAX_EXTRACT_SIZE = 1024 * 1024 * 1024


class TankError(ValueError):
    pass


@dataclass
class FileEntry:
    path: str
    size: int
    offset: int
    format: int
    flags: int
    compressed_size: int = 0
    chunks: tuple = ()


class Cursor:
    def __init__(self, file, limit):
        self.file = file
        self.limit = limit

    def seek(self, offset):
        if not 0 <= offset <= self.limit:
            raise TankError("Index offset lies outside the archive")
        self.file.seek(offset)

    def take(self, count):
        if not 0 <= count <= MAX_FILE_SIZE:
            raise TankError("Invalid field length")
        if self.file.tell() + count > self.limit:
            raise TankError("Truncated or malformed tank")
        data = self.file.read(count)
        if len(data) != count:
            raise TankError("Unexpected EOF")
        return data

    def u16(self):
        return struct.unpack("<H", self.take(2))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def nstring(self):
        length = self.u16()
        aligned = length + 2 + (4 - (length + 2) % 4)
        buffer = self.take(aligned - 2)
        return buffer[:length].decode("cp1252", errors="replace")


class Tank:
    def __init__(self, filename):
        self.filename = Path(filename)
        self.size = self.filename.stat().st_size
        self.entries = {}
        self.dir_offset = 0
        self.file_offset = 0
        self.data_offset = 0
        self._parse()

    def _parse(self):
        with self.filename.open("rb") as file:
            cur = Cursor(file, self.size)
            signature = cur.take(8)
            if signature not in (b"DSg2Tank", b"DSigTank"):
                raise TankError("Unrecognized tank signature")
            self.header_version, self.dir_offset, self.file_offset, _index_size, self.data_offset = struct.unpack("<5I", cur.take(20))
            if not 28 <= self.dir_offset < self.size or not 28 <= self.file_offset < self.size:
                raise TankError("Invalid index offsets")
            if self.data_offset >= self.size:
                raise TankError("Invalid data offset")
            cur.seek(self.dir_offset)
            dirs_count = cur.u32()
            if dirs_count > MAX_ITEMS or dirs_count * 4 > self.size:
                raise TankError("Invalid directory count")
            offsets = [cur.u32() for _ in range(dirs_count)]
            directories = {}
            for off in offsets:
                cur.seek(self.dir_offset + off)
                parent, children = cur.u32(), cur.u32()
                if children > MAX_ITEMS:
                    raise TankError("Too many children in directory")
                cur.take(8)  # FILETIME
                name = cur.nstring()
                if "/" in name or ".." in name or "\0" in name:
                    raise TankError("Invalid directory name")
                cur.take(4 * children)
                directories[off] = (parent, name)
            def directory_path(off):
                seen = set()
                names = []
                while off:
                    if off in seen or off not in directories:
                        raise TankError("Directory cycle or missing parent")
                    seen.add(off)
                    parent, name = directories[off]
                    if name not in ("", "\\"):
                        names.append(name)
                    off = parent
                return list(reversed(names))

            cur.seek(self.file_offset)
            files_count = cur.u32()
            if files_count > MAX_ITEMS or files_count * 4 > self.size:
                raise TankError("Invalid file count")
            offsets = [cur.u32() for _ in range(files_count)]
            for off in offsets:
                cur.seek(self.file_offset + off)
                parent, size, data_off, _crc = struct.unpack("<4I", cur.take(16))
                cur.take(8)  # FILETIME
                fmt, flags = struct.unpack("<2H", cur.take(4))
                name = cur.nstring()
                if size > MAX_FILE_SIZE:
                    # Advertise large files but refuse to extract later.
                    pass
                if not name or name in (".", "..") or any(x in name for x in ("/", "\\", "\0", ":")):
                    raise TankError("Invalid file entry name")
                if fmt not in (0, 1, 2):
                    raise TankError("Unknown compression format " + str(fmt))
                comp_size = 0
                chunks = ()
                if fmt and size:
                    comp_size, chunk_size = cur.u32(), cur.u32()
                    if chunk_size:
                        count = (size + chunk_size - 1) // chunk_size
                        if count > MAX_ITEMS:
                            raise TankError("Invalid chunk count")
                        chunks = tuple(struct.unpack("<4I", cur.take(16)) for _ in range(count))
                rel = directory_path(parent) + [name]
                if len(rel) > 128 or any(part in ("", ".", "..") for part in rel):
                    raise TankError("Unsafe resource path")
                path = "/".join(rel)
                self.entries[path.lower()] = FileEntry(path, size, data_off, fmt, flags, comp_size, chunks)

    def list_files(self, suffixes=()):
        suffixes = tuple(s.lower() for s in suffixes)
        entries = sorted(self.entries.values(), key=lambda e: e.path.lower())
        return [e for e in entries if not suffixes or e.path.lower().endswith(suffixes)]

    def _read_range(self, cur, offset, size):
        if not 0 <= size <= MAX_FILE_SIZE:
            raise TankError("File too large to extract safely")
        position = self.data_offset + offset
        if position + size > self.size:
            raise TankError("File data lies past end of tank")
        cur.seek(position)
        return cur.take(size)

    @staticmethod
    def _inflate(data, expected):
        for mode in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                out = zlib.decompress(data, mode)
                if len(out) == expected:
                    return out
            except zlib.error:
                pass
        raise TankError("Deflate decompression failed or returned unexpected length")

    def read_file(self, entry):
        if isinstance(entry, str):
            entry = self.entries[entry.lower().replace("\\", "/").lstrip("/")]
        if entry.flags & 0x8000:
            raise TankError("File flagged invalid by the game")
        if entry.size > MAX_FILE_SIZE:
            raise TankError("File too large")
        if entry.size == 0:
            return b""
        if entry.format == 2:
            raise TankError("LZO-compressed entry needs a supported LZO decoder")
        with self.filename.open("rb") as file:
            cur = Cursor(file, self.size)
            if entry.format == 0:
                return self._read_range(cur, entry.offset, entry.size)
            if not entry.chunks:
                raw = self._read_range(cur, entry.offset, entry.compressed_size)
                return self._inflate(raw, entry.size)
            result = bytearray()
            for raw_size, packed_size, extra_size, offset in entry.chunks:
                if raw_size > MAX_FILE_SIZE or packed_size > MAX_FILE_SIZE or extra_size > 1024 * 1024:
                    raise TankError("Invalid compressed chunk size")
                blob = self._read_range(cur, entry.offset + offset, packed_size + extra_size)
                if raw_size == packed_size:
                    unpacked = blob[:packed_size]
                else:
                    unpacked = self._inflate(blob[:packed_size], raw_size)
                result.extend(unpacked)
                if extra_size and raw_size != packed_size:
                    result.extend(blob[packed_size:])
                if len(result) > entry.size:
                    raise TankError("Decompressed content exceeds declared size")
            if len(result) != entry.size:
                raise TankError("Decompressed content is truncated")
            return bytes(result)

    def extract(self, destination, suffixes=(".gas", ".skrit", ".asp", ".prs"), max_files=10000, contains=None):
        """Writes only requested types beneath a new destination; never overwrites."""
        destination = Path(destination)
        if destination.exists():
            raise FileExistsError("Destination already exists: " + str(destination))
        entries = self.list_files(suffixes)
        if contains:
            entries = [e for e in entries if contains.casefold() in e.path.casefold()]
        if len(entries) > max_files:
            raise TankError("Too many matching files; use a narrower extension filter")
        if sum(e.size for e in entries) > MAX_EXTRACT_SIZE:
            raise TankError("Requested extraction exceeds 1 GiB safety cap")
        destination.mkdir(parents=True)
        report = {"archive": self.filename.name, "matched": len(entries), "written": 0, "errors": []}
        try:
            for item in entries:
                try:
                    payload = self.read_file(item)
                    path = destination.joinpath(*item.path.split("/"))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(payload)
                    report["written"] += 1
                except (TankError, OSError, KeyError) as e:
                    report["errors"].append({"name": item.path, "error": str(e)})
            (destination / "dscc_extraction_report.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8")
            return report
        except Exception:
            import shutil
            shutil.rmtree(destination, ignore_errors=True)
            raise

    def inventory(self):
        from collections import Counter
        counts = Counter(Path(x.path).suffix.lower() for x in self.entries.values())
        return {"archive": self.filename.name, "total_files": len(self.entries),
                "extensions": dict(counts),
                "gas_examples": [e.path for e in self.list_files((".gas",))[:20]],
                "asp_examples": [e.path for e in self.list_files((".asp",))[:20]],
                "prs_examples": [e.path for e in self.list_files((".prs",))[:20]]}


def game_inventory(game_dir):
    """Deep-inspect local Logic and Objects tanks without extracting resources."""
    root = Path(game_dir)
    candidates = (root / "Resources", root / "resources", root)
    resources = next((p for p in candidates if p.is_dir() and
        any(f.suffix.lower() == ".ds2res" for f in p.iterdir() if f.is_file())), None)
    if resources is None:
        raise TankError("No Dungeon Siege II .ds2res files found")
    report = {"resources": str(resources), "archives": {}}
    for name in ("Logic.ds2res", "Objects.ds2res"):
        path = next((p for p in resources.iterdir() if p.name.lower() == name.lower()), None)
        if path is None:
            report["archives"][name] = {"error": "Archive not found"}
            continue
        try:
            report["archives"][name] = Tank(path).inventory()
        except (TankError, OSError, struct.error) as e:
            report["archives"][name] = {"error": str(e)}
    return report


def extract_game_references(game_dir, output, kind, contains=None):
    """Extract logic GAS/Skrit, or filtered Objects ASP/PRS, into a new folder."""
    if kind not in ("logic", "objects"):
        raise TankError("Select logic or objects references")
    report = game_inventory(game_dir)
    resources = Path(report["resources"])
    tank_name = "Logic.ds2res" if kind == "logic" else "Objects.ds2res"
    path = next((x for x in resources.iterdir() if x.name.lower() == tank_name.lower()), None)
    if path is None:
        raise TankError(tank_name + " not found")
    if kind == "objects" and not contains:
        raise TankError("Use a non-empty filename filter when extracting potentially large model archives")
    tank = Tank(path)
    return tank.extract(output,
                        (".gas", ".skrit") if kind == "logic" else (".asp", ".prs"),
                        max_files=20000,
                        contains=contains)

def main():
    p = argparse.ArgumentParser(description="Local DS2 Tank index/extractor (raw/zlib)")
    p.add_argument("archive", help="Local .ds2res path")
    p.add_argument("--index", action="store_true")
    p.add_argument("--extract-to")
    p.add_argument("--suffix", action="append", choices=[".gas", ".skrit", ".asp", ".prs"])
    args = p.parse_args()
    tank = Tank(args.archive)
    if args.index:
        print(json.dumps(tank.inventory(), indent=2))
    if args.extract_to:
        print(json.dumps(tank.extract(args.extract_to, args.suffix or
              (".gas", ".skrit", ".asp", ".prs")), indent=2))


if __name__ == "__main__":
    main()
