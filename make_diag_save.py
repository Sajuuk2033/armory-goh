"""Write ONE new save copy that separates the theories about why crates don't resupply edited soldiers.

Five soldiers, spare ammo removed from every pack, each given unique headgear so you can tell them apart in game:

  A  control      vanilla breed (rifleman_1), K98          -> expected to be refilled (it is the soldier's own kit)
  B  vanilla G41  vanilla breed vet_sa (G41 is native)      -> tests "a vanilla breed that already carries the weapon"
  C  custom K98   generated breed, K98 (native weapon)      -> tests "does a generated breed itself break refilling?"
  D  FG42 vanilla vanilla breed rifleman_1, FG42            -> a swapped weapon, no breed help (what v0.1 did)
  E  FG42 custom  generated breed with FG42 + full ammo     -> a swapped weapon WITH a matching breed (v0.2)

usage: python make_diag_save.py <source.sav>   (required). Never touches the source; the game must be closed.
"""
import copy
import sys
from pathlib import Path

import breeds
import catalog
import config
import loadout as lo
import savefile as sf

HEADS = ["ger_fieldcap_m43", "ger_stalhelm_m43_var1", "ger_sidecap_m42_var1", "ger_fieldcap_camo", "ger_m40_helmet_early"]
PLAN = [  # label, weapon, breed (None = keep the soldier's own), generated breed?
    ("A control: K98, vanilla breed", "k98", None, False),
    ("B G41 on vanilla vet_sa breed", "g41", "mp/ger/mid/vet_sa", False),
    ("C K98 on a generated breed", "k98", None, True),
    ("D FG42, vanilla breed (swapped weapon)", "fg42", None, False),
    ("E FG42 on a generated breed", "fg42", None, True),
]


def main(src):
    r = config.resolved()
    game = Path(r["game_dir"])
    ws = Path(r["workshop_dir"]) if r["workshop_dir"] else None
    if sf.game_running():
        raise SystemExit("Close the game first.")
    cat = lo.Catalog(catalog.build(str(game), str(ws) if ws else None))
    src = Path(src) if src else max((p for d in config.campaign_dirs() for p in d.glob("*.sav")), key=lambda p: p.stat().st_mtime)
    sd = sf.open_save(src, cat)
    pool = [s for s in sd["soldiers"] if s["breed"].endswith("/rifleman_1")]
    if len(pool) < len(PLAN):
        raise SystemExit(f"Need {len(PLAN)} plain rifleman_1 soldiers in {src.name}, found {len(pool)}")
    heads = [h for h in HEADS if h in cat.items]
    if len(heads) < len(PLAN):
        raise SystemExit("Not enough distinct headgear in the catalog")
    edits, remap, files, rows = {}, {}, {}, []
    for s, (label, weapon, breed, generated), head in zip(pool, PLAN, heads):
        new = copy.deepcopy(s["loadout"])
        new, _ = lo.equip(new, cat, "primary", weapon)
        new, _ = lo.equip(new, cat, "head", head)
        full_kit = copy.deepcopy(new)                                  # the breed describes the FULL kit...
        new["entries"] = [e for e in new["entries"] if e["role"] != "ammo"]      # ...but the pack itself carries no spare ammo
        edits[s["eid"]] = new
        if breed:
            remap[s["eid"]] = breed
        elif generated:
            lines = breeds.inventory_lines(full_kit, cat)
            text = breeds.find_base(game, ws, s["breed"])
            path = breeds.breed_path(s["breed"], text, lines)
            remap[s["eid"]] = path
            files[path] = breeds.make_breed(text, lines)
        rows.append((s["eid"], label, head))
    if files:
        breeds.install(game, files)
    out = sf.write_copy(src, edits, "Armory resupply diag", remap=remap)
    print(f"Wrote {out}\nSource (untouched): {src}\n")
    for eid, label, head in rows:
        print(f"  {eid}  {label:<44} headgear: {head}")
    print("\nIn game: load 'Armory resupply diag', spend nothing (they have no spare ammo), park all five at the ammo crate.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
