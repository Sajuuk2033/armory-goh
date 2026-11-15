"""Write ONE new save copy to test skill (perk) edits in game.

Six plain riflemen from the source save, each with unique headgear so you can tell them apart. Their guns are left alone, only skills change:

  1 control    no change                                -> baseline walking speed / health / abilities
  2 scout      tier 4 Scout                             -> faster than the control, more stamina (runs longer)
  3 defender   tier 1 Defender                          -> slower than the control
  4 engineer   Engineer specialty                       -> can he build fortifications / barricades?
  5 sniper     Marksman + Sniper optics, rifle skill 5  -> aimed shot / scope ability
  6 medic      Medic specialty                          -> can he heal and place a medic flag?

usage: python make_perk_test_save.py <source.sav>   (a Conquest save of yours; it is only read, never modified)
"""
import copy
import sys
from pathlib import Path

import breeds
import catalog
import config
import loadout as lo
import savefile as sf

HEADS = ["ger_fieldcap_m43", "ger_stalhelm_m43_var1", "ger_sidecap_m42_var1", "ger_fieldcap_camo", "ger_m40_helmet_early", "ger_crusher_cap"]
PLAN = [
    ("control: no change", None),
    ("scout: tier 4 Scout (fast, 425% stamina)", {"tier": "tier4_recon"}),
    ("defender: tier 1 Defender (slow)", {"tier": "tier1_defense"}),
    ("engineer: Engineer specialty", {"extras": ["engineer"]}),
    ("sniper: rifle 5 + Marksman + Sniper optics", {"skill": "rifle_skill_rank_5", "extras": ["marksman", "sniper_vision"]}),
    ("medic: Medic specialty", {"extras": ["medic"]}),
]


def main(src):
    r = config.resolved()
    game = Path(r["game_dir"])
    ws = Path(r["workshop_dir"]) if r["workshop_dir"] else None
    if sf.game_running():
        raise SystemExit("Close the game first.")
    cat = lo.Catalog(catalog.build(str(game), str(ws) if ws else None))
    d = list(config.campaign_dirs())[0]
    src = Path(src)
    if not src.is_absolute() and not src.exists():
        src = d / src                              # bare file name: look in the campaign folder
    sd = sf.open_save(src, cat)
    pool = [s for s in sd["soldiers"] if s["breed"].endswith("/rifleman_1")]
    heads = [h for h in HEADS if h in cat.items]
    if len(pool) < len(PLAN) or len(heads) < len(PLAN):
        raise SystemExit(f"Need {len(PLAN)} riflemen and headgear, have {len(pool)} / {len(heads)}")
    edits, looks, rows = {}, {}, []
    for s, head, (label, spec) in zip(pool, heads, PLAN):
        new, _ = lo.equip(copy.deepcopy(s["loadout"]), cat, "head", head)
        edits[s["eid"]] = new
        if spec:
            looks[s["eid"]] = {"perks": spec}
        rows.append((s["eid"], label, head))
    have = {x["eid"]: x["breed"] for x in sd["soldiers"]}
    texts = breeds.find_bases(game, ws, set(have.values()))
    remap, files = breeds.plan(game, ws, edits, have, cat, looks, texts)      # every soldier gets a breed (new headgear)
    breeds.install(game, files)
    out = sf.write_copy(src, edits, "Armory skills test", remap=remap)
    print(f"Wrote {out}\nSource (untouched): {src}\n")
    for eid, label, head in rows:
        print(f"  {eid}  {label:<46} headgear: {head}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
