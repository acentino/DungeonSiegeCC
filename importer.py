"""DungeonSiegeCC desktop companion project editor (Python 3.10+)."""
import json, re, shutil, struct, tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox, simpledialog
import manager
import mmd_assets
import game_pipeline
import asset_probe
import ds2_tank
import logic_inspector

SLOTS = ["default_stance","fight_stance","idle","walk","run","melee_attack","ranged_attack","spell_cast","hit","death"]
def new_project():
    return {"version":1,"name":"New Companion","identifier":"new_companion","model":"","class_note":"Fighter","spawn_note":"","recruitment_dialogue":"Join my party?","donor_template":"","donor_root":"","animations":{k:{"source":"native","file":""} for k in SLOTS}}

def validate(p):
    errors=[]
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}",p.get("identifier","")): errors.append("Unique ID must contain letters, numbers and underscores only.")
    if not p.get("name","").strip(): errors.append("Name required.")
    model=Path(p.get("model") or ".")
    if not model.is_file() or model.suffix.lower() not in (".pmx",".pmd"): errors.append("Choose an existing PMX/PMD model.")
    for k in SLOTS:
        a=p.get("animations",{}).get(k,{})
        if a.get("source")=="custom":
            f=Path(a.get("file") or ".")
            if not f.is_file() or f.suffix.lower()!=".vmd": errors.append(k+": missing .vmd file")
            else:
                with f.open("rb") as stream:
                    if not stream.read(30).startswith(b"Vocaloid Motion Data"): errors.append(k+": invalid VMD header")
    return errors

def export_sources(p,directory):
    errors=validate(p)
    if errors: raise ValueError("\n".join(errors))
    target=Path(directory)/p["identifier"]
    if target.exists(): raise FileExistsError("Export already exists: "+str(target))
    assets=target/"source_assets"
    assets.mkdir(parents=True)
    try:
        data=json.loads(json.dumps(p))
        model=Path(p["model"])
        shutil.copy2(model,assets/("model"+model.suffix.lower()))
        data["model"]=str(Path("source_assets")/("model"+model.suffix.lower()))
        for k in SLOTS:
            a=data["animations"][k]
            if a["source"]=="custom":
                shutil.copy2(a["file"],assets/(k+".vmd"))
                a["file"]=str(Path("source_assets")/(k+".vmd"))
            else: a["file"]=""
        # Produce inspection/conversion intermediates alongside untouched sources.
        neutral=target/"neutral_intermediates"
        neutral.mkdir()
        if model.suffix.lower()==".pmx":
            mmd_assets.export_obj(model,neutral/"model.obj")
        for slot in SLOTS:
            animation=p["animations"].get(slot,{})
            if animation.get("source")=="custom":
                mmd_assets.export_motion(animation["file"],neutral/(slot+".motion.json"))
        if p.get("donor_template") and p.get("donor_root"):
            game_pipeline.stage_leaf(target/"game_overlay",p["identifier"],p["name"],p["donor_template"],p["donor_root"])
        (target/"project.json").write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
        (target/"BUILD_STATUS.txt").write_text("SOURCE PACKAGE ONLY. Not a playable Dungeon Siege II mod. ASP/PRS conversion, GAS/Skrit recruitment scripts and DS2 resource packaging are not yet implemented.\n",encoding="utf-8")
    except Exception:
        shutil.rmtree(target,ignore_errors=True)
        raise
    return target

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DungeonSiegeCC — MMD Companion Importer")
        self.geometry("930x790")
        self.settings=manager.load_settings()
        self.game=tk.StringVar(value=self.settings.get("game_path",""))
        self.vars={k:tk.StringVar(value=v) for k,v in new_project().items() if isinstance(v,str)}
        self.sources={k:tk.StringVar(value="native") for k in SLOTS}
        self.motions={k:tk.StringVar() for k in SLOTS}
        self.project_file=None
        self.build_ui()
        self._startup_framework_running = False
        self._pending_startup_update = None
        self._checking_updates = False
        self.after(100, self.startup_checks)

    def build_ui(self):
        root=ttk.Frame(self,padding=12);root.pack(fill="both",expand=True)
        ttk.Label(root,text="DungeonSiegeCC — MMD Companion Importer",font=("Segoe UI",16,"bold")).pack(anchor="w")
        ttk.Label(root,text="Source staging only: game-ready character conversion is not implemented.").pack(anchor="w",pady=(2,10))
        game=ttk.LabelFrame(root,text="Dungeon Siege II & framework",padding=8);game.pack(fill="x")
        game.columnconfigure(0,weight=1)
        ttk.Entry(game,textvariable=self.game,state="readonly").grid(row=0,column=0,sticky="ew")
        ttk.Button(game,text="Choose game folder",command=self.choose_game).grid(row=0,column=1)
        ttk.Button(game,text="Framework status / install",command=self.framework).grid(row=1,column=0,sticky="w",pady=5)
        ttk.Button(game,text="Check for updates",command=self.check_update).grid(row=1,column=1)
        ttk.Button(game,text="Inspect local game archives",command=self.inspect_game_archives).grid(row=2,column=0,sticky="w")
        ttk.Button(game,text="Import MMD model ZIP",command=self.import_mmd_zip).grid(row=2,column=1,sticky="w")
        ttk.Button(game,text="Extract Logic GAS/Skrit",command=self.extract_logic_references).grid(row=3,column=0,sticky="w")
        ttk.Button(game,text="Extract filtered ASP/PRS",command=self.extract_object_references).grid(row=3,column=1,sticky="w")
        toolbar=ttk.Frame(root);toolbar.pack(fill="x",pady=8)
        for label,fun in [("New",self.reset),("Open",self.open_project),("Save",self.save_project),("Validate",self.check),("Export source package",self.export)]:
            ttk.Button(toolbar,text=label,command=fun).pack(side="left",padx=3)
        inspectbar=ttk.Frame(root);inspectbar.pack(fill="x")
        ttk.Button(inspectbar,text="Inspect MMD model",command=self.inspect_model).pack(side="left",padx=3)
        ttk.Button(inspectbar,text="Inspect VMD overrides",command=self.inspect_motion).pack(side="left",padx=3)
        ttk.Button(inspectbar,text="Analyze Logic reference ZIP",command=self.inspect_logic_zip).pack(side="left",padx=3)
        info=ttk.LabelFrame(root,text="Companion",padding=8);info.pack(fill="x");info.columnconfigure(1,weight=1)
        for i,(key,title) in enumerate([("name","Name"),("identifier","Unique ID"),("model","MMD model (.pmx/.pmd)"),("class_note","Class"),("recruitment_dialogue","Recruitment dialogue"),("spawn_note","Spawn location note"),("donor_template","DS2 donor actor ID"),("donor_root","Extracted Logic GAS folder")]):
            ttk.Label(info,text=title).grid(row=i,column=0,sticky="w")
            ttk.Entry(info,textvariable=self.vars[key]).grid(row=i,column=1,sticky="ew",pady=3)
            if key=="model":ttk.Button(info,text="Browse",command=self.browse_model).grid(row=i,column=2)
            if key=="donor_root":ttk.Button(info,text="Browse",command=self.browse_donor_root).grid(row=i,column=2)
        animations=ttk.LabelFrame(root,text="Per-animation override · Native by default",padding=8);animations.pack(fill="both",expand=True,pady=8)
        animations.columnconfigure(2,weight=1)
        for i,k in enumerate(SLOTS):
            ttk.Label(animations,text=k.replace("_"," ").title()).grid(row=i,column=0,sticky="w",pady=4)
            ttk.Combobox(animations,textvariable=self.sources[k],values=("native","custom"),state="readonly",width=9).grid(row=i,column=1)
            ttk.Entry(animations,textvariable=self.motions[k]).grid(row=i,column=2,sticky="ew",padx=5)
            ttk.Button(animations,text="Browse",command=lambda key=k:self.browse_vmd(key)).grid(row=i,column=3)
            ttk.Button(animations,text="Reset",command=lambda key=k:self.reset_motion(key)).grid(row=i,column=4)
        self.status=tk.StringVar(value="Ready")
        ttk.Label(root,textvariable=self.status,wraplength=850).pack(anchor="w")

    def inspect_game_archives(self):
        """Read tank indices locally, never publish or modify original files."""
        game=self.game.get()
        if not manager.valid_game_folder(game):
            messagebox.showwarning("Game folder","Choose a valid Dungeon Siege II folder first.")
            return
        self.status.set("Reading Logic and Objects tank indices...")
        import threading
        def worker():
            try:
                basic=asset_probe.scan_game_archives(game)
                deep=ds2_tank.game_inventory(game)
                location=manager.settings_path().parent/"local_asset_report.json"
                location.parent.mkdir(parents=True,exist_ok=True)
                asset_probe.write_report({"game":basic,"resource_index":deep},location)
                logic=deep["archives"].get("Logic.ds2res",{})
                objects=deep["archives"].get("Objects.ds2res",{})
                def done():
                    self.status.set(f"Resource inventory saved locally: {location}")
                    messagebox.showinfo("Dungeon Siege II reference scan",
                        f"Logic entries: {logic.get('total_files','unavailable')}\n"
                        f"Objects entries: {objects.get('total_files','unavailable')}\n"
                        f"Report: {location}\n\nNo game files were changed or uploaded.")
                self.after(0,done)
            except Exception as error:
                msg=str(error)
                self.after(0,lambda:messagebox.showerror("Resource scan failed",msg))
        threading.Thread(target=worker,daemon=True).start()

    def extract_logic_references(self):
        self._extract_references("logic")

    def extract_object_references(self):
        self._extract_references("objects")

    def _extract_references(self,kind):
        """Separate files for rig/template analysis without modifying game tanks."""
        game=self.game.get()
        if not manager.valid_game_folder(game):
            messagebox.showwarning("Game folder","Choose a valid Dungeon Siege II folder first.")
            return
        contains=None
        if kind=="objects":
            contains=simpledialog.askstring("Select reference models",
                "Extract .asp/.prs entries whose archive path contains (e.g. human, hero, fs0).\n"
                "Use Inspect local game archives to see example names first.")
            if not contains or not contains.strip():
                return
            contains=contains.strip()
        parent=filedialog.askdirectory(title="Choose where to save reference files")
        if not parent:
            return
        import uuid,threading
        target=Path(parent)/("DungeonSiegeCC_"+kind+"_references_"+uuid.uuid4().hex[:8])
        self.status.set("Extracting "+kind+" reference files locally...")
        def worker():
            try:
                result=ds2_tank.extract_game_references(game,target,kind,contains=contains)
                def finished():
                    if kind=="logic" and result["written"]:
                        self.vars["donor_root"].set(str(target))
                    msg=(f"Extracted {result['written']}/{result['matched']} reference files to:\n"
                         f"{target}\n\nRead errors: {len(result['errors'])}. "
                         "Details in dscc_extraction_report.json.\n"
                         "Original archives were not modified.")
                    self.status.set(msg.split("\n")[0])
                    messagebox.showinfo("Reference extraction",msg)
                self.after(0,finished)
            except Exception as error:
                msg=str(error)
                self.after(0,lambda:messagebox.showerror("Reference extraction failed",msg))
        threading.Thread(target=worker,daemon=True).start()

    def import_mmd_zip(self):
        filename=filedialog.askopenfilename(title="Select MMD character archive",
            filetypes=[("MMD ZIP archives","*.zip")])
        if not filename:return
        try:
            report=asset_probe.scan_mmd_zip(filename)
            models=report["models"]
            summary=f"Found {len(models)} PMX/PMD models, {report['motion_count']} motions, "
            summary+=f"{report['texture_count']} textures.\n\n"
            summary+="\n".join(m["path"] for m in models[:10])
            if not models or not any(m["recognized_signature"] for m in models):
                messagebox.showwarning("No usable model",summary+"\n\nNo recognized PMX/PMD signature.")
                return
            if not messagebox.askyesno("MMD character archive",summary+"\n\nExtract to a new folder?"):
                return
            parent=filedialog.askdirectory(title="Choose parent folder for extracted MMD character")
            if not parent:return
            destination=Path(parent)/(Path(filename).stem+"_MMD")
            result=asset_probe.extract_mmd_zip(filename,destination)
            if len(result["models"])==1:
                self.vars["model"].set(result["models"][0])
            messagebox.showinfo("MMD archive extracted",f"Saved {result['extracted_count']} files to:\n{destination}\n\n"
                +"One model selected automatically." if len(result["models"])==1 else
                f"Saved {result['extracted_count']} files to:\n{destination}\n\nChoose a model from the extracted folder.")
            self.status.set("Extracted MMD files locally; game installation unchanged.")
        except Exception as error:
            messagebox.showerror("MMD archive import failed",str(error))

    def inspect_model(self):
        path=self.vars["model"].get()
        if not Path(path).is_file():
            messagebox.showwarning("Missing model","Choose an MMD model first.")
            return
        try:
            if path.lower().endswith(".pmx"):
                result=mmd_assets.read_pmx(path)
                detail=f"PMX {result['version']} — {result['name']}\\nVertices: {len(result['vertices'])}\\nTriangles: {len(result['indices'])//3}\\nBones: {len(result['bones'])}\\nMaterials: {len(result['materials'])}"
            else:
                result=mmd_assets.inspect_pmd(path)
                detail=f"PMD — {result['name']}\\nVertices: {result['vertex_count']}\\nConvert to PMX to export neutral OBJ."
            messagebox.showinfo("Model inspection",detail.replace("\\\\n","\\n"))
        except Exception as exc:
            messagebox.showerror("Model inspection failed",str(exc))

    def inspect_motion(self):
        custom=[(k,self.motions[k].get()) for k in SLOTS if self.sources[k].get()=="custom" and self.motions[k].get()]
        if not custom:
            messagebox.showinfo("Motions","No VMD overrides configured; all animations are native.")
            return
        reports=[]
        for slot, path in custom:
            try:
                motion=mmd_assets.read_vmd(path)
                reports.append(f"{slot}: {motion['keyframe_count']} keys, {len(motion['tracks'])} bones, {round(max(0,motion['frame_count']-1)/30,2)}s")
            except Exception as exc:
                reports.append(f"{slot}: ERROR — {exc}")
        messagebox.showinfo("VMD motion inspection","\\n".join(reports).replace("\\\\n","\\n"))

    def inspect_logic_zip(self):
        """Analyze user-owned GAS templates inside a ZIP without unpacking them."""
        archive=filedialog.askopenfilename(title="Choose the extracted Logic references ZIP",
            filetypes=[("Extracted Logic archive","*.zip")])
        if not archive:
            return
        self.status.set("Reading recruitable template inheritance from Logic ZIP...")
        import threading
        def worker():
            try:
                report=logic_inspector.inspect_logic_source(archive)
                path=manager.settings_path().parent/"logic_template_report.json"
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
                def finish():
                    candidates=report["humanoid_candidates"]
                    diagnostics=report["diagnostics"]
                    summary=(f"GAS files: {report['gas_file_count']}\n"
                             f"Templates: {report['template_count']}\n"
                             f"base_pm-derived matches: {report['potential_recruitable_count']}\n"
                             f"All actor donor prospects: {report['donor_candidate_count']}\n"
                             f"Humanoid/known companion leads: {report['humanoid_candidate_count']}\n"
                             f"Non-humanoid/hostile matches excluded: {report['excluded_non_humanoid_count']}\n"
                             f"Unresolved parent links: {diagnostics['unresolved_specialization_count']}\n"
                             f"Report: {path}\n\n")
                    if not candidates:
                        example=diagnostics.get("template_examples_if_no_match",[])
                        summary+="No plausible humanoid donors identified automatically.\n"
                        if example:
                            summary+="Available template examples:\n"+"\n".join(
                                f"{x['template']} -> {x['specializes'] or '(root)'}"
                                for x in example[:15])
                        summary+="\n\nPlease share logic_template_report.json for manual review.\n"
                        summary+="Do not select a giant, beast, ghost, or monster as a normal humanoid rig donor."
                        self.status.set("Logic analysis completed; inspect report for template lineage.")
                        messagebox.showwarning("Logic reference analysis",summary)
                        return
                    summary+="Humanoid/vanilla companion REFERENCE leads (not validated rigs):\n"+"\n".join(
                        f"{x['template']} — {x['screen_name'] or '(unnamed)'} "
                        f"[{x['compatibility_category']}; {', '.join(x['compatibility_reasons'][:2])}]"
                        for x in candidates[:15])
                    summary+="\n\nNo donor is verified compatible with Dalvi yet.\n"
                    summary+="Enter a template ID for inspection, or Cancel to leave it unchanged."
                    chosen=simpledialog.askstring("Logic template candidates",summary,
                        initialvalue=candidates[0]["template"])
                    if not chosen:
                        self.status.set("Logic reference report saved; donor unchanged.")
                        return
                    try:
                        donor=logic_inspector.verify_donor_in_source(archive,chosen.strip())
                    except logic_inspector.LogicAnalysisError as exc:
                        messagebox.showerror("Invalid donor selection",str(exc))
                        return
                    if not any(x["template"].casefold()==donor["template"].casefold()
                               for x in candidates):
                        if not messagebox.askyesno(
                                "Unverified donor template",
                                "This template was not classified as a humanoid donor. "
                                "It may be a beast or monster with an incompatible skeleton. "
                                "Select it for reference inspection anyway?"):
                            return
                    self.vars["donor_template"].set(donor["template"])
                    self.vars["donor_root"].set(archive)
                    self.status.set(f"Selected donor {donor['template']} from Logic ZIP. No game files modified.")
                self.after(0,finish)
            except Exception as error:
                msg=str(error)
                self.after(0,lambda:messagebox.showerror("Logic ZIP analysis failed",msg))
        threading.Thread(target=worker,daemon=True).start()

    def browse_donor_root(self):
        folder=filedialog.askdirectory(title="Folder of untanked Dungeon Siege II Logic.ds2res GAS files")
        if folder:self.vars["donor_root"].set(folder)

    def browse_model(self):
        f=filedialog.askopenfilename(filetypes=[("MMD models","*.pmx *.pmd")])
        if f:self.vars["model"].set(f)
    def browse_vmd(self,key):
        f=filedialog.askopenfilename(filetypes=[("MMD motion","*.vmd")])
        if f:self.sources[key].set("custom");self.motions[key].set(f)
    def reset_motion(self,key):self.sources[key].set("native");self.motions[key].set("")
    def capture(self):
        p=new_project()
        p.update({k:v.get() for k,v in self.vars.items()})
        p["animations"]={k:{"source":self.sources[k].get(),"file":self.motions[k].get() if self.sources[k].get()=="custom" else ""} for k in SLOTS}
        return p
    def load_project(self,p):
        for k,v in self.vars.items():v.set(p.get(k,""))
        for k in SLOTS:
            a=p.get("animations",{}).get(k,{})
            self.sources[k].set(a.get("source","native"));self.motions[k].set(a.get("file",""))
    def reset(self):self.project_file=None;self.load_project(new_project())
    def open_project(self):
        f=filedialog.askopenfilename(filetypes=[("Companion project","*.json")])
        if f:
            try:self.load_project(json.loads(Path(f).read_text(encoding="utf-8")));self.project_file=f
            except Exception as e:messagebox.showerror("Open failed",str(e))
    def save_project(self):
        f=self.project_file or filedialog.asksaveasfilename(defaultextension=".json")
        if f:
            try:Path(f).write_text(json.dumps(self.capture(),indent=2,ensure_ascii=False),encoding="utf-8");self.project_file=f
            except Exception as e:messagebox.showerror("Save failed",str(e))
    def check(self):
        errors=validate(self.capture())
        if errors:messagebox.showerror("Validation","\n".join(errors))
        else:
            if self.vars["donor_template"].get() or self.vars["donor_root"].get():
                try:game_pipeline.verify_donor(self.vars["donor_root"].get(),self.vars["donor_template"].get())
                except Exception as e:messagebox.showerror("Donor validation",str(e));return
            messagebox.showinfo("Validation","Source paths valid. Actual DS2 animation retargeting and NPC map integration still require game assets.")
    def export(self):
        folder=filedialog.askdirectory(title="Export source package")
        if folder:
            try:out=export_sources(self.capture(),folder);self.status.set("Exported source package: "+str(out))
            except Exception as e:messagebox.showerror("Export failed",str(e))
    def startup_checks(self):
        """Run the online and local checks automatically on EVERY launch."""
        self.status.set("Startup: checking GitHub releases and local framework files...")
        self._startup_framework_running = True
        # Start the network request immediately in a daemon thread. The game
        # folder/framework wizard runs on the UI thread; update prompts queue
        # until it has finished, avoiding overlapping modal windows.
        self.check_update(startup=True)
        self.after(10, self.startup_framework_check)

    def startup_framework_check(self):
        try:
            self.first_launch()
        finally:
            self._startup_framework_running = False
            if self._pending_startup_update is not None:
                success, outcome = self._pending_startup_update
                self._pending_startup_update = None
                self.finish_update_check(success, outcome, startup=True)

    def finish_update_check(self, success, outcome, startup=False):
        self._checking_updates = False
        if startup and self._startup_framework_running:
            self._pending_startup_update = (success, outcome)
            return
        if success:
            self.update_offer(outcome)
        else:
            self.status.set("Update check unavailable (framework check still ran): " + str(outcome))

    def first_launch(self):
        if not manager.valid_game_folder(self.game.get()):
            messagebox.showinfo("Game setup","Select your Dungeon Siege II installation folder.")
            self.choose_game()
        else:self.framework()
    def choose_game(self):
        folder=filedialog.askdirectory(title="Select folder containing DungeonSiege2.exe")
        if not folder:return
        if not manager.valid_game_folder(folder):messagebox.showerror("Invalid folder","DungeonSiege2.exe not found.");return
        self.game.set(folder);self.settings["game_path"]=folder;manager.save_settings(self.settings);self.framework()
    def framework(self):
        path=self.game.get()
        if not manager.valid_game_folder(path):messagebox.showwarning("Game folder","Select game folder first.");return
        try:
            status=manager.framework_status(path)
            if status=="installed":self.status.set("Bundled framework scaffold installed and verified.");return
            if messagebox.askyesno("Framework installation","Framework status: "+status+". Install or repair bundled scaffold?\n\nThis is NOT yet a gameplay runtime."):
                manager.install_framework(path)
                self.status.set("Framework scaffold installed.")
        except Exception as e:messagebox.showerror("Framework installation failed",str(e))
    def check_update(self, startup=False):
        """Check GitHub automatically at launch and on manual request."""
        if self._checking_updates:
            return
        self._checking_updates = True
        self.status.set("Checking GitHub for updates...")
        import threading
        def check():
            try:
                release = manager.latest_release()
                self.after(0, lambda: self.finish_update_check(True, release, startup=startup))
            except Exception as exc:
                error = str(exc)
                self.after(0, lambda: self.finish_update_check(False, error, startup=startup))
        threading.Thread(target=check,daemon=True).start()
    def update_offer(self,release):
        if not release["newer"]:
            self.status.set("Importer is up to date ("+manager.VERSION+").")
            return
        if not release["download_url"]:
            if messagebox.askyesno("New version","Version "+release["version"]+" is available, but no Windows update archive was published. Open GitHub?"):
                import webbrowser
                webbrowser.open(release["page"])
            return
        if messagebox.askyesno("Update available","DungeonSiegeCC "+release["version"]+" is available. Download and install the updated tool?\n\nGame files and character projects will not be deleted."):
            self.status.set("Downloading tool update...")
            import threading
            threading.Thread(target=self.download_update,args=(release,),daemon=True).start()

    def download_update(self,release):
        import tempfile
        from pathlib import Path
        try:
            root=Path(tempfile.mkdtemp(prefix="dscc_stage_"))
            archive=root/"update.zip"
            manager.download_release(release["download_url"],archive)
            staged=manager.extract_update(archive,root/"staged")
            self.after(0,lambda:self.install_update(staged))
        except Exception as exc:
            self.after(0,lambda msg=str(exc):messagebox.showerror("Update failed",msg))

    def install_update(self,staged):
        import os,subprocess,sys
        from pathlib import Path
        if getattr(sys,"frozen",False):
            messagebox.showwarning("EXE update unsupported","The source updater cannot replace a packaged EXE. Download the new installer from GitHub.")
            return
        if not messagebox.askyesno("Apply update","Close the importer and apply the downloaded update?\n\nSave your current companion project first."):
            return
        helper=Path(staged)/"update_helper.py"
        if not helper.is_file():
            messagebox.showerror("Update failed","Update helper missing")
            return
        try:
            subprocess.Popen([sys.executable,str(helper),str(staged),str(Path(__file__).resolve().parent),str(os.getpid())],
                             creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            self.destroy()
        except OSError as exc:
            messagebox.showerror("Update failed",str(exc))

if __name__=="__main__":App().mainloop()
