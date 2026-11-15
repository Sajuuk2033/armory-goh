# Armory - soldier editor for Gates of Hell (Dynamic Conquest)

Change what your soldiers carry, wear and know, then load the result as a new campaign save.
Armory is a small local app (Python plus your web browser). It never touches the running game process.

Version 1.0.0 - MIT license - not affiliated with the game's developers or publisher.

## What you need
- Call to Arms - Gates of Hell: Ostfront (developed against v1.067.0), **your own copy**. Armory ships no game files;
  it reads item, skin, name and soldier-type data from your install to build its pick-lists.
- Python 3.10 or newer. Nothing to install (standard library only).
- A Dynamic Conquest campaign save.

## Install and run
1. Download and unzip Armory anywhere.
2. Double-click `start_armory.bat`, or run `python server.py` in the folder. Your browser opens at http://127.0.0.1:8765/
   (the server listens on your PC only, with a per-run token).
3. Armory finds the game and your saves itself (Steam libraries, Documents/OneDrive). If not, open **Settings** and paste
   the game folder and the profiles folder. They are remembered in `config.json`.
4. The first start builds `catalog.json` from your game files. This can take a minute.

## Safety model
- **Saves are copied, never overwritten.** "Review & save a copy" writes a new `.sav` next to your others, with its own
  campaign name. (The game saves back to the campaign *name*, so a copy that kept the old name would overwrite the
  original the first time you saved in game.)
- "Overwrite the original" is optional, needs a tick-box confirmation and first copies the original to `backups/`.
- Close the game before saving from Armory.
- Items that come from a mod the save does not list are refused (the game would silently drop them).
- Armory writes one small data-only mod, `armory_breeds`, into the game's `mods` folder. **Restart the game after saving
  if it was open**: the game reads mods at startup, so changed soldier types are only picked up after a restart.
- No DLL injection, no executable patching, nothing runs inside the game. Intended for single-player Conquest.

## What each section edits
- **Identity**: name (picked from the game's own name lists), unit-card icon, ability tag, portrait.
- **Rank**: veterancy level.
- **Skills**: weapon skill level, toughness/build, anti-tank rank and specialties (stealth, medic, marksman, sniper optics,
  binocular optics, skilled repair, engineer). Medic and sniper optics also need the matching item (medic bag, scoped rifle).
- **Weapons & gear**: primary, sidearm, launcher, backup gun, headgear, grenades, medical, tools. Ammo follows the weapon.
- **Uniform**: skin picker (grouped by uniform family).
- **Pack**: the 8-wide inventory grid; auto-sort, drag and drop, "Add ammo".
- "Apply to" changes just one soldier, his squad, or every soldier of a role. Undo/redo with Ctrl+Z / Ctrl+Y.

Why a generated mod? Supply crates refill a soldier to the inventory of his *soldier type* (breed), not to what his pack
currently holds. For soldiers whose gear, look, skills or identity you changed, Armory writes a modified copy of their
soldier type into `armory_breeds` and points the save at it.

## Limits and unverified items
Confirmed in game (German saves): loadout edits, uniform, rank, skills, names, crate refill for edited soldiers,
launcher and backup gun carried together.

Not verified in game; treat as experimental:
- Portrait changes.
- Unit-card icon changes (for example a sniper icon on a plain rifleman) and whether an ability tag changes behaviour.
- The on-screen name of generated soldier types ("Rifleman [Heer]" style labels).
- Whether a save's veterancy or the soldier type's veterancy wins in every case.
- Whether later skill presets override earlier ones in every combination.
- Non-German nations (Soviet, British, American, Finnish): handled from the game's own data and unit tests, not yet played.
- Saves from heavily modded campaigns may contain items or soldier types Armory cannot describe.
- The inventory grid height (11 rows) is the largest seen; the true limit is unknown.
- The health figure in the Skills section is inferred from one in-game reading.

Keep your own backups of saves you care about.

## Credits
Inspired by the idea behind **Cursed Workshop** (an external editor plus a generated local mod for Gates of Hell).
No code from it was copied; Armory was written independently from the game's data files and saves.
Gates of Hell and Call to Arms belong to their respective owners. No game files, assets or game data are included
in this project.

## Support
Armory is free. If it saved you time, you can support its development on Ko-fi (Sajuuk): https://ko-fi.com/sajuuk2033

[![Support on Ko-fi](https://storage.ko-fi.com/cdn/generated/fhfuc7slzawvi/2026-11-15_rest-e3d3b1148ed8909b5afd4e9a847d0c82-fthlyfbg.jpg)](https://ko-fi.com/sajuuk2033)

## For developers
See `docs/DEVELOPMENT.md` and `CHANGELOG.md`.
