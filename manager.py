"""Game setup, framework integrity and GitHub release discovery."""
import hashlib
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

VERSION = "0.2.0"
REPO = "acentino/DungeonSiegeCC"
FRAMEWORK_DIR = "DungeonSiegeCC"

def app_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

def settings_path():
    return Path(os.getenv("APPDATA") or (Path.home()/".config"))/"DungeonSiegeCC"/"settings.json"

def load_settings(path=None):
    try:
        p=Path(path) if path else settings_path()
        value=json.loads(p.read_text(encoding="utf-8"))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def save_settings(data,path=None):
    p=Path(path) if path else settings_path()
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,indent=2),encoding="utf-8")
    tmp.replace(p)

def valid_game_folder(folder):
    p=Path(folder)
    return p.is_dir() and (p/"DungeonSiege2.exe").is_file()

def sha256(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()

def bundled_manifest(bundle_root=None):
    root=Path(bundle_root) if bundle_root else app_root()/"framework_bundle"
    manifest=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    files=manifest.get("files")
    if not isinstance(files,dict) or not files:raise ValueError("Empty framework manifest")
    for name,digest in files.items():
        path=Path(name)
        if path.is_absolute() or ".." in path.parts or path.as_posix()!=name or not isinstance(digest,str):
            raise ValueError("Invalid manifest path: "+name)
        if not (root/path).is_file() or sha256(root/path)!=digest:
            raise ValueError("Bundled framework integrity check failed: "+name)
    return manifest

def framework_status(game,bundle_root=None):
    if not valid_game_folder(game):return "invalid_game"
    manifest=bundled_manifest(bundle_root)
    dest=Path(game)/FRAMEWORK_DIR
    statefile=dest/"installed.json"
    if not statefile.is_file():return "missing"
    try:state=json.loads(statefile.read_text(encoding="utf-8"))
    except (ValueError,OSError):return "repair"
    if state.get("version")!=manifest.get("version"):return "outdated"
    for name,digest in manifest["files"].items():
        f=dest/name
        if not f.is_file() or sha256(f)!=digest:return "repair"
    return "installed"

def install_framework(game,bundle_root=None):
    if not valid_game_folder(game):raise ValueError("Choose a folder containing DungeonSiege2.exe")
    root=Path(bundle_root) if bundle_root else app_root()/"framework_bundle"
    manifest=bundled_manifest(root)
    dest=Path(game)/FRAMEWORK_DIR
    dest.mkdir(parents=True,exist_ok=True)
    for name,digest in manifest["files"].items():
        target=dest/name
        target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_name(target.name+".dscc-new")
        shutil.copyfile(root/name,temp)
        if sha256(temp)!=digest:
            temp.unlink(missing_ok=True)
            raise ValueError("Copy verification failed: "+name)
        temp.replace(target)
    state={"version":manifest["version"],"files":manifest["files"],"scope":"scaffolding-only"}
    temp=dest/"installed.json.tmp"
    temp.write_text(json.dumps(state,indent=2),encoding="utf-8")
    temp.replace(dest/"installed.json")
    return dest

def version_tuple(value):
    return tuple(int(part) for part in value.lstrip("v").split("."))

def latest_release(opener=None):
    url="https://api.github.com/repos/"+REPO+"/releases/latest"
    req=urllib.request.Request(url,headers={"User-Agent":"DungeonSiegeCC/"+VERSION,"Accept":"application/vnd.github+json"})
    opener=opener or urllib.request.urlopen
    with opener(req,timeout=8) as response:release=json.load(response)
    tag=release["tag_name"]
    if not isinstance(tag,str) or len(tag)>40:raise ValueError("Invalid version")
    asset=next((a for a in release.get("assets",[]) if a.get("name")=="DungeonSiegeCC-Windows.zip"),None)
    return {"version":tag,"newer":version_tuple(tag)>version_tuple(VERSION),"download_url":asset.get("browser_download_url") if asset else None,"page":release.get("html_url","https://github.com/"+REPO+"/releases")}
