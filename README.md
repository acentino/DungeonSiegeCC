# DungeonSiegeCC

Dungeon Siege II MMD Companion Importer, v0.2.0 (development).

The Windows/Python desktop importer supports PMX/PMD source profiles, per-animation VMD overrides, and source package staging. Its new first-run game-folder wizard saves the game directory, verifies a **bundled framework scaffold** by SHA-256, and asks to install or repair missing/outdated files. The framework is bundled for offline installation. The application checks the GitHub latest release for tool updates and offers an opt-in update.

**Important:** This is not yet an engine-functional companion mod. ASP/PRS conversion, GAS/Skrit recruitment logic, and DS2 resource-tank packaging remain to be implemented. Bundled framework v0.2.0 consists of verified bootstrap metadata/readme, not gameplay hooks.

## Source snapshot

The complete tested v0.2.0 source archive is available as a downloadable artifact in the ChatGPT conversation where it was produced. The repository currently contains setup metadata; remaining source files need to be imported from that archive.

## Release convention

Publish tagged releases with an asset named `DungeonSiegeCC-Windows.zip` containing `importer.py`, `manager.py`, `update_helper.py`, `START_WINDOWS.bat`, `framework_bundle/`, and `README.md` at archive root. The updater uses this asset for opt-in in-app updates.

Python 3.10+ required. Run `python -m unittest discover -s tests -v` for local tests. Never bundle copyrighted game files.
