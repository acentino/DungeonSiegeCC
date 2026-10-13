# DungeonSiegeCC v0.3.0 (development)

**Status:** An MMD companion **project editor and source packager**, not yet a playable Dungeon Siege II companion mod or finished character converter. ASP/PRS conversion, VMD retargeting, GAS/Skrit recruitment scripts, and real framework runtime remain unimplemented. The bundled framework is currently an offline-installable **scaffold**, not gameplay support.

## Installation (Windows)

1. In GitHub choose **Code > Download ZIP** and **Extract All**, or clone this repository.
2. Open the extracted repository folder and double-click `START_WINDOWS.bat`. `importer.py`, `manager.py` and `update_helper.py` must be in the **same folder** as the launcher.
3. Requires Python 3.10+ with Tkinter. No pip dependencies.

For troubleshooting, open a terminal in the extracted folder and run `py -3 importer.py`.

## Game location & bundled framework

On the first launch, choose the folder containing `DungeonSiege2.exe`. The path is saved in `%APPDATA%\\DungeonSiegeCC\\settings.json`. The launcher asks to install/repair the bundled framework scaffold only if files are missing, outdated or damaged. It checks a SHA-256 manifest and only replaces **its own managed files** under `<game>/DungeonSiegeCC/`. It does **not** delete character files, user projects or pre-existing resources. The package contains framework files, allowing offline repair.

## Characters and animation choices

Create a companion profile with PMX/PMD model paths and recruitment metadata. Per-animation, select `native` (the default) or a single `.vmd` override. Save/open profiles and export model/motion **source staging packages**. These are **not playable DS2 mods**; compatibility with DS2 animations and models requires a verified skeleton and format converter.

## Updates

For GitHub Release tags newer than this tool's version, the desktop app prompts to download the `DungeonSiegeCC-Windows.zip` asset. When accepted, the Python-source version downloads, checks and stages it, then launches the updater after the app exits. It replaces **only managed tool files** and bundled framework files; it does not touch game installs, custom characters, or saved profiles. There is no download if the tool is already current. Packaged EXE updates remain unsupported.

**Private repository limitation:** This repository is currently **private**. Anonymous GitHub release API calls return 404. For private development, set a GitHub fine-grained read-only personal access token in the environment variable `DUNGEONSIEGECC_GITHUB_TOKEN` before launching the importer; **never put your token in this repository or character projects**. For distribution to normal users, publish the releases through a public repository or make this repository public.

**Publishing releases:** GitHub Actions includes `.github/workflows/release.yml`. Under **Actions > Publish Windows source release > Run workflow**, enter a version such as `v0.3.0`. The workflow runs tests and packages the source and the complete bundled framework scaffold as `DungeonSiegeCC-Windows.zip`. Alternatively, pushing a `v*` tag triggers the workflow. Ensure GitHub Actions are enabled and workflow permissions allow writing releases. Releases generated while the repo is private remain private.

## Test

```powershell
py -3 -m unittest discover -s tests -v
```

Windows CI tests run on Python 3.11 and 3.14. Results must be inspected in GitHub Actions; successful commits alone are not evidence that the GUI runs correctly.

## Repository files

- `importer.py`: Windows Tkinter project editor and update prompt
- `manager.py`: settings, framework validation/installation, release discovery and staging
- `update_helper.py`: post-exit application file replacement, backup and rollback
- `framework_bundle/`: packaged offline bootstrap assets; currently scaffold-only
- `tests/`: automated tests for project editing, framework installation and updates
- `.github/workflows/`: CI and release packaging

No copyrighted Dungeon Siege II original game assets are bundled.
