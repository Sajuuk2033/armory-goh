import re, sys, zipfile, glob, unittest
from loadout import *
import os
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures") + os.sep
CAT = Catalog()

def blocks(save):
    text = zipfile.ZipFile(P + save).read("campaign.scn").decode("utf-8").replace("\r", "")
    return [m.group(0) for m in re.finditer(r"\t\{Inventory 0x[0-9a-f]+\n.*?\n\t\}", text, re.S)]

@unittest.skipUnless((__import__('pathlib').Path(__file__).parent / "fixtures" / "fresh_ger.sav").exists(), "fixtures/fresh_ger.sav is not in this checkout")
class T(unittest.TestCase):
    def test_roundtrip_german_save(self):
        n = bad = 0
        for s in ("fresh_ger.sav",):
            for b in blocks(s):
                n += 1
                lo = parse(b, CAT)
                if serialize(lo) != b:
                    bad += 1
                    if bad < 3: print("MISMATCH\n", b[:400], "\n--\n", serialize(lo)[:400])
        print(n, "blocks, mismatches:", bad)
        self.assertEqual(bad, 0)
    def test_grid_bounds(self):
        mx = my = 0
        for s in ("fresh_ger.sav",):
            for b in blocks(s):
                lo = parse(b, CAT)
                for e in lo["entries"]:
                    mx = max(mx, e["x"] + e["size"][0]); my = max(my, e["y"] + e["size"][1])
        print("grid extent seen:", mx, "x", my)
        self.assertLessEqual(mx, GRID_W); self.assertLessEqual(my, GRID_H)
    def rifleman(self):
        return next(parse(b, CAT) for b in blocks("fresh_ger.sav") if b.startswith("	{Inventory 0xb006"))
    def test_k98_to_g41_keeps_ammo(self):
        lo = self.rifleman(); n = len(lo["entries"])
        new, msgs = equip(lo, CAT, "primary", "g41")
        print(msgs); self.assertEqual(len(new["entries"]), n)
        self.assertTrue(any(e["tokens"] == ["g41"] for e in new["entries"]))
    def test_to_mp40_swaps_ammo(self):
        new, msgs = equip(self.rifleman(), CAT, "primary", "mp40_folded")
        print(msgs)
        self.assertFalse(any(e["tokens"][:2] == ["rifle_ger", "clip"] for e in new["entries"]))
        self.assertTrue(sum(e["tokens"][0] == "mp40" for e in new["entries"]) >= 5)
        # no overlaps
        g = set()
        for e in new["entries"]:
            for dx in range(e["size"][0]):
                for dy in range(e["size"][1]):
                    self.assertNotIn((e["x"] + dx, e["y"] + dy), g); g.add((e["x"] + dx, e["y"] + dy))
    def test_head(self):
        new, msgs = equip(self.rifleman(), CAT, "head", "ger_sidecap_m41_var1"); print(msgs)
        self.assertEqual(sum(e["user"] == "head" for e in new["entries"]), 1)
    def test_picker_flags(self):
        c = candidates(self.rifleman(), CAT, "primary", ["ger"]); print(len(c), "german primaries;", sum(x["fits"] for x in c), "fit")
        self.assertTrue(any(x["name"] == "g41" and x["fits"] for x in c))
    def test_undoable_pure(self):
        lo = self.rifleman(); before = serialize(lo); equip(lo, CAT, "primary", "g41"); self.assertEqual(serialize(lo), before)
if __name__ == "__main__":
    unittest.main(verbosity=1)
