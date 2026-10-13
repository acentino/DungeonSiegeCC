"""Local-only inspector for Dungeon Siege II archives and zipped MMD assets.

No game or model data is uploaded. File types are inspected without extracting
the potentially large resource tanks.
"""
from __future__ import annotations
import json
import os
import re
import stat
import struct
import zipfile
from pathlib import Path

TANK_NAMES = {"logic.ds2res", "objects.ds2res", "terrain.ds2res", "language.ds2res",
              "voices.ds2res", "sound1.ds2res", "sound2.ds2res", "movies1.ds2res", "movies2.ds2res"}
ALLOWED_MMD = {".pmx",".pmd",".vmd",".png",".jpg",".jpeg",".bmp",".tga",".dds",".spa",".sph",".psd",".txt",".json"}
MAX_FILES = 25000
MAX_UNCOMPRESSED = 1_500_000_000

class AssetProbeError(ValueError):
    pass

def tank_header(path):
    """Read only the uncompressed header. No DS2RES extraction or repacking."""
    path = Path(path)
    size = path.stat().st_size
    with path.open("rb") as file:
        data = file.read(96)
    if len(data) < 28:
        raise AssetProbeError("Tank header is truncated")
    product, tag = data[:4], data[4:8]
    if tag != b"Tank" or product not in (b"DSg2", b"DSig"):
        raise AssetProbeError("Not a recognized Dungeon Siege tank (DSg2/DSig + Tank)")
    header_version, dir_offset, file_offset, index_size, data_offset = struct.unpack_from("<5I",data,8)
    for off in (dir_offset, file_offset, data_offset):
        if off > size:
            raise AssetProbeError("Archive header points past end of file")
    return {
        "name":path.name, "size_bytes":size,
        "product":product.decode("ascii"),"header_version":header_version,
        "dir_index_offset":dir_offset, "file_index_offset":file_offset,
        "index_size":index_size, "data_offset":data_offset,
        "valid_basic_header":True
    }

def scan_game_archives(game_dir):
    root=Path(game_dir)
    folders=[root/"Resources",root/"resources",root]
    resource=next((p for p in folders if p.is_dir() and any(p.glob("*.ds2res"))),None)
    if resource is None:
        raise AssetProbeError("No .ds2res resource files found in the game folder")
    entries=[]
    for file in sorted(resource.iterdir(),key=lambda p:p.name.lower()):
        if not file.is_file() or file.suffix.lower()!=".ds2res":
            continue
        try:entries.append(tank_header(file))
        except (OSError,AssetProbeError) as error:
            entries.append({"name":file.name,"error":str(error)})
    found={entry["name"].lower() for entry in entries}
    return {"resource_directory":str(resource),"archive_count":len(entries),
            "core_logic_found":"logic.ds2res" in found,
            "core_objects_found":"objects.ds2res" in found,
            "archives":entries,
            "note":"Headers only. Internal GAS/ASP/PRS data has NOT been extracted or inspected."}

def safe_member_path(info):
    name=info.filename.replace("\\","/")
    if re.match(r"^[A-Za-z]:",name) or name.startswith(("/","//")) or "\x00" in name:
        raise AssetProbeError("Absolute ZIP archive entry path: "+repr(name))
    parts=name.split("/")
    if any(part in ("","..",".") for part in parts[:-1]) or ".." in parts:
        raise AssetProbeError("Unsafe ZIP archive entry path: "+repr(name))
    if not parts[-1] and info.is_dir():
        parts=parts[:-1]
    if not parts or any(part in ("",".","..") for part in parts):
        raise AssetProbeError("Invalid ZIP archive member name")
    if (info.external_attr>>16)&0o170000 == 0o120000:
        raise AssetProbeError("ZIP symlinks are unsupported")
    if len(parts)>32 or len(name)>500:
        raise AssetProbeError("ZIP path too long")
    return Path(*parts)

def _inventory(path):
    path=Path(path)
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist()
        if len(infos)>MAX_FILES:
            raise AssetProbeError("Archive contains too many entries")
        total=sum(x.file_size for x in infos)
        if total>MAX_UNCOMPRESSED:
            raise AssetProbeError("Archive expands beyond configured safety limit")
        members=[]
        for item in infos:
            rel=safe_member_path(item)
            if item.is_dir():continue
            members.append((item,rel))
        return members

def scan_mmd_zip(path):
    zip_path=Path(path)
    with zipfile.ZipFile(zip_path) as archive:
        infos=archive.infolist()
        if len(infos)>MAX_FILES or sum(x.file_size for x in infos)>MAX_UNCOMPRESSED:
            raise AssetProbeError("MMD archive exceeds configured safety limits")
        models,motions,textures,skipped=[],[],[],[]
        for info in infos:
            rel=safe_member_path(info)
            if info.is_dir():continue
            entry={"path":rel.as_posix(),"size_bytes":info.file_size}
            suffix=rel.suffix.lower()
            if suffix in (".pmx",".pmd"):
                with archive.open(info) as stream:
                    signature=stream.read(4)
                valid=(suffix==".pmx" and signature==b"PMX ") or (suffix==".pmd" and signature[:3]==b"Pmd")
                entry["recognized_signature"]=valid
                models.append(entry)
            elif suffix==".vmd": motions.append(entry)
            elif suffix in ALLOWED_MMD and suffix not in {".json",".txt"}: textures.append(entry)
            else:skipped.append(entry)
        return {"archive_name":zip_path.name,"archive_size_bytes":zip_path.stat().st_size,
                "model_count":len(models),"models":models,
                "motion_count":len(motions),"motions":motions,
                "texture_count":len(textures),"texture_examples":textures[:30],
                "skipped_count":len(skipped),
                "note":"Archive index and model signatures verified locally. No PMX rig retargeting performed."}

def extract_mmd_zip(path,destination):
    """Safely unpack supported MMD assets to a *new* folder. Never overwrite."""
    path=Path(path)
    dest=Path(destination)
    if dest.exists():
        raise FileExistsError("Extraction destination already exists: "+str(dest))
    dest.mkdir(parents=True)
    extracted=[]
    try:
        with zipfile.ZipFile(path) as archive:
            infos=archive.infolist()
            if len(infos)>MAX_FILES or sum(x.file_size for x in infos)>MAX_UNCOMPRESSED:
                raise AssetProbeError("Archive exceeds safety limits")
            for info in infos:
                rel=safe_member_path(info)
                if info.is_dir() or rel.suffix.lower() not in ALLOWED_MMD:
                    continue
                # Preserve nested model/texture references without path traversal.
                output=dest/rel
                output.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(info) as src, output.open("wb") as dst:
                    left=info.file_size
                    while left:
                        chunk=src.read(min(1024*1024,left))
                        if not chunk:raise AssetProbeError("Unexpected end of ZIP entry")
                        dst.write(chunk)
                        left-=len(chunk)
                extracted.append(rel.as_posix())
        return {"destination":str(dest),"extracted_count":len(extracted),
                "models":[str(dest/p) for p in extracted if Path(p).suffix.lower() in (".pmx",".pmd")],
                "motions":[str(dest/p) for p in extracted if Path(p).suffix.lower()==".vmd"]}
    except Exception:
        import shutil
        shutil.rmtree(dest,ignore_errors=True)
        raise

def write_report(payload, output):
    Path(output).write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8")
    return output

if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(description="Scan local DS2 archives or MMD ZIP. NEVER uploads data.")
    parser.add_argument("--game",help="Path containing DungeonSiege2.exe and Resources/")
    parser.add_argument("--mmd-zip",help="Path to a zipped PMX/PMD model")
    parser.add_argument("--report",default="asset_report.json")
    parser.add_argument("--extract-to",help="Optional empty destination for MMD extraction")
    args=parser.parse_args()
    if not (args.game or args.mmd_zip):parser.error("Provide --game and/or --mmd-zip")
    report={}
    if args.game: report["game"]=scan_game_archives(args.game)
    if args.mmd_zip:
        report["mmd"]=scan_mmd_zip(args.mmd_zip)
        if args.extract_to:report["extraction"]=extract_mmd_zip(args.mmd_zip,args.extract_to)
    print(write_report(report,args.report))
