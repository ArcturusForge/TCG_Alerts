"""Install declarative providers and enable trusted external Python providers at runtime."""
import json,os,subprocess,sys,threading,shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox,simpledialog
from .plugins import validate_manifest


class PluginManager(tk.Toplevel):
    def __init__(self,app):
        super().__init__(app);self.app=app;self.title('Game and store providers');self.geometry('980x600');self.configure(bg='#0d1321')
        ttk.Label(self,text='Add games without rebuilding the app',style='Heading.TLabel',padding=16).pack(anchor='w')
        ttk.Label(self,text='JSON providers map public card APIs. Python plugins can add card catalogues and store readers.\nPython plugins run with your account permissions: enable code only from authors you trust. New plugins start disabled.',style='Muted.TLabel',padding=(16,0),wraplength=920).pack(anchor='w')
        self.table=app.make_table(self,[('name','Provider',210),('games','Games',180),('kind','Type',140),('state','Status',350)])
        tools=ttk.Frame(self,padding=16);tools.pack(fill='x')
        for label,command in [('Install JSON provider…',self.install),('Install from GitHub…',self.install_github),('Open plugin folder',self.open_folder),('Enable / disable',self.toggle),('Reload providers',self.reload)]:ttk.Button(tools,text=label,command=command).pack(side='left',padx=(0,8))
        ttk.Label(self,text=str(app.plugins.directory),style='Muted.TLabel',padding=16).pack(anchor='w')
        self.refresh()
    def refresh(self):
        self.table.delete(*self.table.get_children());self.rows={}
        self.table.insert('','end',iid='builtin',values=('OpenRift','Riftbound','Built-in catalogue','Ready · no account required'))
        for i,row in enumerate(self.app.plugins.entries):
            key=str(i);self.rows[key]=row
            self.table.insert('','end',iid=key,values=(row.get('name',Path(row['path']).parent.name),', '.join(row.get('games',[])),row.get('kind','Invalid'),row['error'] or ('Enabled' if row['enabled'] else 'Disabled')))
    def reload(self):self.app.plugins.reload();self.refresh();self.app.refresh()
    def toggle(self):
        ids=self.table.selection()
        if not ids or ids[0] not in self.rows:return
        row=self.rows[ids[0]]
        if not row.get('id'):return
        self.app.plugins.enable(row['id'],not row['enabled']);self.refresh();self.app.refresh()
    def install_github(self):
        repository=simpledialog.askstring('GitHub plugin','GitHub owner/repository:',initialvalue='ArcturusForge/TCG_Alerts',parent=self)
        if not repository:return
        asset_name=simpledialog.askstring('Plugin release asset','ZIP asset name (for example TCGAlerts-plugin-netdeck-cyberpunk.zip):',initialvalue='TCGAlerts-plugin-netdeck-cyberpunk.zip',parent=self)
        if not asset_name:return
        self.app.update_status.set('Downloading and checking plugin release…')
        def worker():
            try:
                from .updates import Releases,repo_name,select_asset,install_version
                repo_name(repository);client=Releases();release=client.latest(repository)
                def validate(folder):
                    paths=list(folder.rglob('plugin.json'))
                    if len(paths)!=1:raise ValueError('Plugin ZIP must contain exactly one manifest.')
                    manifest=validate_manifest(json.loads(paths[0].read_text()))
                    if manifest.get('update')!=dict(repository=repository,asset=asset_name):raise ValueError('Manifest update source must match the selected repository and asset.')
                safe_name=__import__('hashlib').sha256((repository+asset_name).encode()).hexdigest()[:20]
                folder=install_version(client,repository,release,select_asset(release,asset_name),self.app.updates.root/('install-'+safe_name),validate)
                manifest_path=next(folder.rglob('plugin.json'));manifest=validate_manifest(json.loads(manifest_path.read_text()))
                target=self.app.plugins.directory/manifest['id']
                if target.exists():raise ValueError('Provider is already installed; use its automatic updater instead.')
                stage=target.with_name(target.name+'.updating')
                if stage.exists():shutil.rmtree(stage)
                shutil.copytree(manifest_path.parent,stage);stage.rename(target)
                self.app.monitor.events.put(('plugin_installed',manifest['name']+' installed. Enable it in Game / store plugins.'))
            except Exception as e:self.app.monitor.events.put(('update_status','Plugin installation: '+str(e)))
        threading.Thread(target=worker,daemon=True).start()

    def open_folder(self):
        directory=str(self.app.plugins.directory)
        if sys.platform=='win32':os.startfile(directory)
        else:
            try:subprocess.Popen(['xdg-open',directory])
            except OSError:self.app.status.set('Plugin folder: '+directory)
    def install(self):
        file=filedialog.askopenfilename(parent=self,filetypes=[('Provider manifest','*.json')])
        if not file:return
        try:
            path=Path(file)
            if path.stat().st_size>64000:raise ValueError('Manifest exceeds 64 KB.')
            manifest=validate_manifest(json.loads(path.read_text(encoding='utf-8')))
            if manifest['kind']!='catalogue-json':raise ValueError('For Python providers, copy the full plugin folder here, then Reload and enable it.')
            directory=self.app.plugins.directory/manifest['id'];directory.mkdir(exist_ok=True)
            target=directory/'plugin.json'
            if target.exists() and not messagebox.askyesno('Replace provider','Replace this installed provider manifest?',parent=self):return
            target.write_text(json.dumps(manifest,indent=2),encoding='utf-8');self.reload()
        except (OSError,ValueError) as e:messagebox.showerror('Could not install provider',str(e),parent=self)
