"""Regression tests for the save writer. Uses frozen fixtures and a temp folder only."""
import pathlib, re, shutil, tempfile, unittest, zipfile

import breeds
import loadout as lo
import savefile

FIX = pathlib.Path(__file__).parent / "fixtures"
CAT = lo.Catalog()
INV = re.compile(r"\t\{Inventory (0x[0-9a-f]+)\n.*?\n\t\}", re.S)


@unittest.skipUnless((pathlib.Path(__file__).parent / "fixtures" / "fresh_ger.sav").exists(), "fixtures/fresh_ger.sav is not in this checkout")
class W(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.src = self.d / "a.sav"
        shutil.copy(FIX / "fresh_ger.sav", self.src)
        self.s = savefile.open_save(self.src, CAT)["soldiers"][5]
        self.new, _ = lo.equip(self.s["loadout"], CAT, "primary", "g41")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def status(self, p):
        return zipfile.ZipFile(p).read("status").decode()

    def scn(self, p):
        return zipfile.ZipFile(p).read("campaign.scn").decode().replace("\r", "")

    def test_name_is_quoted_and_scoped(self):
        out = savefile.write_copy(self.src, {self.s["eid"]: self.new}, "My Armory (copy)")
        st = self.status(out)
        self.assertIn('{name "My Armory (copy)"}', st)
        # only the campaign name differs; map {name ...} entries in the same file are untouched
        self.assertEqual(self.status(self.src).replace("{name TESTCAMPAIGN}", '{name "My Armory (copy)"}'), st)

    def test_plain_name_stays_bare(self):
        out = savefile.write_copy(self.src, {self.s["eid"]: self.new}, "ArmoryOne")
        self.assertIn("{name ArmoryOne}", self.status(out))

    def test_never_overwrites(self):
        a = savefile.write_copy(self.src, {self.s["eid"]: self.new}, "Same")
        b = savefile.write_copy(self.src, {self.s["eid"]: self.new}, "Same")
        self.assertNotEqual(a, b)
        self.assertTrue(a.exists() and b.exists())

    def test_source_untouched(self):
        before = self.src.read_bytes()
        savefile.write_copy(self.src, {self.s["eid"]: self.new}, "X")
        self.assertEqual(before, self.src.read_bytes())

    def test_only_target_inventory_changes(self):
        out = savefile.write_copy(self.src, {self.s["eid"]: self.new}, "X")
        a, b = self.scn(self.src), self.scn(out)
        ia = {m.group(1): m.group(0) for m in INV.finditer(a)}
        ib = {m.group(1): m.group(0) for m in INV.finditer(b)}
        self.assertEqual([k for k in ia if ia[k] != ib[k]], [self.s["eid"]])
        self.assertEqual(INV.sub("", a), INV.sub("", b))        # everything outside inventories is identical

    def test_crlf_preserved(self):
        out = savefile.write_copy(self.src, {self.s["eid"]: self.new}, "X")
        raw = zipfile.ZipFile(out).read("campaign.scn")
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))

    def test_overwrite_backs_up_and_keeps_name(self):
        savefile.BACKUPS = self.d / "bk"
        before = self.src.read_bytes()
        out = savefile.write_copy(self.src, {self.s["eid"]: self.new}, None, overwrite=True)
        self.assertEqual(out, self.src)
        self.assertNotEqual(before, self.src.read_bytes())
        self.assertEqual([p.read_bytes() for p in (self.d / "bk").glob("*.sav")], [before])
        self.assertIn("{name TESTCAMPAIGN}", self.status(self.src))

    def test_generated_breed_is_wired_into_save_and_mod(self):
        import config
        game = pathlib.Path(config.resolved()["game_dir"])
        remap, files = breeds.plan(game, None, {self.s["eid"]: self.new}, {self.s["eid"]: self.s["breed"]})
        newp = remap[self.s["eid"]]
        self.assertIn('{item "g41" filled}', files[newp])
        root = breeds.install(game, files, self.d / "mods")
        self.assertIn(f"set/breed/{newp}.set", zipfile.ZipFile(root / "resource" / "gamelogic.pak").namelist())
        out = savefile.write_copy(self.src, {self.s["eid"]: self.new}, "B", remap=remap)
        self.assertIn(f'{{Human "{newp}" {self.s["eid"]}', self.scn(out))
        self.assertIn('"armory_breeds:0"', self.status(out))
        self.assertEqual(self.status(out).count("armory_breeds"), 1)
        self.assertEqual(breeds.add_to_mods(self.status(out)), self.status(out))     # idempotent

    def test_breed_is_full_kit_even_if_pack_was_spent(self):
        import copy
        import config
        game = pathlib.Path(config.resolved()["game_dir"])
        spent = copy.deepcopy(self.new)
        spent["entries"] = [e for e in spent["entries"] if e["role"] != "ammo"]      # a pack that already burned every mag
        plain = breeds.inventory_lines(spent)
        full = breeds.inventory_lines(spent, CAT)
        self.assertFalse([l for l in plain if " ammo" in l])
        self.assertTrue([l for l in full if l.startswith('{item "rifle_ger clip ammo"')], full)

    def test_skin_and_rank_via_breed_and_save(self):
        import config
        game = pathlib.Path(config.resolved()["game_dir"])
        eid = self.s["eid"]
        remap, files = breeds.plan(game, None, {}, {eid: self.s["breed"]}, None, {eid: {"skin": "ger_heer_43_rfl_2", "vet": 4}})
        body = files[remap[eid]]
        self.assertIn('{skin "ger_heer_43_rfl_2"}', body)
        self.assertIn('("veterancy_lvl_4")', body)
        self.assertEqual(body.count("{inventory"), 1)                  # inventory untouched for a look-only change
        out = savefile.write_copy(self.src, {}, "Look", remap=remap, vets={eid: 4})
        self.assertEqual(savefile.human_vet(self.scn(out), eid), 4)
        self.assertIn(f'{{Human "{remap[eid]}" {eid}', self.scn(out))

    def test_add_ammo_and_auto_sort(self):
        n2, _ = lo.add_ammo(self.new, CAT, "rifle_ger.clip", 2)
        k = lambda x: sum(1 for e in x["entries"] if e["role"] == "ammo")
        self.assertEqual(k(n2), k(self.new) + 2)
        n3, _ = lo.auto_sort(n2)
        self.assertEqual(sorted(e["id"] for e in n3["entries"]), sorted(e["id"] for e in n2["entries"]))
        cells = [(e["x"] + dx, e["y"] + dy) for e in n3["entries"] for dx in range(e["size"][0]) for dy in range(e["size"][1])]
        self.assertEqual(len(cells), len(set(cells)))                      # nothing overlaps
        self.assertTrue(all(e["role"] != "ammo" or e["y"] >= 0 for e in n3["entries"]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
