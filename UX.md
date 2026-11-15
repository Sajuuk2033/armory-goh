# Armory — UX brief (2026-11-14)

Goal: someone who has never seen the tool can change a soldier's gun and hat in under a minute without reading docs.

## What the references taught (sources are thin; treat as inspiration, not rules)
- Arma 3 Arsenal and its community clones: category tabs, a live preview, save/load of named loadouts, copy/paste/export of a loadout.
  Overwrite behavior is the recurring complaint -> our saves are ALWAYS copies, never in-place.
- Grid inventories (Tarkov, Diablo 4): drag to place, but rotate/auto-fit is poorly discoverable. The game's grid doesn't rotate,
  so we skip rotation and auto-place instead; dragging is optional.
- Loadout systems (SWTOR, light.gg): a summary panel of "everything selected", presets, and a clear "New/Reset". Menus that make
  you dig for what you want are a known pain.
- Cursed Workshop itself: 3 panes, numbered steps, long technical inspector (XYZ, parents, pivots). Powerful, but intimidating.
  Armory should feel like the opposite: one screen, plain words, nothing technical visible by default.

## Principles
1. **Slots first, grid second.** People think "give him a G41", not "cell 0 0". The main view is named slots (Primary, Sidearm,
   Headgear, Grenades, Medical, Tools). The raw pack grid is shown but secondary (a "Pack" section; drag optional).
2. **Do the boring parts automatically.** Swapping a weapon swaps the matching ammo, keeps the same number of magazines/clips
   (capped by space), auto-places items in the first free spot. The user never picks ammo or cells.
3. **Always safe.** Never overwrite the original save; output is a new copy. Undo/Redo and "Reset soldier" always visible.
   Every change appears in a plain-language list ("Rifle: K98 -> G41"). Warn if the game seems to be running.
4. **Scale the edit.** "Apply to: just him / his squad / all riflemen". Copy loadout from soldier A to B. Presets by name.
5. **Show, don't ask.** Picker shows only what fits and is German by default (toggle for other nations); items that don't fit the
   pack are disabled WITH the reason ("Not enough room: needs 6x2"), never hidden silently.
6. **Plain language, no IDs.** Soldiers are "Rifleman 3" / "NCO", never 0xb006. Internal names only in a tooltip.
7. **Instant feedback.** Pack meter ("31 of 48 cells used"), current weight if available, changed items highlighted.
8. **Forgiving.** Search-as-you-type, keyboard navigable, confirm only before writing the file, every action undoable.
9. **Honest about unknowns.** No item art yet -> clean colored tiles with the name + size; no fake icons.

## Layout (single screen, left to right)
- Left: Squad list -> soldier cards (role, weapon, hat; changed ones get a dot).
- Center: the selected soldier: slot cards on top, Pack grid underneath, diff list + Undo/Redo.
- Right: Picker (search, category chips, "fits" badges). Opens when a slot is clicked; otherwise shows tips/presets.
- Bottom bar: "N changes" · Apply-to scope · [Save as new copy].

## Out of scope for v1 (said plainly in the UI where relevant)
Skins/uniforms (needs a generated breed mod), non-German rosters beyond the "show other nations" toggle, item icons.
