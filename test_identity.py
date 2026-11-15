"""Tests for icon / tag edits (breed text) and soldier names (save text)."""
import pathlib
import re
import shutil
import tempfile
import unittest
import zipfile

import breeds
import identity
import loadout as lo
import savefile

FIX = pathlib.Path(__file__).parent / "fixtures"
BREED = '''{breed
	{behaviour soldier}
	{skin "ger_heer_43_at_rkt_asst"}
	{icon "smg"}
	{icon_priority 0}
	{tags "soldier_pzfaust"}
	{portrait "ger_regular"}
	{perks
		(include "ability.inc")
		("rifle_skill_rank_2")
	}
	{veterancy
		(include "ability.inc")
		("veterancy_lvl_0")
	}
	{inventory
		{item "mp40_folded" filled}
	}
}
'''
NOTAGS = BREED.replace('\t{tags "soldier_pzfaust"}\n', "")
ICONS, TAGS = ["rifle", "smg", "bazooka"], ["soldier", "soldier_pzscheck", "crew"]


class I(unittest.TestCase):
    def test_read(self):
        self.assertEqual(identity.read(BREED), {"icon": "smg", "tag": "soldier_pzfaust", "portrait": "ger_regular"})

    def test_icon_tag_replaced_in_place(self):
        out = identity.apply(BREED, icon="bazooka", tag="soldier_pzscheck")
        self.assertEqual({k: identity.read(out)[k] for k in ("icon", "tag")}, {"icon": "bazooka", "tag": "soldier_pzscheck"})
        self.assertIn('{icon_priority 0}', out)              # icon_priority must not be mistaken for the icon
        self.assertIn('("rifle_skill_rank_2")', out)

    def test_only_what_is_given_changes(self):
        out = identity.apply(BREED, tag="crew")
        self.assertEqual({k: identity.read(out)[k] for k in ("icon", "tag")}, {"icon": "smg", "tag": "crew"})

    def test_missing_tags_line_is_added(self):
        out = identity.apply(NOTAGS, tag="soldier")
        self.assertEqual(identity.read(out)["tag"], "soldier")
        self.assertTrue(out.startswith("{breed\n"))

    def test_clean_rejects_values_the_game_does_not_use(self):
        with self.assertRaises(ValueError):
            identity.clean({"icon": "laser"}, ICONS, TAGS)
        with self.assertRaises(ValueError):
            identity.clean({"tag": "god"}, ICONS, TAGS)
        self.assertEqual(identity.clean({"icon": "rifle", "other": 1}, ICONS, TAGS), {"icon": "rifle"})

    def test_portrait_replaced_and_added(self):
        out = identity.apply(BREED, portrait="ger_pionier")
        self.assertEqual(identity.read(out)["portrait"], "ger_pionier")
        self.assertEqual(identity.read(out)["icon"], "smg")                 # nothing else moves
        bare = re.sub(r'[ \t]*\{portrait "ger_regular"\}\n', "", BREED)
        self.assertIsNone(identity.read(bare)["portrait"])
        self.assertEqual(identity.read(identity.apply(bare, portrait="ger_gd"))["portrait"], "ger_gd")

    def test_clean_checks_portraits(self):
        with self.assertRaises(ValueError):
            identity.clean({"portrait": "nope"}, ICONS, TAGS, ["ger_regular"])
        self.assertEqual(identity.clean({"portrait": "ger_regular"}, ICONS, TAGS, ["ger_regular"]), {"portrait": "ger_regular"})

    def test_make_breed_applies_portrait(self):
        out = breeds.make_breed(BREED, None, skin="ger_heer_43_nco", vet=1, portrait="ger_scout")
        self.assertEqual(identity.read(out)["portrait"], "ger_scout")

    def test_suggest_tag_follows_the_launcher(self):
        self.assertEqual(identity.suggest_tag(["mp40_folded", "panzershreck_54"]), "soldier_pzscheck")
        self.assertEqual(identity.suggest_tag(["k98"]), "soldier")

    def test_make_breed_applies_icon_and_tag_with_everything_else(self):
        out = breeds.make_breed(BREED, None, skin="ger_heer_43_nco", vet=3, icon="rifle", tag="soldier")
        self.assertEqual({k: identity.read(out)[k] for k in ("icon", "tag")}, {"icon": "rifle", "tag": "soldier"})
        self.assertIn('{skin "ger_heer_43_nco"}', out)


class L(unittest.TestCase):
    """Generated breeds need an on-screen name, or the game prints the raw key desc/human/<breed path>."""

    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def pot(self):
        return zipfile.ZipFile(self.d / "armory_breeds" / "localizations" / "default.pak").read(breeds.LOC_FILE).decode()

    def files(self, newp, base):
        f = breeds.Files({newp: BREED})
        f.labels[newp] = base
        return f

    def test_new_breed_gets_the_name_of_its_base(self):
        breeds.install(self.d, self.files("mp/ger/mid/arm_aaa", "mp/ger/mid/rifleman_1"), self.d, {"mp/ger/mid/rifleman_1": "Rifleman"})
        self.assertIn('msgctxt "desc/human/mp/ger/mid/arm_aaa"\nmsgid "Rifleman"', self.pot())

    def test_regenerated_breed_keeps_the_name_it_already_had(self):
        breeds.install(self.d, self.files("mp/ger/mid/arm_aaa", "mp/ger/mid/nco"), self.d, {"mp/ger/mid/nco": "Squad Leader"})
        breeds.install(self.d, self.files("mp/ger/mid/arm_bbb", "mp/ger/mid/arm_aaa"), self.d, {})
        t = self.pot()
        self.assertIn('desc/human/mp/ger/mid/arm_bbb"\nmsgid "Squad Leader"', t)
        self.assertIn('desc/human/mp/ger/mid/arm_aaa"\nmsgid "Squad Leader"', t)      # older breeds stay named

    def test_unknown_base_falls_back_to_a_readable_name(self):
        breeds.install(self.d, self.files("mp/ger/mid/arm_ccc", "mp/ger/mid/vet_rifle"), self.d, {})
        self.assertIn('msgid "Vet rifle"', self.pot())

    def test_breeds_from_before_names_existed_are_backfilled(self):
        breeds.install(self.d, breeds.Files({"mp/ger/mid/arm_old": BREED}), self.d, {})          # no labels at all
        self.assertIn('desc/human/mp/ger/mid/arm_old"\nmsgid "Soldier"', self.pot())

    def test_quotes_in_names_survive_a_round_trip(self):
        breeds.install(self.d, self.files("mp/ger/mid/arm_q", "mp/ger/mid/x"), self.d, {"mp/ger/mid/x": 'The "Boss"'})
        self.assertEqual(breeds.read_loc(self.d / "armory_breeds" / "localizations" / "default.pak")["mp/ger/mid/arm_q"], 'The "Boss"')


@unittest.skipUnless((pathlib.Path(__file__).parent / "fixtures" / "fresh_ger.sav").exists(), "fixtures/fresh_ger.sav is not in this checkout")
class N(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp())
        self.src = self.d / "a.sav"
        shutil.copy(FIX / "fresh_ger.sav", self.src)
        self.cat = lo.Catalog()
        self.sd = savefile.open_save(self.src, self.cat)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def scn(self, p):
        return zipfile.ZipFile(p).read("campaign.scn").decode().replace("\r", "")

    def test_every_soldier_has_a_name_id(self):
        self.assertTrue(all(s["name_id"] and len(s["name_id"]) == 2 for s in self.sd["soldiers"]))

    def test_rename_changes_only_that_soldier(self):
        a, b = self.sd["soldiers"][0], self.sd["soldiers"][1]
        out = savefile.write_copy(self.src, {}, "Renamed", names={a["eid"]: [5, 7]})
        after = {s["eid"]: s["name_id"] for s in savefile.open_save(out, self.cat)["soldiers"]}
        self.assertEqual(after[a["eid"]], [5, 7])
        self.assertEqual(after[b["eid"]], b["name_id"])
        # nothing else in the file moved
        norm = lambda t: re.sub(r"\{NameId \d+ \d+\}", "{NameId}", t)
        self.assertEqual(norm(self.scn(self.src)), norm(self.scn(out)))

    def test_unknown_soldier_is_an_error(self):
        with self.assertRaises(ValueError):
            savefile.write_copy(self.src, {}, "Bad", names={"0xdead": [1, 1]})


if __name__ == "__main__":
    unittest.main(verbosity=1)
