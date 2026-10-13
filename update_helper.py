"""Standalone updater: run from a temporary staging folder after the GUI exits.

Only known program files are replaced; profiles, user directories, and
installed game characters are never modified.
"""
import os
import shutil
import sys
import time
from pathlib import Path

FILES = ("importer.py", "manager.py", "update_helper.py", "mmd_assets.py", "game_pipeline.py", "README.md", "START_WINDOWS.bat")
OPTIONAL = ("updater.py",)

def wait_for_exit(pid, seconds=30):
    if os.name != "nt":
        return
    import ctypes
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x00100000, False, int(pid))
    if handle:
        try:
            if kernel.WaitForSingleObject(handle, int(seconds * 1000)) == 0x102:
                raise TimeoutError("Importer did not close")
        finally:
            kernel.CloseHandle(handle)

def apply_update(source, target, previous_pid=None):
    source, target = Path(source).resolve(), Path(target).resolve()
    if not (source / "importer.py").is_file() or not (source / "manager.py").is_file():
        raise ValueError("Incomplete update package")
    if not (source / "framework_bundle" / "manifest.json").is_file():
        raise ValueError("Framework bundle missing from update")
    if previous_pid is not None:
        wait_for_exit(previous_pid)
    from manager import bundled_manifest
    bundled_manifest(source / "framework_bundle")
    names = [name for name in FILES if (source / name).is_file()]
    names += [name for name in OPTIONAL if (source / name).is_file()]
    names += [str(path.relative_to(source)) for path in (source / "framework_bundle").rglob("*") if path.is_file()]
    backup = source / "_backup"
    replaced = []
    try:
        for name in names:
            src, dst = source / name, target / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            previous = backup / name
            if dst.is_file():
                previous.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, previous)
            temp = dst.with_name(dst.name + ".dscc-new")
            shutil.copy2(src, temp)
            temp.replace(dst)
            replaced.append((dst, previous))
    except Exception:
        for dst, previous in reversed(replaced):
            if previous.is_file():
                shutil.copy2(previous, dst)
            else:
                dst.unlink(missing_ok=True)
        raise
    finally:
        for name in names:
            (target / name).with_name(Path(name).name + ".dscc-new").unlink(missing_ok=True)
    # Leave staging intact for diagnostics if a failure occurs; otherwise remove.
    if source.name == "staged" and source.parent.name.startswith("dscc_stage_"):
        shutil.rmtree(source.parent, ignore_errors=True)
    return len(replaced)

if __name__ == "__main__":
    try:
        apply_update(*sys.argv[1:4])
    except Exception as exc:
        Path.home().joinpath("DungeonSiegeCC-update-error.txt").write_text(str(exc), encoding="utf-8")
        raise
