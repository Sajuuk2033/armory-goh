"""Non-German armies (usa, rus, ... and an unknown one). Everything here is synthetic and lives in a temp folder:

  * a tiny fake game (resource/gamelogic.pak, humanskin.pak, localizations/default.pak) holding a few USA / Soviet / German
    items, breeds, skins and name lists, spelled like the real files,
  * Conquest saves written from scratch for army usa, rus and ig (a made-up army the table doesn't know).

No game install, no catalog.json and none of the owner's saves or mods are needed or touched.
"""
import os
import pathlib
import re
import shutil
import tempfile
import unittest
import zipfile
from unittest import mock

import breeds
import catalog
import config
import identity
import loadout as lo
import savefile as sf
import server

# ---------------------------------------------------------------- the fake game
ITEM = '{item\n\t{inventory {size %d %d}}\n\t%s\n}\n'


def rifle(w, h, ammo):
    return ITEM % (w, h, '{filling "ammo %s" 8}' % ammo)


def plain(w, h):
    return ITEM % (w, h, "")


AMMO = "{ammo\n\t{inventory {size 1 1}{block %d}}\n}\n"


def breed(skin, icon, tag, portrait, inv):
    return ('{breed\n\t{skin "%s"}\n\t{icon "%s"}\n\t{tags "%s"}\n\t{portrait "%s"}\n'
            '\t{perks\n\t\t("rifle_skill_rank_3")\n\t}\n\t{veterancy\n\t\t("veterancy_lvl_0")\n\t}\n\t{inventory\n%s\n\t}\n}\n'
            % (skin, icon, tag, portrait, "".join("\t\t%s\n" % l for l in inv)))


GAME_FILES = {
    # items (set/stuff/<category>/<name>)
    "set/stuff/rifle/garand": rifle(6, 2, "rifle_usa garand_clip"),
    "set/stuff/rifle/mosin": rifle(6, 2, "rifle_rus mosin_clip"),
    "set/stuff/rifle/k98": rifle(6, 2, "rifle_ger clip"),
    "set/stuff/bazooka/bazooka_m1.weapon": rifle(6, 1, "bazooka_m1 rocket"),
    "set/stuff/head/us_m1_helmet": plain(2, 2),
    "set/stuff/head/sov_ssh40": plain(2, 2),
    "set/stuff/head/usa_cap_patrol": plain(2, 2),          # in no breed's pack: only its name says whose it is
    "set/stuff/head/sov_ushanka": plain(2, 2),
    "set/stuff/head/ger_stalhelm_m42": plain(2, 2),
    "set/stuff/head/plain_hat": plain(2, 2),               # no army in the name, in no pack: belongs to nobody
    "set/stuff/ammo/rifle_usa.garand_clip.ammo": AMMO % 8,
    "set/stuff/ammo/rifle_rus.mosin_clip.ammo": AMMO % 5,
    "set/stuff/ammo/rifle_ger.clip.ammo": AMMO % 5,
    # breeds: two bazooka soldiers (same tag) so the tag table has something to read
    "set/breed/mp/usa/late/rifleman.set": breed("us_m41_rfl_1", "rifle", "soldier", "usa_regular", [
        '{item "garand" filled}', '{item "rifle_usa garand_clip ammo" 80 8}', '{item "us_m1_helmet"}']),
    "set/breed/mp/usa/late/ranger.set": breed("us_m41_rfl_2", "rifle", "soldier", "usa_ranger", [
        '{item "garand" filled}', '{item "rifle_usa garand_clip ammo" 80 8}']),
    "set/breed/mp/usa/late/at_1.set": breed("us_m41_rfl_1", "bazooka", "soldier_bazooka", "usa_regular", [
        '{item "garand" filled}', '{item "bazooka_m1"}', '{item "rifle_usa garand_clip ammo" 40 8}']),
    "set/breed/mp/usa/late/at_2.set": breed("us_m41_rfl_1", "bazooka", "soldier_bazooka", "usa_regular", [
        '{item "garand" filled}', '{item "bazooka_m1"}', '{item "rifle_usa garand_clip ammo" 40 8}']),
    "set/breed/mp/rus/early/rifleman.set": breed("sov_41_rkka_rfl_1", "rifle", "soldier", "rus_regular", [
        '{item "mosin" filled}', '{item "rifle_rus mosin_clip ammo" 60 5}', '{item "sov_ssh40"}']),
    "set/breed/mp/rus/early/guards.set": breed("sov_41_rkka_rfl_2", "rifle", "soldier", "rus_guards", [
        '{item "mosin" filled}', '{item "rifle_rus mosin_clip ammo" 60 5}']),
    "set/breed/mp/ger/mid/rifleman_1.set": breed("ger_heer_43_rfl_1", "rifle", "soldier", "ger_regular", [
        '{item "k98" filled}', '{item "rifle_ger clip ammo" 60 5}']),
}
SKINS = ["us_m41_rfl_1", "us_m41_rfl_2", "sov_41_rkka_rfl_1", "sov_41_rkka_rfl_2", "ger_heer_43_rfl_1"]
SKIN_DIR = {"us": ("united_states", "us_m41"), "sov": ("soviets", "sov_41_rkka"), "ger": ("germans", "ger_heer_43")}

NAMES_POT = ('msgid ""\nmsgstr ""\n\n' + "".join(
    'msgctxt "names/%s/first"\nmsgid "%s"\nmsgstr ""\n\nmsgctxt "names/%s/last"\nmsgid "%s"\nmsgstr ""\n\n' % (n, f, n, l)
    for n, f, l in (("usa", "Hank\\nJoe\\nBill", "Miller\\nCarter"), ("rus", "Ivan\\nPyotr", "Petrov\\nSidorov\\nVolkov"),
                    ("ger", "Karl\\nOtto", "Adler\\nBauer"))))
WEAPON_POT = ('msgid ""\nmsgstr ""\n\nmsgctxt "desc/weapon/garand"\nmsgid "M1 Garand"\nmsgstr ""\n\n'
              'msgctxt "desc/weapon/bazooka_m1"\nmsgid "M1 \'Bazooka\' Launcher"\nmsgstr ""\n\n'
              'msgctxt "desc/stuff/us_m1_helmet"\nmsgid "<c(ffffff)>M1</c> Helmet"\nmsgstr ""\n\n')


def build_game(root: pathlib.Path) -> pathlib.Path:
    (root / "resource" / "entity").mkdir(parents=True)
    (root / "localizations").mkdir()
    (root / "binaries").mkdir()
    with zipfile.ZipFile(root / "resource" / "gamelogic.pak", "w") as z:
        for n, t in GAME_FILES.items():
            z.writestr(n, t)
    with zipfile.ZipFile(root / "resource" / "entity" / "humanskin.pak", "w") as z:
        for s in SKINS:
            folder, group = SKIN_DIR[s.split("_")[0]]
            z.writestr("humanskin/[%s]/%s/%s.def" % (folder, group, s), "{skin}")
    with zipfile.ZipFile(root / "resource" / "properties.pak", "w") as z:          # the crates' lists of infantry ammo, per army
        z.writestr("properties/resupply.inc", "".join(
            '(define "items_light_%s"\n\t{item "%s" "%s" "ammo" 1}\n)\n' % (a, *st.split(".")) for a, st in
            (("usa", "rifle_usa.garand_clip"), ("rus", "rifle_rus.mosin_clip"), ("ger", "rifle_ger.clip"))))
    with zipfile.ZipFile(root / "localizations" / "default.pak", "w") as z:
        z.writestr("default/interface/text/names/dlg_names_all.pot", NAMES_POT)
        z.writestr("default/interface/text/desc/desc_weapon_usa.pot", WEAPON_POT)
    return root


# ---------------------------------------------------------------- synthetic saves
def human(breed_path, eid, first, last):
    return '\t{Human "%s" %s\n\t\t{Position 0 0}\n\t\t{Player 0}\n\t\t{NameId %d %d}\n\t}\n' % (breed_path, eid, first, last)


def inventory(eid, lines):
    body = "".join("\t\t\t%s\n" % l for l in lines)
    return "\t{Inventory %s\n\t\t{box\n\t\t\t{clear}\n%s\t\t}\n\t}\n" % (eid, body)


def write_save(path, army, soldiers, name="SYNTH"):
    """soldiers: [(breed path, eid, first, last, [inventory lines])]"""
    scn = "{campaign\n" + "".join(human(b, e, f, l) for b, e, f, l, _ in soldiers) + "".join(inventory(e, i) for _, e, _, _, i in soldiers)
    scn += '\t{CampaignSquads\n\t\t{"squad_test" "" %s}\n\t}\n}\n' % " ".join(e for _, e, _, _, _ in soldiers)
    status = "{saveinfo\n\t{version 9}\n\t{timestamp 1794677309}\n\t{name %s}\n\t{army %s}\n}\n" % (name, army)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("campaign.scn", scn)
        z.writestr("status", status)
    return path


USA_KIT = ['{item "garand" filled {cell 0 0}{user "hand_right"}}'] + [
    '{item "rifle_usa" "garand_clip" "ammo" 8 {cell %d %d}}' % (x, 2) for x in range(6)] + ['{item "us_m1_helmet" {cell 0 4}{user "head"}}']
RUS_KIT = ['{item "mosin" filled {cell 0 0}{user "hand_right"}}'] + [
    '{item "rifle_rus" "mosin_clip" "ammo" 5 {cell %d %d}}' % (x, 2) for x in range(6)] + ['{item "sov_ssh40" {cell 0 4}{user "head"}}']
GER_KIT = ['{item "k98" filled {cell 0 0}{user "hand_right"}}'] + [
    '{item "rifle_ger" "clip" "ammo" 5 {cell %d %d}}' % (x, 2) for x in range(6)]


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.game = build_game(cls.tmp / "game")
        cls.data = catalog.build(cls.game)
        cls.cat = lo.Catalog(cls.data)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.camp = pathlib.Path(tempfile.mkdtemp())
        self.mods = pathlib.Path(tempfile.mkdtemp())
        self.usa = write_save(self.camp / "usa.sav", "usa", [
            ("mp/usa/late/rifleman", "0xb000", 1, 1, USA_KIT), ("mp/usa/late/ranger", "0xb001", 2, 0, USA_KIT)])
        self.rus = write_save(self.camp / "rus.sav", "rus", [("mp/rus/early/rifleman", "0xb000", 1, 2, RUS_KIT)])
        self.ig = write_save(self.camp / "ig.sav", "ig", [("mp/ig/late/rifleman", "0xb000", 0, 0, GER_KIT)])
        env = {"ARMORY_CAMPAIGN_DIR": str(self.camp), "ARMORY_MODS_DIR": str(self.mods)}
        res = {"game_dir": str(self.game), "game_ok": True, "profiles_dir": "", "profiles_ok": False, "workshop_dir": "", "ok": True,
               "auto_game": False, "auto_profiles": True}
        self.patches = [mock.patch.dict(os.environ, env), mock.patch.object(config, "resolved", lambda: res),
                        mock.patch.object(sf, "game_running", lambda: False), mock.patch.object(server, "CAT", self.cat),
                        mock.patch.object(sf, "BACKUPS", self.camp / "backups")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.camp, ignore_errors=True)
        shutil.rmtree(self.mods, ignore_errors=True)

    def open(self, name):
        return server.api_open({"file": [name], "dir": [str(self.camp)]}, None)


class Armies(unittest.TestCase):
    def test_table_maps_the_five_conquest_armies_to_their_skin_folders(self):
        got = {c: catalog.army_info(c)["skins"] for c in ("ger", "rus", "eng", "usa", "fin")}
        self.assertEqual(got, {"ger": "germans", "rus": "soviets", "eng": "united_kingdom", "usa": "united_states", "fin": "finnish"})
        self.assertEqual(catalog.army_info("usa")["nation"], "usa")

    def test_unknown_or_empty_army_is_not_guessed(self):
        self.assertIsNone(catalog.army_info("ig"))
        self.assertIsNone(catalog.army_info(""))
        self.assertIsNone(catalog.army_info(None))


class Build(Base):
    def test_skins_are_filed_by_folder(self):
        self.assertEqual({v["nation"] for v in self.cat.skins.values()}, {"united_states", "soviets", "germans"})

    def test_ammo_totals_come_from_non_german_breeds_too(self):
        self.assertEqual(self.cat.total("rifle_usa.garand_clip"), 80)
        self.assertEqual(self.cat.stack("rifle_usa.garand_clip"), 8)
        self.assertEqual(self.cat.total("rifle_rus.mosin_clip"), 60)
        self.assertEqual(self.cat.total("rifle_ger.clip"), 60)

    def test_items_know_their_nation(self):
        self.assertEqual(self.cat.items["garand"]["nations"], ["usa"])
        self.assertEqual(self.cat.items["mosin"]["nations"], ["rus"])

    def test_headgear_nobody_packs_is_filed_by_the_army_in_its_name(self):
        n = lambda k: self.cat.items[k]["nations"]
        self.assertEqual((n("usa_cap_patrol"), n("sov_ushanka"), n("ger_stalhelm_m42"), n("plain_hat")), (["usa"], ["rus"], ["ger"], []))

    def test_identity_is_per_nation(self):
        by = self.data["identity"]["by_nation"]
        self.assertEqual(by["usa"]["portraits"][:1], ["usa_regular"])
        self.assertEqual(sorted(by["usa"]["portraits"]), ["usa_ranger", "usa_regular"])
        self.assertEqual(sorted(by["rus"]["portraits"]), ["rus_guards", "rus_regular"])
        self.assertNotIn("usa_ranger", by["rus"]["portraits"])
        self.assertIn("soldier_bazooka", by["usa"]["tags"])
        self.assertNotIn("soldier_bazooka", by["rus"]["tags"])

    def test_tag_for_weapon_is_read_from_the_nations_own_breeds(self):
        usa = self.data["identity"]["by_nation"]["usa"]["tag_for_weapon"]
        self.assertEqual(usa, {"bazooka_m1": "soldier_bazooka"})
        self.assertEqual(identity.suggest_tag(["garand", "bazooka_m1.weapon"], usa), "soldier_bazooka")
        self.assertEqual(identity.suggest_tag(["mosin"], self.data["identity"]["by_nation"]["rus"]["tag_for_weapon"]), "soldier")
        self.assertEqual(identity.suggest_tag(["panzershreck_54"], {}), "soldier")          # an empty table is not the German one

    def test_german_tag_table_keeps_its_base(self):
        self.assertEqual(self.data["identity"]["by_nation"]["ger"]["tag_for_weapon"].get("panzerfaust_60"), "soldier_pzfaust")

    def test_the_games_own_item_names_are_read(self):
        self.assertEqual(self.cat.item_names["garand"], "M1 Garand")
        self.assertEqual(self.cat.item_names["bazooka_m1.weapon"], "M1 'Bazooka' Launcher")
        self.assertEqual(self.cat.item_names["us_m1_helmet"], "M1 Helmet")                 # colour markup stripped


class Open(Base):
    def test_usa_save_opens_with_its_own_army_nation_names(self):
        d = self.open("usa.sav")
        self.assertEqual((d["army"], d["army_known"]), ("usa", True))
        self.assertEqual(d["army_info"]["label"], "American")
        self.assertEqual(d["army_info"]["skins"], "united_states")
        self.assertEqual(sorted(d["name_lists"]), ["usa"])
        self.assertEqual(d["name_lists"]["usa"]["first"], ["Hank", "Joe", "Bill"])
        self.assertEqual(len(d["soldiers"]), 2)

    def test_soldiers_read_skin_icon_tag_portrait_from_their_breed(self):
        s = {x["breed"]: x for x in self.open("usa.sav")["soldiers"]}
        a, b = s["mp/usa/late/rifleman"], s["mp/usa/late/ranger"]
        self.assertEqual((a["skin"], a["icon"], a["tag"], a["portrait"]), ("us_m41_rfl_1", "rifle", "soldier", "usa_regular"))
        self.assertEqual(b["portrait"], "usa_ranger")
        self.assertEqual(a["name_id"], [1, 1])

    def test_rus_save(self):
        d = self.open("rus.sav")
        self.assertEqual(d["army_info"]["skins"], "soviets")
        self.assertEqual(sorted(d["name_lists"]), ["rus"])
        self.assertEqual(d["soldiers"][0]["portrait"], "rus_regular")

    def test_unknown_army_opens_and_says_so(self):
        d = self.open("ig.sav")
        self.assertFalse(d["army_known"])
        self.assertEqual(d["army"], "ig")
        self.assertEqual(len(d["soldiers"]), 1)           # a breed no catalog knows still opens (no skin / portrait, no crash)
        self.assertIsNone(d["soldiers"][0]["portrait"])

    def test_item_names_ride_along(self):
        self.assertEqual(self.open("usa.sav")["item_names"]["garand"], "M1 Garand")


class Pickers(Base):
    def cands(self, save, role="primary", **extra):
        d = self.open(save)
        body = {"loadout": d["soldiers"][0]["loadout"], "role": role, "army": d["army"], "mods": d["mods"], **extra}
        return [i["name"] for i in server.api_candidates(None, body)["items"]]

    def test_usa_is_offered_usa_rifles_only(self):
        self.assertEqual(self.cands("usa.sav"), ["garand"])

    def test_rus_is_offered_soviet_rifles_only(self):
        self.assertEqual(self.cands("rus.sav"), ["mosin"])

    def test_the_soldiers_own_nation_beats_the_save_army(self):
        self.assertEqual(self.cands("usa.sav", nation="rus"), ["mosin"])

    def test_every_nation_switch_shows_everything(self):
        self.assertEqual(sorted(self.cands("usa.sav", everything=True)), ["garand", "k98", "mosin"])

    def test_unknown_army_offers_everything_instead_of_nothing(self):
        self.assertEqual(sorted(self.cands("ig.sav")), ["garand", "k98", "mosin"])

    def test_headgear_follows_the_nation(self):
        self.assertEqual(sorted(self.cands("usa.sav", "head")), ["us_m1_helmet", "usa_cap_patrol"])
        self.assertEqual(sorted(self.cands("rus.sav", "head")), ["sov_ssh40", "sov_ushanka"])
        self.assertIn("plain_hat", self.cands("usa.sav", "head", everything=True))

    def test_launcher_slot_offers_the_bazooka_to_the_us(self):
        self.assertEqual(self.cands("usa.sav", "launcher"), ["bazooka_m1.weapon"])

    def test_ammo_picker_is_nation_scoped_too(self):
        d = self.open("rus.sav")
        body = {"loadout": d["soldiers"][0]["loadout"], "army": "rus", "mods": []}
        names = [i["name"] for i in server.api_ammo_candidates(None, body)["items"]]
        self.assertIn("rifle_rus.mosin_clip", names)
        self.assertNotIn("rifle_usa.garand_clip", names)
        names = [i["name"] for i in server.api_ammo_candidates(None, {**body, "everything": True})["items"]]
        self.assertIn("rifle_usa.garand_clip", names)

    def test_equipping_a_us_rifle_gives_us_ammo_amounts(self):
        d = self.open("usa.sav")
        new, _ = lo.equip(d["soldiers"][0]["loadout"], self.cat, "primary", "garand")
        self.assertEqual(new["entries"][0]["tokens"], ["garand"])

    def test_skins_are_filtered_to_the_armys_folder(self):
        sk = lambda **b: {k["name"] for k in server.api_skins(None, {"mods": [], **b})["skins"]}
        self.assertEqual(sk(army="usa"), {"us_m41_rfl_1", "us_m41_rfl_2"})
        self.assertEqual(sk(army="rus"), {"sov_41_rkka_rfl_1", "sov_41_rkka_rfl_2"})
        self.assertEqual(sk(army="ger"), {"ger_heer_43_rfl_1"})
        self.assertEqual(sk(army="usa", everything=True), set(SKINS))
        self.assertEqual(sk(army="ig"), set(SKINS))                       # unknown army: no filtering
        self.assertEqual(sk(), set(SKINS))
        self.assertTrue(server.api_skins(None, {"mods": [], "army": "usa"})["filtered"])
        self.assertFalse(server.api_skins(None, {"mods": [], "army": "ig"})["filtered"])


class Save(Base):
    """Breed generation with portrait / icon / tag / skin for a non-German soldier, end to end through server.api_save."""

    def save(self, name, army_file, **look):
        d = self.open(army_file)
        s = d["soldiers"][0]
        r = server.api_save(None, {"file": army_file, "dir": str(self.camp), "name": name, "edits": [], "looks": {s["eid"]: look}})
        return s, r

    def breed_texts(self):
        with zipfile.ZipFile(self.mods / breeds.MOD_ID / "resource" / "gamelogic.pak") as z:
            return {n: z.read(n).decode() for n in z.namelist()}

    def test_usa_portrait_icon_tag_skin_land_in_a_new_breed(self):
        s, r = self.save("UsaCopy", "usa.sav", portrait="usa_ranger", icon="bazooka", tag="soldier_bazooka", skin="us_m41_rfl_2", vet=3)
        self.assertEqual(r["breeds"], 1)
        (name, text), = self.breed_texts().items()
        self.assertTrue(name.startswith("set/breed/mp/usa/late/arm_"))
        self.assertIn('{portrait "usa_ranger"}', text)
        self.assertIn('{icon "bazooka"}', text)
        self.assertIn('{tags "soldier_bazooka"}', text)
        self.assertIn('{skin "us_m41_rfl_2"}', text)
        self.assertIn('("veterancy_lvl_3")', text)
        self.assertEqual(text.count("{portrait"), 1)
        out = sf.open_save(pathlib.Path(r["path"]), self.cat)
        new = next(x for x in out["soldiers"] if x["eid"] == s["eid"])
        self.assertEqual(new["breed"], "mp/usa/late/" + name.split("/")[-1][:-4])
        self.assertIn(breeds.MOD_ID, out["mods"])
        untouched = next(x for x in out["soldiers"] if x["eid"] != s["eid"])
        self.assertEqual(untouched["breed"], "mp/usa/late/ranger")

    def test_new_breed_is_named_in_the_games_localization(self):
        self.save("UsaCopy2", "usa.sav", portrait="usa_ranger")
        names = breeds.read_loc(self.mods / breeds.MOD_ID / "localizations" / "default.pak")
        (path, label), = names.items()
        self.assertTrue(path.startswith("mp/usa/late/arm_"))
        self.assertTrue(label)

    def test_reopening_a_copy_reads_the_new_portrait_and_a_readable_role(self):
        s, r = self.save("UsaCopy3", "usa.sav", portrait="usa_ranger")
        d = server.api_open({"file": [r["file"]], "dir": [str(self.camp)]}, None)
        new = next(x for x in d["soldiers"] if x["eid"] == s["eid"])
        self.assertEqual(new["portrait"], "usa_ranger")
        self.assertFalse(new["role"].lower().startswith("arm "), new["role"])

    def test_rus_portrait(self):
        _, r = self.save("RusCopy", "rus.sav", portrait="rus_guards")
        (_, text), = self.breed_texts().items()
        self.assertIn('{portrait "rus_guards"}', text)

    def test_a_portrait_of_another_nation_is_still_a_value_the_game_uses(self):
        # the server only checks that the value exists in the game's breeds (identity.clean); it does not tie it to the nation
        self.save("Cross", "usa.sav", portrait="rus_guards")

    def test_a_made_up_portrait_is_refused(self):
        with self.assertRaises(lo.LoadoutError):
            self.save("Bad", "usa.sav", portrait="usa_made_up")

    def test_loadout_edit_with_portrait_on_a_rus_soldier(self):
        d = self.open("rus.sav")
        s = d["soldiers"][0]
        mid = s["loadout"]
        r = server.api_save(None, {"file": "rus.sav", "dir": str(self.camp), "name": "RusKit", "edits": [mid],
                                   "looks": {s["eid"]: {"portrait": "rus_guards"}}})
        (_, text), = self.breed_texts().items()
        self.assertIn('{portrait "rus_guards"}', text)
        self.assertIn('{item "mosin" filled}', text)
        self.assertTrue(pathlib.Path(r["path"]).is_file())

    def test_source_save_is_never_touched(self):
        before = self.usa.read_bytes()
        self.save("Copy4", "usa.sav", portrait="usa_ranger")
        self.assertEqual(before, self.usa.read_bytes())


class Names(Base):
    def test_rename_uses_the_soldiers_own_nations_list(self):
        d = self.open("rus.sav")
        s = d["soldiers"][0]
        r = server.api_save(None, {"file": "rus.sav", "dir": str(self.camp), "name": "Renamed", "edits": [],
                                   "names": {s["eid"]: [1, 2]}})
        again = sf.open_save(pathlib.Path(r["path"]), self.cat)["soldiers"][0]
        self.assertEqual(again["name_id"], [1, 2])
        lists = self.open("rus.sav")["name_lists"]["rus"]
        self.assertEqual((lists["first"][1], lists["last"][2]), ("Pyotr", "Volkov"))

    def test_index_past_the_end_of_that_nations_list_is_refused(self):
        s = self.open("usa.sav")["soldiers"][0]          # usa: 3 first names, 2 last names
        with self.assertRaises(lo.LoadoutError):
            server.check_names(self.usa, {s["eid"]: [0, 2]})

    def test_unknown_army_cannot_be_renamed_but_says_why(self):
        s = self.open("ig.sav")["soldiers"][0]
        with self.assertRaises(lo.LoadoutError) as c:
            server.check_names(self.ig, {s["eid"]: [0, 0]})
        self.assertIn("ig", str(c.exception))


if __name__ == "__main__":
    unittest.main(verbosity=1)
