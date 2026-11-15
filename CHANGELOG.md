# Changelog

## 1.0.0

First public release.

- Local web editor (Python standard library only, 127.0.0.1) for Gates of Hell Dynamic Conquest saves.
- Loadout: primary weapon, sidearm, launcher, backup gun, headgear, grenades, medical, tools; ammo follows the weapon;
  "Add ammo" picker; pack grid with auto-sort and optional drag and drop; undo/redo; per-soldier, per-squad or per-role scope.
- Uniform (skin) picker and rank (veterancy 0..max).
- Skills: weapon skill level, toughness/build tier, anti-tank rank, specialties (stealth, medic, marksman, sniper optics,
  binocular optics, skilled repair, engineer).
- Identity: soldier name (from the game's own name lists), unit-card icon, ability tag, portrait.
- Generated data-only mod `armory_breeds` so supply crates refill edited soldiers to their new kit, with on-screen unit
  names for generated soldier types.
- Safety: saves are always written as new copies with their own campaign name; "overwrite" is opt-in and backs up first.
  Items from mods the save does not list are refused.
- Game and save folders auto-detected (Steam libraries, Documents/OneDrive), overridable in Settings.
- Multi-nation support (German, Soviet, British, American, Finnish) based on the game's own unit sets.
  Verified in game for German saves; other nations are covered by unit tests only.
- Unit tests and developer scripts (see docs/DEVELOPMENT.md).

---
Support the project on Ko-fi (Sajuuk): https://ko-fi.com/sajuuk2033
