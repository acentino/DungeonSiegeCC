# DungeonSiegeCC

Windows desktop source editor for Dungeon Siege II MMD recruitable-character projects.

## Launch

Install Python 3.10 or newer and run `START_WINDOWS.bat` from the **repository root**. It launches `importer.py`, which is committed alongside `manager.py` and `update_helper.py`.

## Setup and bundled framework

On first run, choose the directory containing `DungeonSiege2.exe`. The game path is saved in `%APPDATA%\\DungeonSiegeCC\\settings.json`.

The application checks the SHA-256 hashes and version of the bundled `framework_bundle/` files. When missing, outdated or damaged, it asks whether to install or repair them in `<game>/DungeonSiegeCC/`. Existing character files are not deleted.

**Current framework files are a bootstrap scaffold only. They are not functional gameplay mods.** No original game binaries are bundled.

## Companion configuration

Select a PMX/PMD source model, define companion metadata, and individually choose game-default or custom VMD animations for each slot. Projects can be saved as JSON and source assets exported. Export **does not** convert PMX/PMD to Dungeon Siege II ASP, retarget motions to PRS, or create a playable .ds2res. Recruitment scripts and actual in-game character installation are not implemented yet.

## Updates

The application queries the latest GitHub Release and offers to open the release page if a newer version exists. **Automated in-place downloads and upgrades are not implemented in the current GitHub application**. The `update_helper.py` module is present for a future update pipeline. The framework bundle is included in the repository and doesn't rely on GitHub being online.

## Tests

Run `python -m unittest discover -s tests -v` in the repository root.

## Files

- `importer.py`: Windows Tkinter desktop editor
- `manager.py`: game path settings, framework integrity, installation, release version discovery
- `update_helper.py`: staging file replacement helper (not yet wired into GUI)
- `framework_bundle/`: offline versioned bootstrap files
- `tests/`: unit tests

The GUI implementation committed here is a streamlined working implementation of the earlier v0.2.0 prototype, not byte-for-byte identical to the previously provided ZIP.
