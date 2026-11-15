"""Tests for perk (skill) reading and rewriting. Uses breed text shaped exactly like the game's own files."""
import unittest

import breeds
import perks

AT = '''{breed
	{behaviour soldier}
	{skin "ger_heer_43_at_rkt_asst"}
	{perks
		(include "ability.inc")
		("rifle_skill_rank_2")("tier2_standard")
		("at_rank_3")
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
TANK = '''{breed
	{perks
		(include "ability.inc")
		("rifle_skill_rank_2")("tier2_standard")
		("loader_skill_smg_rank_2")("skilled_repair")
		("tank_commander")
	}
	{inventory
		{item "k98" filled}
	}
}
'''


class P(unittest.TestCase):
    def test_read(self):
        self.assertEqual(perks.read(AT), {"skill": "rifle_skill_rank_2", "tier": "tier2_standard", "at": 3, "extras": []})

    def test_read_none_without_block(self):
        self.assertIsNone(perks.read("{breed {skin \"x\"}}"))

    def test_change_skill_only_keeps_the_rest(self):
        out = perks.apply(AT, {"skill": "smg_skill_rank_4"})
        self.assertEqual(perks.read(out), {"skill": "smg_skill_rank_4", "tier": "tier2_standard", "at": 3, "extras": []})
        self.assertIn('(include "ability.inc")', out)
        self.assertIn('("veterancy_lvl_0")', out)            # other blocks untouched
        self.assertIn('{item "mp40_folded" filled}', out)

    def test_tier_and_extras(self):
        out = perks.apply(AT, {"tier": "tier4_recon", "extras": ["stealth", "medic"], "at": 0})
        self.assertEqual(perks.read(out), {"skill": "rifle_skill_rank_2", "tier": "tier4_recon", "at": 0, "extras": ["stealth", "medic"]})

    def test_untouched_layers_are_not_rewritten(self):
        out = perks.apply(TANK, {"tier": "tier3_defense"})
        for keep in ("loader_skill_smg_rank_2", "skilled_repair", "tank_commander", "rifle_skill_rank_2"):
            self.assertIn(f'("{keep}")', out)
        self.assertNotIn("tier2_standard", out)
        self.assertIn("tier3_defense", out)

    def test_unmanaged_presets_survive_a_skill_change(self):
        out = perks.apply(TANK, {"skill": "mg_skill_rank_3", "extras": []})
        self.assertIn("tank_commander", out)                  # not one of the layers we manage
        self.assertNotIn("skilled_repair", out)               # an extras layer, so it was cleared

    def test_empty_spec_is_a_no_op(self):
        self.assertEqual(perks.apply(AT, {}), AT)
        self.assertEqual(perks.apply(AT, None), AT)

    def test_rejects_unknown_names(self):
        with self.assertRaises(ValueError):
            perks.apply(AT, {"skill": "godmode"})
        with self.assertRaises(ValueError):
            perks.apply(AT, {"tier": "tier9_standard"})
        with self.assertRaises(ValueError):
            perks.apply(AT, {"extras": ["stealth", "nuke"]})
        with self.assertRaises(ValueError):
            perks.apply(AT, {"at": 9})

    def test_idempotent(self):
        spec = {"skill": "mg_skill_rank_5", "tier": "tier1_defense", "at": 1, "extras": ["stealth"]}
        once = perks.apply(AT, spec)
        self.assertEqual(perks.apply(once, spec), once)

    def test_make_breed_applies_perks_with_skin_and_vet(self):
        out = breeds.make_breed(AT, None, skin="ger_heer_43_nco", vet=5, perks={"skill": "smg_skill_rank_3"})
        self.assertIn('{skin "ger_heer_43_nco"}', out)
        self.assertIn('("veterancy_lvl_5")', out)
        self.assertEqual(perks.read(out)["skill"], "smg_skill_rank_3")

    def test_skill_presets_report_what_they_set_per_weapon(self):
        inc = {"skills": '(define "rifle_skill_rank_2"\n\t("at_rank_2")\n\t{"pistol" lvl_3}\n\t{"smg" lvl_2}\n\t{"rifle" lvl_3}\n\t{"melee" lvl_2}\n)\n'}
        s = perks.read_presets(inc)["skills"][0]
        self.assertEqual(s["levels"], {"pistol": 3, "smg": 2, "rifle": 3, "melee": 2})

    def test_presets_from_game_text(self):
        inc = {"skills": '(define "skill_rank_0")(define "rifle_skill_rank_1")(define "loader_skill_smg_rank_2")(define "at_rank_6")',
               "health": '(define "tier1_defense")(define "civilian")(define "tier3_recon")',
               "spec": '(define "stealth")(define "tank_commander")'}
        r = perks.read_presets(inc)
        self.assertEqual([s["name"] for s in r["skills"]], ["skill_rank_0", "rifle_skill_rank_1", "loader_skill_smg_rank_2"])
        self.assertEqual([t["name"] for t in r["tiers"]], ["tier1_defense", "tier3_recon"])
        self.assertEqual(r["at_max"], 6)
        self.assertEqual(r["extras"], ["stealth"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
