"""Apply a downloaded source update after the application exits."""
import os
import shutil
import sys
import time
from pathlib import Path

def apply_update(source,target,previous_pid):
    source,target=Path(source),Path(target)
    if not (source/"importer.py").is_file():
        raise ValueError("Invalid update staging")
    if os.name=="nt":
        import ctypes
        for _ in range(100):
            handle=ctypes.windll.kernel32.OpenProcess(0x100000,False,int(previous_pid))
            if not handle:break
            ctypes.windll.kernel32.CloseHandle(handle)
            time.sleep(.2)
    for name in ("importer.py","manager.py","update_helper.py","README.md","START_WINDOWS.bat"):
        src=source/name
        if src.exists():shutil.copy2(src,target/name)
    if (source/"framework_bundle").exists():
        dest=target/"framework_bundle"
        dest.mkdir(exist_ok=True)
        for item in (source/"framework_bundle").rglob("*"):
            if item.is_file():
                out=dest/item.relative_to(source/"framework_bundle")
                out.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(item,out)
    shutil.rmtree(source,ignore_errors=True)

if __name__=="__main__":
    apply_update(*sys.argv[1:4])
