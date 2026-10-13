import tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import game_pipeline as g
class Tests(unittest.TestCase):
    def test_template_is_sanitized(self):
        text=g.generate_leaf('miku','Hatsune Miku','base_pm_fg')
        self.assertIn('[t:template,n:dscc_miku]',text)
        self.assertIn('specializes = base_pm_fg;',text)
        with self.assertRaises(g.PipelineError): g.generate_leaf('bad]','hi','base_pm_fg')
        with self.assertRaises(g.PipelineError): g.generate_leaf('hi','Bad\nName','base_pm_fg')
    def test_donor_required(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            donor=root/'logic'/'characters.gas';donor.parent.mkdir()
            donor.write_text('[t:template,n:base_pm_fg]\n{ specializes = base_farmgirl; }')
            dest=g.stage_leaf(root/'out','miku','Hatsune Miku','base_pm_fg',root/'logic')
            self.assertTrue(dest.exists())
            self.assertTrue((root/'out'/'GAME_BUILD_REQUIREMENTS.json').exists())
            with self.assertRaises(g.PipelineError):g.stage_leaf(root/'out','a','Test','wrong',root/'logic')
    def test_zipped_logic_donor_source(self):
        import zipfile
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            archive=root/'logic_references.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('world/contentdb/templates/regular/actors/good/pms.gas',
                    '[t:template,n:base_pm_fg]\n{ specializes = base_human; }')
            output=g.stage_leaf(root/'out','dalvi','Dalvi','base_pm_fg',archive)
            self.assertTrue(output.is_file())
            self.assertIn('logic_references.zip', (root/'out'/'GAME_BUILD_REQUIREMENTS.json').read_text())

if __name__=='__main__':unittest.main()
