# Armory - development notes

Technical facts learned while building Armory. Everything here was observed in the game's own data or in saves;
items marked "unverified" have not been confirmed in game.

## Architecture
- `server.py` - stdlib `http.server` on 127.0.0.1 (port 8765) with a per-run token; JSON API used by `web/`.
- `savefile.py` - reads/writes Conquest saves (ZIP). Writes only new copies (or backed-up overwrites).
- `loadout.py` - inventory model: place/remove items, auto-pack into the grid, ammo auto-fill, undo-friendly pure functions.
- `catalog.py` - builds `catalog.json` from the game's paks (`gamelogic.pak`, DLC paks, `mods/*`, Workshop content).
  Base-game files win over mods that redefine the same file.
- `breeds.py` - generates modified soldier types ("breeds") into the local mod `armory_breeds` (data-only pak + `mod.info`
  + a localization pak).
- `perks.py`, `identity.py` - skill preset tokens; name/icon/tag/portrait handling.
- `config.py` - game/profile discovery (Steam registry + `libraryfolders.vdf`, Documents/OneDrive), `config.json` overrides.
- `web/` - single-page UI (plain JS, no build step).
- Environment variables for testing: `ARMORY_CAMPAIGN_DIR` (use a scratch folder of saves) and `ARMORY_MODS_DIR`
  (write the generated mod to a scratch folder instead of the game's `mods`).

## Save file format
- A Conquest `.sav` is a ZIP with `campaign.scn`, `status` and map data. Text format, CRLF, UTF-8. Preserve line endings
  and every other ZIP member when rewriting.
- Soldier: `{Human "<breed template>" 0xEID {Position}...{NameId first last}...}`. Look, voice and perks come from the breed.
- Loadout: `{Inventory 0xEID {box ...{item "name" ... {cell x y}{user "hand_right"}} ...}}`. The per-soldier pack is persisted
  and honoured on load. Worn headgear is an inventory item with `{user "head"}`.
- Item token forms: weapon/gear `"k98"`; grenade `"m24_splinter" "grenade"`; ammo `"rifle_ger" "clip" "ammo" 5`
  (count = rounds in the stack); dotted ammo file `mgun_ger.belt` becomes `"mgun_ger" "belt" "ammo"`;
  launchers `{item "x" "weapon" filled}`. Always write items using the catalog `tokens`.
- A fresh save's rifle has no `{user "hand_right"}`; the game adds it when it re-saves. Preserve whatever the save has.
- Grid is 8 wide; height is unknown (11 used, the tallest seen).
- Ammo stack sizes/totals follow what vanilla units carry (for example rifle 12x5, SMG 6x32, pistol 2x8, MG belts 2x300),
  not the `{block}` value in the ammo file.
- Squads: `{CampaignSquads {"template" "stage_1" 0xEID ...}}`. The squad template is separate from the breed.
- `status` holds the campaign `{name}`; quote it when it has spaces or brackets.
- **The game saves back to the campaign name, not to the file you loaded.** Copies must get a new unique name.
- Mods a save uses are listed in `{mods}` inside `{saveinfo}`; Armory appends `"armory_breeds:0"`.
- Veterancy is stored in `{Extender "vitality" {Veterancy N}}`; the save stores no other perk-derived stats.
- Army is `{army ger}` etc. in `status`. Conquest unit sets exist for ger, rus, eng, fin, usa
  (`set/multiplayer/units/conquest/units_<army>.set`). Skin folders: germans, soviets, united_kingdom, united_states, finnish.

## Items
- Item definitions live in `set/stuff/<category>/<name>`; grenades `<name>.grenade`, ammo `<family>.<kind>.ammo`.
  Items inherit via `{from "..."}`; grid size is `{inventory {size W H}}` somewhere up the chain.
- Weapon to ammo: `{filling "ammo <family> <kind>" N}`; MGs use `{filling "mgun_ger" 50}` (a family without the `ammo ` prefix).
- Items that exist only in a mod are silently turned into empty ammo entries if the save does not list that mod.
  `server.check_item_sources` refuses such edits.

## Resupply rule
Crates refill a soldier to the inventory of his **breed** (`{inventory}` in the breed file), not to his saved pack.
A breed whose inventory has no ammo line refills nothing, so generated breeds describe the full kit: every carried weapon
gets at least the catalog's normal ammo total. Hand-held weapon is listed first, then other guns, then launchers
(`{in_hands 0}` is the first listed weapon). Breed inventory syntax: `{item "rifle_ger clip ammo" TOTAL STACK}`,
weapons `{item "x" filled}`, other items bare `{item "x"}`.
Generated breed names: `<base breed dir>/arm_<sha1[:10]>`. A changed local mod needs a game restart.

## Perks (skills)
- Perks are preset tokens in a breed's `{perks}` block, e.g. `("rifle_skill_rank_2")("tier2_standard")("at_rank_3")`.
  Presets: `set/breed/presets/perks/{skills,health,specialties,vision}.inc`.
- Layers: skill (`skill_rank_0` or `rifle|smg|mg|loader|loader_smg _skill_rank_1..5`), tier (`tier1..4 _ standard|recon|defense`:
  health/stamina/speed/regen), `at_rank_1..6`, extras (stealth, medic, marksman, sniper_vision, binocular_vision,
  skilled_repair, engineer). `perks.py` rewrites only the named layers and keeps unmanaged presets.
- Confirmed in game: speed tiers, engineer, skill levels. Sniper optics and Medic need a matching item to show their ability.
- A skill rank sets every weapon to that level; the trained weapon and pistol get +1. Unverified: whether later tokens
  override earlier ones.

## Identity
- Name: `{NameId first last}` are **0-based** indexes into the game's name lists (`localizations names/<nation>/first|last`).
  Only listed names can be chosen; free text would need a localization mod.
- Icon (`{icon "smg"}`) and tag (`{tags "soldier_pzscheck"}`) are single values in the breed. In vanilla the tag follows the
  launcher almost perfectly (Panzerschreck, Panzerfaust, anti-tank rifle).
- Portrait: `{portrait "ger_regular"}` line in the breed (unverified in game).

## Localization of generated breeds
The unit panel shows the localized text `desc/human/<breed path>`. Generated breeds need an entry or the raw key is shown.
Armory ships `mods/armory_breeds/localizations/default.pak` with `default/interface/text/desc/armory_breeds.pot`
(`msgctxt "desc/human/<breed>"`, English text in `msgid`, empty `msgstr`) and gives each generated breed the name of the
breed it was made from. Unverified in game.

## Gotchas
- `draggable: true` rendered `draggable=""`; the attribute must be the string `'true'`. Same for `aria-pressed`.
- A mod that redefines a vanilla file (for example an SMG pattern) can zero vanilla sizes; base-game files must win.
- Reading breed files per soldier is slow with large Workshop folders; use `breeds.find_bases` (single pass).
- Launchers are carried in addition to the rifle; "backup" is a second loaded long gun in the pack with no `{user}`.
- Python scripts that patch backslash escapes via shell heredocs get mangled; edit files with an editor tool.

## Tests and tools
Run from this folder:
- First build the catalog from your own game install (the tests that touch items need it, and it is never shipped):
  `python catalog.py catalog.json`
- Then `python -m unittest discover` (uses the frozen saves in `fixtures/`). `test_factions.py` and `test_package.py` need no game install.
- `python validate_catalog.py catalog.json <save.sav> ...` checks that every item in real saves resolves and fits the grid.
- `python slice.py <src.sav> <dst.sav> <eid>` is the original proof-of-concept edit of one soldier (German rifle/helmet swap).
- `python make_feature_test_save.py <source.sav>`, `make_identity_test_save.py`, `make_perk_test_save.py` write in-game test
  saves from a German save with at least six riflemen. They take the source save as a required argument and only read it.
  Use `ARMORY_CAMPAIGN_DIR` / `ARMORY_MODS_DIR` scratch folders when experimenting.
