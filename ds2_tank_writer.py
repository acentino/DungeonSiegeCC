"""Experimental read/write complement to ds2_tank.Tank.

Builds a DS2 .ds2res container from user-owned loose resource files.
This is container packing only: it does not turn OBJ/PMX into ASP nor
implement Skrit recruitment logic.

The Tank index/header layout was cross-checked with the MIT-licensed
TankEditor by PartakithRC1 (c) 2026.
https://github.com/PartakithRC1/TankEditor
No TankEditor binary or source code is bundled.
"""
from __future__ import annotations
import datetime as dt
import os
import struct
import uuid
import zlib
from pathlib import Path
from ds2_tank import Tank, TankError

MAX_ENTRY = 256 * 1024 * 1024
MAX_TOTAL = 1024 * 1024 * 1024
MAX_ENTRIES = 20_000


class TankBuildError(ValueError):
    pass


def _name(text):
    if text == "":
        return bytes(4)  # Only the root directory uses an empty NSTRING.
    if text in (".", "..") or any(x in text for x in "/\\:\0"):
        raise TankBuildError("Invalid tank entry name: " + repr(text))
    try:
        encoded = text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise TankBuildError("Tank path must use ASCII names: " + text) from exc
    if len(encoded) > 250:
        raise TankBuildError("Tank name too long: " + text)
    padding = 4 - (len(encoded) + 2) % 4
    return struct.pack("<H", len(encoded)) + encoded + bytes(padding)


def _windows_filetime(path):
    stamp = path.stat().st_mtime
    value = int((stamp + 11644473600) * 10_000_000)
    return struct.pack("<Q", max(0, value))


def _header(data_offset, dir_offset, file_offset, index_size, index_crc, data_crc):
    """Produce a DSg2 Tank v1.1.0 header and 16-byte raw header pad."""
    now = dt.datetime.now(dt.timezone.utc)
    systemtime = struct.pack("<8H", now.year, now.month,
                             (now.weekday() + 1) % 7, now.day, now.hour,
                             now.minute, now.second, now.microsecond // 1000)
    header = bytearray()
    header.extend(b"DSg2Tank")
    header.extend(struct.pack("<5I", 0x00010100, dir_offset, file_offset,
                              index_size, data_offset))
    header.extend(struct.pack("<6I", 2, 0, 0, 2, 0, 0))
    header.extend(struct.pack("<2I", 0x40004000, 0))
    header.extend(b"USER")
    header.extend(uuid.uuid4().bytes_le)
    header.extend(struct.pack("<2I", index_crc, data_crc))
    header.extend(systemtime)
    for text, count in (("", 100), ("DungeonSiegeCC", 100),
                        ("DungeonSiegeCC custom resource", 100), ("DungeonSiegeCC", 40)):
        encoded = text.encode("utf-16-le")[:(count-1)*2]
        header.extend(encoded.ljust(count*2, b"\0"))
    header.extend(b"\0" * 4)  # Empty UTF-16 description NSTRING.
    if len(header) > data_offset:
        raise TankBuildError("Header exceeds data section offset")
    header.extend(bytes(data_offset - len(header)))
    return bytes(header)


def pack_directory(source, destination, *, verify=True):
    """Pack a new raw-payload DS2RES; refuses to overwrite and verifies extraction.

    The entire folder is considered user-authored tank content. Callers must
    supply an overlay folder, not the Dungeon Siege II installation itself.
    """
    root = Path(source).resolve()
    output = Path(destination)
    if not root.is_dir():
        raise TankBuildError("Choose a directory with loose mod resources")
    if output.exists():
        raise FileExistsError("Never overwrite an existing tank: " + str(output))
    entries = []
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise TankBuildError("Symlinks not supported: " + str(path))
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        for part in relative.parts:
            _name(part)
        size = path.stat().st_size
        if size > MAX_ENTRY:
            raise TankBuildError("Resource too large: " + relative.as_posix())
        total += size
        if total > MAX_TOTAL:
            raise TankBuildError("Archive exceeds 1 GiB limit")
        entries.append((relative.parts, path, size))
        if len(entries) > MAX_ENTRIES:
            raise TankBuildError("Too many resource files")
    if not entries:
        raise TankBuildError("No resource files found")
    entries.sort(key=lambda x: "/".join(x[0]).lower())
    # Preserve all path components; ensure no duplicate Windows paths.
    keys = ["/".join(x[0]).casefold() for x in entries]
    if len(set(keys)) != len(keys):
        raise TankBuildError("Case-insensitive duplicate tank paths")
    directories = {(): root}
    for parts, path, _ in entries:
        for n in range(1, len(parts)):
            key = tuple(parts[:n])
            directories[key] = root.joinpath(*key)
    all_dirs = sorted(directories, key=lambda x: (len(x), [n.lower() for n in x]))
    file_children = {key: [] for key in all_dirs}
    dir_children = {key: [] for key in all_dirs}
    for parts, path, size in entries:
        file_children[parts[:-1]].append((parts, path, size))
    for parts in all_dirs:
        if parts:
            dir_children[parts[:-1]].append(parts)
    for key in all_dirs:
        file_children[key].sort(key=lambda x: x[0][-1].casefold())
        dir_children[key].sort(key=lambda x: x[-1].casefold())

    # Relative offsets are independent of where the data section lives.
    dir_offsets = {}
    cursor = 4 + 4 * len(all_dirs)
    for key in all_dirs:
        dir_offsets[key] = cursor
        size = 16 + len(_name(key[-1] if key else ""))
        size += 4 * (len(dir_children[key]) + len(file_children[key]))
        cursor += size
    dirset_size = cursor

    # Data is streamed into the output rather than materialized in memory.
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".dscc-partial")
    if temp.exists():
        raise FileExistsError("Incomplete previous build: " + str(temp))
    # Header is 788 bytes, including zero-length WNSTRING. Add 16-byte pad.
    data_offset = 804
    metadata = {}
    data_crc = 0
    try:
        with temp.open("xb") as f:
            f.write(bytes(data_offset))
            for parts, path, size in entries:
                offset = f.tell() - data_offset
                per_file_crc = 0
                with path.open("rb") as inp:
                    while True:
                        chunk = inp.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        per_file_crc = zlib.crc32(chunk, per_file_crc)
                        data_crc = zlib.crc32(chunk, data_crc)
                metadata[parts] = (offset, size, per_file_crc & 0xffffffff)
            f.write(bytes(16))   # 16-byte raw data-to-index pad
            dir_offset = f.tell()
            file_offsets = {}
            cursor = 4 + 4 * len(entries)
            for parts, path, size in entries:
                file_offsets[parts] = cursor
                cursor += 28 + len(_name(parts[-1]))
            fileset_size = cursor
            file_offset = dir_offset + dirset_size

            dirset = bytearray()
            dirset.extend(struct.pack("<I", len(all_dirs)))
            for key in all_dirs:
                dirset.extend(struct.pack("<I", dir_offsets[key]))
            for key in all_dirs:
                parent = dir_offsets.get(key[:-1], 0) if key else 0
                children = [(parts[-1], dir_offsets[parts]) for parts in dir_children[key]]
                children.extend((parts[-1],
                    dirset_size + file_offsets[parts]) for parts, _path, _sz in file_children[key])
                children.sort(key=lambda x: x[0].casefold())
                dirset.extend(struct.pack("<II", parent, len(children)))
                dirset.extend(_windows_filetime(directories[key]))
                dirset.extend(_name(key[-1] if key else ""))
                for _name_value, ref in children:
                    dirset.extend(struct.pack("<I", ref))
            if len(dirset) != dirset_size:
                raise TankBuildError("Directory index size mismatch")

            fileset = bytearray()
            fileset.extend(struct.pack("<I", len(entries)))
            for parts, _path, _sz in entries:
                fileset.extend(struct.pack("<I", file_offsets[parts]))
            for parts, path, _sz in entries:
                offset, size, crc = metadata[parts]
                fileset.extend(struct.pack("<4I", dir_offsets[parts[:-1]], size, offset, crc))
                fileset.extend(_windows_filetime(path))
                fileset.extend(struct.pack("<HH", 0, 0))
                fileset.extend(_name(parts[-1]))
            if len(fileset) != fileset_size:
                raise TankBuildError("File index size mismatch")

            index = dirset + fileset
            f.write(index)
            f.seek(0)
            f.write(_header(data_offset, dir_offset, file_offset,
                            len(index), zlib.crc32(index), data_crc))
        # Read-back verification checks the same index/parser used for the
        # user's licensed archives, plus bytes (and CRC) of every output file.
        if verify:
            unpacked = Tank(temp)
            if len(unpacked.entries) != len(entries):
                raise TankBuildError("Read-back file count mismatch")
            for parts, path, _size in entries:
                name = "/".join(parts)
                original = path.read_bytes()
                emitted = unpacked.read_file(name)
                if emitted != original or zlib.crc32(emitted) != metadata[parts][2]:
                    raise TankBuildError("Read-back failed: " + name)
        temp.replace(output)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return {"path": str(output), "files": len(entries), "bytes": total,
            "verification": "read_back_passed" if verify else "not_verified",
            "gameplay_tested": False}
