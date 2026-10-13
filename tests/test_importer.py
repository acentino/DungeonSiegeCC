import sys, tempfile, unittest, struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from importer import new_project, validate, export_sources

class ImporterTests(unittest.TestCase):
    def test_native_defaults(self):
        p=new_project()
        self.assertTrue(all(a["source"]=="native" for a in p["animations"].values()))
    def test_model_required(self):
        self.assertTrue(validate(new_project()))
    def test_staging(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            model=root/"model.pmd"
            model.write_bytes(b"Pmd"+b"0"*10)
            p=new_project()
            p.update({"name":"Miku","identifier":"miku","model":str(model)})
            self.assertEqual(validate(p),[])
            out=export_sources(p,root/"export")
            self.assertTrue((out/"source_assets"/"model.pmd").is_file())
            self.assertFalse((out/"miku.ds2res").exists())
    def test_vmd_validation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            model=root/"model.pmx"
            model.write_bytes(b"PMX ")
            motion=root/"idle.vmd"
            motion.write_bytes(b"not a valid motion")
            p=new_project()
            p.update({"model":str(model)})
            p["animations"]["idle"]={"source":"custom","file":str(motion)}
            self.assertTrue(any("idle" in e for e in validate(p)))

if __name__=="__main__":unittest.main()
