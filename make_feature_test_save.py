"""Write ONE new save copy for the in-game test of skin/rank, launcher/backup slots and Add ammo.

Six plain riflemen from the source save, each with unique headgear so you can tell them apart:

  1 uniform only      new skin, rank unchanged
  2 rank only         veterancy 8, uniform unchanged
  3 uniform + rank    different skin, veterancy 4
  4 launcher          MP40 + Panzerschreck, NO spare ammo/rockets in the pack  -> do crates refill both?
  5 backup gun        MP40 in hand + K98 as backup, NO spare ammo              -> do crates refill both?
  6 add ammo          MG42 drum with 3 extra drums added                       -> are the added drums kept?

usage: python make_feature_test_save.py <source.sav>   (a Conquest save of yours; it is only read, never modified)
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


def pick_skins(cat, current, n):
    """n skins from n different German uniform groups, none in the soldier's current group."""
    by = {}
    for k, v in sorted(cat.skins.items()):
        if v["nation"] == "germans" and v["source"] == "" and v["group"] != current:
            by.setdefault(v["group"], k)
    return list(by.values())[:: max(1, len(by) // n)][:n]


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
    if len(pool) < 6 or len(heads) < 6:
        raise SystemExit(f"Need 6 riflemen and 6 headgear, have {len(pool)} / {len(heads)}")
    cur_group = cat.skins[pool[0]["skin"]]["group"] if pool[0].get("skin") in cat.skins else ""
    skins = pick_skins(cat, cur_group, 2)
    edits, looks, rows = {}, {}, []

    def prep(s, head, fn=None, strip=False):
        new = copy.deepcopy(s["loadout"])
        new, _ = lo.equip(new, cat, "head", head)
        if fn:
            new = fn(new)
        if strip:
            new["entries"] = [e for e in new["entries"] if e["role"] != "ammo"]
        edits[s["eid"]] = new
        return s["eid"]

    s1, s2, s3, s4, s5, s6 = pool[:6]
    full = {}
    h = heads
    e = prep(s1, h[0]); full[e] = copy.deepcopy(edits[e]); looks[e] = {"skin": skins[0]}; rows.append((e, f"uniform only -> {skins[0]}", h[0]))
    e = prep(s2, h[1]); full[e] = copy.deepcopy(edits[e]); looks[e] = {"vet": 8}; rows.append((e, "rank only -> veterancy 8", h[1]))
    e = prep(s3, h[2]); full[e] = copy.deepcopy(edits[e]); looks[e] = {"skin": skins[1], "vet": 4}; rows.append((e, f"uniform + rank -> {skins[1]}, vet 4", h[2]))

    def launcher(x):
        x, _ = lo.equip(x, cat, "primary", "mp40_folded")
        x, _ = lo.equip(x, cat, "launcher", "panzershreck_54.weapon")
        return x

    def backup(x):
        x, _ = lo.equip(x, cat, "primary", "mp40_folded")
        x, _ = lo.equip(x, cat, "backup", "k98")
        return x

    def mg(x):
        x, _ = lo.equip(x, cat, "primary", "mg42_drum")
        x, _ = lo.add_ammo(x, cat, "mgun_ger.drum", 3)
        return x

    for s, head, fn, label, strip in ((s4, h[3], launcher, "MP40 + Panzerschreck, no spare ammo", True),
                                      (s5, h[4], backup, "MP40 + K98 backup, no spare ammo", True),
                                      (s6, h[5], mg, "MG42 drum + 3 added drums (kept)", False)):
        eid = prep(s, head, fn)
        full[eid] = copy.deepcopy(edits[eid])             # breed = full kit
        if strip:
            edits[eid] = copy.deepcopy(edits[eid])
            edits[eid]["entries"] = [x for x in edits[eid]["entries"] if x["role"] != "ammo"]
        rows.append((eid, label, head))

    have = {x["eid"]: x["breed"] for x in sd["soldiers"]}
    texts = breeds.find_bases(game, ws, set(have.values()))
    # the breed describes the FULL kit; the saved pack may be spent
    remap, files = breeds.plan(game, ws, {**{k: full[k] for k in full}}, have, cat, looks, texts)
    breeds.install(game, files)
    vets = {k: v["vet"] for k, v in looks.items() if v.get("vet") is not None}
    out = sf.write_copy(src, edits, "Armory feature test", remap=remap, vets=vets)
    print(f"Wrote {out}\nSource (untouched): {src}\n")
    for eid, label, head in rows:
        print(f"  {eid}  {label:<48} headgear: {head}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
