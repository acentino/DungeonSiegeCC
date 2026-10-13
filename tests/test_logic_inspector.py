import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import logic_inspector as lib


GAS = r'''
// Commented-out fake template: [t:template,n:fake_pm]
[t:template,n:base_pm_fg]
{
    specializes = base_farmgirl;
    [store] { can_sell_self = true; }
    [aspect] { gold_value = 150; }
    /* "quoted comment" */
}
[t:template,n:dalvi_donor]
{
    specializes = base_pm_fg;
    [common] { screen_name = "Dalvi"; }
    [mind] { jat_talk = "world\ai\jobs\common\job_talk.skrit"; }
}
[t:template,n:other_actor]
{
    specializes = base_npc_female;
    [common] { screen_name = "Not a recruit"; }
}
'''

class TestLogicInspector(unittest.TestCase):
    def setUp(self):
        context = tempfile.TemporaryDirectory()
        self.addCleanup(context.cleanup)
        self.root = Path(context.name)
        self.zip = self.root / "LogicReferences.zip"
        with zipfile.ZipFile(self.zip, "w", zipfile.ZIP_DEFLATED) as f:
            f.writestr("world/contentdb/templates/regular/actors/good/pm_fg_based.gas", GAS)
            f.writestr("world/ai/jobs/common/job_talk.skrit", "code")

    def test_zip_index_discovers_hirable_template(self):
        report = lib.inspect_logic_source(self.zip)
        self.assertEqual(report["gas_file_count"], 1)
        self.assertEqual(report["template_count"], 3)
        self.assertEqual(report["potential_recruitable_count"], 2)
        candidates = {x["template"]:x for x in report["potential_recruitable"]}
        self.assertEqual(candidates["dalvi_donor"]["screen_name"], "Dalvi")
        self.assertIn("base_pm_fg", candidates["dalvi_donor"]["template_chain"])
        self.assertNotIn("other_actor", candidates)

    def test_actor_donors_without_base_pm(self):
        """Regression for real scans showing 0 base_pm matches."""
        sample = """
[t:template,n:base_villager] { [common] { screen_name = "Village Base"; } }
[t:template,n:vendor_donor] {
    specializes = base_villager;
    [common] { screen_name = "Friendly Villager"; }
    [mind] { jat_talk = "world/ai/jobs/talk.skrit"; }
}
[t:template,n:lost_actor] {
    specializes = missing_game_base;
    [common] { screen_name = "Unknown Ancestor"; }
}
"""
        path=self.root/"no_base_pm.zip"
        with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("world/contentdb/templates/regular/actors/good/villagers.gas",sample)
            z.writestr("world/contentdb/templates/regular/items/weapons.gas",
                       "[t:template,n:sword] { specializes = weapon_base; }")
        report=lib.inspect_logic_source(path)
        self.assertEqual(report["potential_recruitable_count"],0)
        self.assertGreaterEqual(report["donor_candidate_count"],2)
        donors={item["template"]:item for item in report["donor_candidates"]}
        self.assertIn("vendor_donor",donors)
        self.assertIn("actor directory",donors["vendor_donor"]["donor_reasons"])
        self.assertNotIn("sword",donors)
        self.assertFalse(donors["lost_actor"]["inheritance_complete"])
        self.assertGreater(report["diagnostics"]["unresolved_specialization_count"],0)

    def test_dalvi_references_exclude_monsters_and_rank_known_companions(self):
        specimen = """
[t:template,n:base_agallan_giant] { [common] { screen_name = "Agallan Giant"; } }
[t:template,n:npc_ghost_threnith] { [common] { screen_name = "Ghost"; } }
[t:template,n:npc_morden_kohl_beast] { [common] { screen_name = "Morden-Vir Cavalry"; } }
[t:template,n:siege_bug_npc] { [common] { screen_name = "Siege Bug"; } }
[t:template,n:npc_evangeline] {
    specializes = base_human_female;
    [common] { screen_name = "Evangeline"; }
}
[t:template,n:human_female_villager] {
    specializes = base_npc_human;
    [common] { screen_name = "Female Villager"; }
}
"""
        zfile=self.root/"actors.zip"
        with zipfile.ZipFile(zfile,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("world/contentdb/templates/regular/actors/good/actors.gas", specimen)
        report=lib.inspect_logic_source(zfile)
        self.assertEqual(report["potential_recruitable_count"], 0)
        self.assertGreaterEqual(report["donor_candidate_count"], 6)
        recommended={x["template"]:x for x in report["humanoid_candidates"]}
        for name in ("base_agallan_giant","npc_ghost_threnith",
                     "npc_morden_kohl_beast","siege_bug_npc"):
            self.assertNotIn(name,recommended)
        self.assertIn("npc_evangeline",recommended)
        self.assertIn("human_female_villager",recommended)
        self.assertEqual(report["humanoid_candidates"][0]["template"],"npc_evangeline")
        self.assertGreaterEqual(report["excluded_non_humanoid_count"],4)
        self.assertIn("known DS2 companion name: evangeline",
                      recommended["npc_evangeline"]["compatibility_reasons"])

    def test_companion_names_are_whole_tokens(self):
        item={"source_file":"world/actors/good/test.gas","screen_name":"Vixen",
              "can_sell_self_explicit":"","talk_job":""}
        result=lib.donor_compatibility(item,["generic_actor"])
        self.assertNotEqual(result["compatibility_category"],"known_companion_reference")
        named=dict(item,screen_name="Deru")
        self.assertEqual(lib.donor_compatibility(named,["npc_deru"])["compatibility_category"],
                         "known_companion_reference")

    def test_windows_archive_paths_match_actor_directory(self):
        item={"source_file":r"world\\contentdb\\templates\\regular\\actors\\good\\town.gas",
              "screen_name":"Town Friend","talk_job":"","can_sell_self_explicit":""}
        score, reasons=lib.rank_donor(item,["town_friend"])
        self.assertGreaterEqual(score,60)
        self.assertIn("actor directory",reasons)

    def test_donor_validation(self):
        item = lib.verify_donor_in_source(self.zip, "dalvi_donor")
        self.assertEqual(item["screen_name"], "Dalvi")
        with self.assertRaises(lib.LogicAnalysisError):
            lib.verify_donor_in_source(self.zip, "fake_pm")
        with self.assertRaises(lib.LogicAnalysisError):
            lib.verify_donor_in_source(self.zip, "../bad")

    def test_directory_matches_zip(self):
        folder = self.root/"logic"
        folder.mkdir()
        (folder/"templates.gas").write_text(GAS, encoding="utf-8")
        self.assertEqual(
            lib.inspect_logic_source(folder)["potential_recruitable_count"],
            lib.inspect_logic_source(self.zip)["potential_recruitable_count"])

    def test_path_traversal_is_rejected(self):
        source = self.root/"evil.zip"
        with zipfile.ZipFile(source,"w") as f:
            f.writestr("../evil.gas", GAS)
        with self.assertRaises(lib.LogicAnalysisError):
            lib.inspect_logic_source(source)
        self.assertFalse((self.root/"evil.gas").exists())

    def test_report_excludes_script_bodies(self):
        output = self.root/"report.json"
        lib.write_report(self.zip,output)
        data=json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(data["potential_recruitable"])
        self.assertNotIn("Commented-out fake", output.read_text())

if __name__ == "__main__":
    unittest.main()
