# Release packages

Armory is released in three packages. All are built locally by `package.py` into `dist/`, from an allowlist, and scanned
for personal data before they are written. Nothing is uploaded automatically.

## 1. Steam Workshop - data-only mod shell (partial)
- Contents: `mod.info`, an empty or placeholder `resource/` and `localizations/`, plus the Workshop description
  (`workshop/description.bbcode`).
- No Python, no native code, no generated breeds, no game data.
- Purpose: a discoverable listing that explains Armory and points to the separate download. The generated mod
  (`armory_breeds`) is created on the player's PC by the app.

## 2. Nexus Mods - runnable app release (partial)
- Contents: the app only: `server.py`, `savefile.py`, `loadout.py`, `catalog.py`, `breeds.py`, `identity.py`, `perks.py`,
  `config.py`, `version.py`, `start_armory.bat`, `web/`, `README.md`, `LICENSE`, `CHANGELOG.md`.
- Excluded: tests, fixtures, developer scripts (`make_*`, `slice.py`, `validate_catalog.py`), `docs/`, `catalog.json`,
  `config.json`, `backups/`, `__pycache__`.
- Description: `nexus/description.txt`.

## 3. GitHub - full repository
- Contents: everything in the Nexus package plus tests, synthetic fixtures, developer scripts, `docs/`, `UX.md`,
  `.gitignore`.
- Never included: `catalog.json` (derived from game files and local paths), `config.json`, `backups/`, real saves.
- License: MIT (holder "Armory authors"); the owner may change this before publishing.

## Support link
Every public description includes the Ko-fi page (https://ko-fi.com/sajuuk2033, Sajuuk). The banner image is hot-linked, never bundled.

## Common rules
- Leak scan over every file (and inside zip fixtures) for personal names, e-mail addresses, profile ids, absolute drive
  paths and Workshop item ids taken from private saves; any hit fails the build.
- No game files, assets or game-derived data in any package.
