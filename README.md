# DungeonSiegeCC — development source v0.3.0

**This repository does not yet produce playable custom MMD companions for Dungeon Siege II.** The editor, source export, GAS template staging and bootstrap installation are implemented. The game's proprietary ASP/PRS conversion and map placement / recruitment runtime are not. Do not distribute as a finished companion framework.

## Run the Windows importer

1. Download the **repository ZIP** (Code > Download ZIP) or clone it.
2. Extract the whole folder, not only the launcher.
3. Run `START_WINDOWS.bat` with Python 3.10 or newer (Tkinter included).
4. When prompted, select the directory containing `DungeonSiege2.exe`.
5. If framework files are missing/damaged, accept the **scaffold** installation; these are not in-game gameplay files.

The game path is saved under `%APPDATA%\DungeonSiegeCC\settings.json`. Character files are not removed during framework repair.

## MMD model and animation pipeline

- The application reads PMX 2.0/2.1 meshes, UVs, material references, rig hierarchy and bone labels directly, without pip dependencies.
- PMX geometry can be exported as a **neutral OBJ/MTL**, alongside a bone hierarchy JSON file and referenced texture copies. This is *not* a skinned ASP mesh.
- PMD headers are inspected; full PMD geometry conversion requires converting the model to PMX first.
- Custom VMD v1/v2 bone tracks can be inspected and exported to intermediate motion JSON. The JSON retains quaternion keys and VMD interpolation bytes at 30 FPS, but it is **not a PRS file**.
- Each animation slot defaults to **native DS2**. Override one slot by selecting **custom** and pointing to a VMD file. Every other slot remains native in the project definition. The project format does not itself perform game-native rig retargeting.
- Export Source Package creates a copy of model and requested VMD sources plus the neutral intermediates. No game resource archive is generated.

## Optional game-template overlay

If you have **extracted your own** `Logic.ds2res` with DS2 toolkit's Tank Viewer/DS2 Tank Editor, set **Extracted Logic GAS folder** and select a **DS2 donor actor ID** in the editor. The tool verifies that donor exists in the extracted .gas templates, then creates `game_overlay/world/contentdb/templates/regular/actors/good/dscc_<id>.gas` specializing it. This is a **template only**, not a spawned recruitable NPC. Its validity depends on the actual game version and base template schema.

The export's `GAME_BUILD_REQUIREMENTS.json` enumerates remaining engine work: model rig, animations, map placement, conversation/recruitment, tank packaging and in-game verification. You can manually package verified GAS files with the DS2 Toolkit, <https://www.siegetheday.org/?q=node/1437> or <https://github.com/PartakithRC1/TankEditor>. Do **not** republish another mod author's copyrighted assets without permission.

## Updates and releases

The source installer checks the latest GitHub Release and offers an **opt-in** download of its `DungeonSiegeCC-Windows.zip` release asset when newer. It stages a validated archive and replaces only application files after exit, leaving profiles, game data and installed characters untouched. The `.github/workflows/release.yml` workflow can publish a source release when a `v*` tag is pushed or when triggered manually with a version.

**Privacy limitation:** The repository is currently **private**. Anonymous release queries cannot see it. For your private development environment, optionally configure the read-only environment variable `DUNGEONSIEGECC_GITHUB_TOKEN` (do not commit or embed a token). Public releases should be distributed from a public repository; the GUI does not bypass GitHub permissions. Packaged-EXE updates are not implemented.

## Automated tests

```powershell
py -3 -m py_compile importer.py manager.py update_helper.py mmd_assets.py game_pipeline.py
py -3 -m unittest discover -s tests -v
```

GitHub Actions tests Python 3.11 and 3.14 on Windows. Passing tests verify source parsing, staging, integrity and update logic; they **do not** prove runtime compatibility with Dungeon Siege II.

## Required for a real playable release

A lawful installation and version-specific game resources are essential for validating the native animation rig and files. In particular, engineering remains for **PMX skin-weight/skeleton retargeting → ASP export**, **VMD/DS2 animation retargeting → PRS** (with events), DS2-specific **GAS/Skrit recruitment & map placement**, **.ds2res tank generation**, collision/compatibility testing, and real in-game party recruiting, combat and save/load checks.

Technical references: [Siege University — Characters](https://dungeonsiege.fandom.com/wiki/Guide:_Siege_University_-_214:_Siege_Max:_Characters), [Siege University — NPCs](https://dungeonsiege.fandom.com/wiki/Guide:_Siege_University_-_208a:_Non-Player_Characters), and [DS2 Tank Editor](https://github.com/PartakithRC1/TankEditor).
