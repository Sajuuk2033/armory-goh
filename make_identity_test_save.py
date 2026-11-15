"""Write ONE new save copy to test names, icons and tags in game.

Six plain riflemen from the source save, each with unique headgear so you can tell them apart:

  1 control      nothing changed
  2 name A       NameId 1 1   -> "Adolf Altmann" if the indexes start at 0, "Achim Adler" if they start at 1
  3 name B       NameId 145 149 -> "Otto Zumwald" (the last entries of both lists)
  4 icon         icon "sniper" (he is still a plain K98 rifleman)  -> does his unit card show a sniper symbol?
  5 AT, tag OK   MP40 + Panzerschreck, tag soldier_pzscheck        -> what the game itself gives a shreck carrier
  6 AT, tag off  MP40 + Panzerschreck, tag soldier (plain)         -> does he behave differently from soldier 5?

usage: python make_identity_test_save.py <source.sav>   (a Conquest save of yours; it is only read, never modified)
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
    ger = cat.name_lists["ger"]
    assert ger["first"][145] and ger["last"][149], "name lists shorter than expected"

    def launcher(x):
        x, _ = lo.equip(x, cat, "primary", "mp40_folded")          # base-game MP40 (plain "mp40" is a Workshop item)
        x, _ = lo.equip(x, cat, "launcher", "panzershreck_54.weapon")
        return x

    plan = [("control: nothing changed", None, {}, None),
            ("name A: NameId 1 1", None, {}, [1, 1]),
            ("name B: NameId 145 149", None, {}, [145, 149]),
            ("icon: sniper", None, {"icon": "sniper"}, None),
            ("AT: MP40 + Panzerschreck, tag soldier_pzscheck", launcher, {"tag": "soldier_pzscheck"}, None),
            ("AT: MP40 + Panzerschreck, tag soldier", launcher, {"tag": "soldier"}, None)]
    edits, looks, names, rows = {}, {}, {}, []
    for s, head, (label, fn, look, nm) in zip(pool, heads, plan):
        new, _ = lo.equip(copy.deepcopy(s["loadout"]), cat, "head", head)
        if fn:
            new = fn(new)
        edits[s["eid"]] = new
        if look:
            looks[s["eid"]] = look
        if nm:
            names[s["eid"]] = nm
        rows.append((s["eid"], label, head, s["name_id"]))
    have = {x["eid"]: x["breed"] for x in sd["soldiers"]}
    texts = breeds.find_bases(game, ws, set(have.values()))
    remap, files = breeds.plan(game, ws, edits, have, cat, looks, texts)
    breeds.install(game, files)
    out = sf.write_copy(src, edits, "Armory identity test", remap=remap, names=names)
    print(f"Wrote {out}\nSource (untouched): {src}\n")
    for eid, label, head, was in rows:
        print(f"  {eid}  {label:<48} headgear: {head:<24} original NameId: {was}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
