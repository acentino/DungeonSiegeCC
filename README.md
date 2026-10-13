# DungeonSiegeCC — development source v0.3.6

**This repository does not yet produce playable custom MMD companions for Dungeon Siege II.** The editor, source export, GAS template staging and bootstrap installation are implemented. The game's proprietary ASP/PRS conversion and map placement / recruitment runtime are not. Do not distribute as a finished companion framework.

## Automatic checks on every startup (v0.3.2)

Every time the Windows tool opens, it **immediately starts a GitHub Release check**
in a non-blocking background thread and performs a **local game/framework integrity check**.
The framework check uses its bundled SHA-256 manifest and saved game location.
Missing, outdated, or damaged managed framework files trigger an install/repair
prompt; healthy installations do not prompt or rewrite files.

The two startup checks do not show overlapping dialogs. A newer published
release prompts for an optional download. If you accept, the tool installs
its own files after closing and **automatically reopens the updated importer**;
the restarted app checks its bundled framework again. Offline operation is
supported: network failure does not prevent local framework verification.
The **Check for updates** and **Framework status / install** buttons remain
available for manual checks.

**Important:** The bundled framework is still a source/metadata scaffold,
not a playable Dungeon Siege II companion runtime.

## Run the Windows importer

1. Download the **repository ZIP** (Code > Download ZIP) or clone it.
2. Extract the whole folder, not only the launcher.
3. Run `START_WINDOWS.bat` with Python 3.10 or newer (Tkinter included).
4. When prompted, select the directory containing `DungeonSiege2.exe`.
5. If framework files are missing/damaged, accept the **scaffold** installation; these are not in-game gameplay files.

The game path is saved under `%APPDATA%\DungeonSiegeCC\settings.json`. Character files are not removed during framework repair.

## Logic donor discovery with zero base_pm matches (v0.3.6)

The original analyzer only counted templates inheriting from `base_pm`.
An extracted Logic archive can contain thousands of valid templates without
any `base_pm`-derived entries; **0 matches did not mean 0 usable actors**.

Re-analyzing the same ZIP now provides two separate categories:
- `potential_recruitable`: `base_pm` lineage matches, retained for
  compatibility. These were never confirmed recruitable in-game.
- `donor_candidates`: scored actor-template prospects inferred from the GAS
  file path (`actors/good`, `characters` etc.), ancestry names, dialogue
  jobs, displayed names and `can_sell_self` properties. Each includes
  `donor_score`, explanatory `donor_reasons`, and ancestor-chain metadata.

The expanded `logic_template_report.json` also contains diagnostic samples
for missing specializations and root ancestry. If no actor-like template is
identified, it shows the template examples and missing parents rather than
claiming that the archive contains no NPCs. Scores are **heuristics**, not
evidence of functioning recruitment. You can still manually enter any
verified donor template ID from the archive.

## Direct Logic reference ZIP analysis (v0.3.5)

The **Analyze Logic reference ZIP** button accepts the ZIP produced by
**Extract Logic GAS/Skrit**, without first extracting it manually. Select a
user-owned reference archive and the importer identifies template definitions,
`specializes` inheritance, names, optional hiring cost, talk jobs and
potential `base_pm` descendants. You can select one as the donor for a
character source package; donor validation can now read ZIP entries directly.

A report is written to
`%APPDATA%\\DungeonSiegeCC\\logic_template_report.json`. The report
contains **metadata only**, not the original GAS source contents.

**Important:** An actor inherited from `base_pm` is only a **potential
hireable template**. This does not prove it is spawned in a particular map or
can be recruited there. Player-party integration, rig export, and in-game
save/load verification remain unfinished.

Command-line usage:

```powershell
py -3 logic_inspector.py "C:\\References\\DungeonSiegeCC_logic_references.zip" --report "logic_template_report.json"
```

We do not publish the original game scripts or extracted models in GitHub.

## Deep local Tank inspection and selective reference extraction (v0.3.4)

This release introduces a **read-only DS2 Tank parser** (`ds2_tank.py`),
which inspects the actual contents of `Logic.ds2res` and
`Objects.ds2res` on the user's computer. The previous header-only scan
is enhanced with local file counts and examples of GAS, ASP, and PRS
filenames; the JSON report remains under
`%APPDATA%\\DungeonSiegeCC\\local_asset_report.json`.

Use **Extract Logic GAS/Skrit** to create a new reference directory containing
the scripts and templates from your own game. The importer selects that
directory for donor-template lookup. Use **Extract filtered ASP/PRS** to
extract only model/animation resources whose internal path contains the term
you enter (for example, `hero`, `female`, `fs0`). If you are unsure of
the names, inspect local archives first and check example paths in the JSON.
Each extraction gets a new output directory and a report of skipped entries.

Currently supported payload formats: **uncompressed and zlib/deflate**,
including chunked zlib. **LZO is not yet supported**, and those files are
reported as failures instead of writing bogus asset data. The parser has been
tested using synthetic DSg2 tank fixtures. It has **not** been validated
against every production Dungeon Siege II tank variant, so do not infer
game compatibility from the automated tests. No game-owned resource archive,
asset, texture, or MMD character file is added to this public repository.

Manual CLI (Windows PowerShell):

```powershell
py -3 ds2_tank.py "C:\\Games\\Dungeon Siege II\\Resources\\Logic.ds2res" --index
py -3 ds2_tank.py "C:\\Games\\Dungeon Siege II\\Resources\\Logic.ds2res" --extract-to "C:\\DSCC\\LogicReferences" --suffix .gas
```

The archive reader is a **reference-extraction milestone**, not the actual
ASP skin exporter, PRS retargeter, or recruitable-NPC game runtime.

## Local archive inspection and importing a character ZIP (v0.3.3)

Use **Inspect local game archives** to inventory the game's `Resources/*.ds2res`
and validate basic Tank header offsets. This reads only the archive headers,
**not the compressed files inside**. Core `Logic.ds2res` and
`Objects.ds2res` are identified; a JSON report is saved in
`%APPDATA%\\DungeonSiegeCC\\local_asset_report.json`.
This report stays on your PC. No original game file is sent to GitHub or copied
into the framework.

Use **Import MMD model ZIP** to inspect models (.pmx/.pmd), motion (.vmd),
and texture filenames *without extracting*. On confirmation, select a parent
directory: supported asset files are extracted into a fresh
`<ZipName>_MMD` subdirectory, leaving the ZIP untouched. Unsafe paths
and symlinks are blocked. If the archive contains only one PMX/PMD, it is
selected in the importer automatically. Existing directories are never
overwritten. The tool will not unpack copyrighted game tanks or import
skinned assets into the DS2 engine yet.

A command-line report is also available:

```powershell
py -3 asset_probe.py --game "C:\\Games\\Dungeon Siege II" --mmd-zip "C:\\Models\\Dalvi MMD.zip" --report "asset_report.json"
```

If you need a complete asset inventory, use your own licensed game data and a
compatible DS2 Tank Viewer locally. This scan intentionally **does not claim**
it can decrypt, extract, or repack DS2 resources.

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

At startup and when manually requested, the source installer checks the latest GitHub Release and offers an **opt-in** download of its `DungeonSiegeCC-Windows.zip` release asset when newer. It stages a validated archive and replaces only application files after exit and automatically relaunches the importer, leaving profiles, game data and installed characters untouched. The `.github/workflows/release.yml` workflow can publish a source release when a `v*` tag is pushed or when triggered manually with a version.

**Public repository:** No GitHub token is required to check or download public releases. Updates require a published GitHub Release containing `DungeonSiegeCC-Windows.zip`; a commit on `main` alone does not trigger an update prompt. To publish a new release, update `manager.VERSION`, `RELEASE_VERSION` and the release workflow tag together. Packaged-EXE updates are not implemented.

## Automated tests

```powershell
py -3 -m py_compile importer.py manager.py update_helper.py mmd_assets.py game_pipeline.py asset_probe.py ds2_tank.py logic_inspector.py
py -3 -m unittest discover -s tests -v
```

GitHub Actions tests Python 3.11 and 3.14 on Windows. Passing tests verify source parsing, staging, integrity and update logic; they **do not** prove runtime compatibility with Dungeon Siege II.

## Required for a real playable release

A lawful installation and version-specific game resources are essential for validating the native animation rig and files. In particular, engineering remains for **PMX skin-weight/skeleton retargeting → ASP export**, **VMD/DS2 animation retargeting → PRS** (with events), DS2-specific **GAS/Skrit recruitment & map placement**, **.ds2res tank generation**, collision/compatibility testing, and real in-game party recruiting, combat and save/load checks.

Technical references: [Siege University — Characters](https://dungeonsiege.fandom.com/wiki/Guide:_Siege_University_-_214:_Siege_Max:_Characters), [Siege University — NPCs](https://dungeonsiege.fandom.com/wiki/Guide:_Siege_University_-_208a:_Non-Player_Characters), and [DS2 Tank Editor](https://github.com/PartakithRC1/TankEditor).
