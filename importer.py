"""DungeonSiegeCC desktop companion project editor (Python 3.10+)."""
import json, re, shutil, struct, tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
import manager
import mmd_assets
import game_pipeline

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
        toolbar=ttk.Frame(root);toolbar.pack(fill="x",pady=8)
        for label,fun in [("New",self.reset),("Open",self.open_project),("Save",self.save_project),("Validate",self.check),("Export source package",self.export)]:
            ttk.Button(toolbar,text=label,command=fun).pack(side="left",padx=3)
        inspectbar=ttk.Frame(root);inspectbar.pack(fill="x")
        ttk.Button(inspectbar,text="Inspect MMD model",command=self.inspect_model).pack(side="left",padx=3)
        ttk.Button(inspectbar,text="Inspect VMD overrides",command=self.inspect_motion).pack(side="left",padx=3)
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
