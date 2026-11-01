"""Explicit identity choice with artwork, async lookup, and a persistent local result cache."""
import hashlib,json,threading,time
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox
from .visuals import VisualGrid


class CatalogueSearch(tk.Toplevel):
    def __init__(self,page,match=False):
        super().__init__(page.app);self.page=page;self.match=page.selected() if match else None
        self.title('Choose card artwork' if match else 'Find a '+page.current['game']+' card');self.geometry('1000x720');self.configure(bg='#0d1321')
        self.deck_id=page.current['id'];self.game=page.current['game'];self.rows={};self.token=0;self.busy=False
        tools=ttk.Frame(self,padding=14);tools.pack(fill='x')
        self.query=tk.StringVar(value=self.match['name'] if self.match else '')
        ttk.Label(tools,text='Card name').pack(side='left',padx=(0,8));entry=ttk.Entry(tools,textvariable=self.query,width=35);entry.pack(side='left',fill='x',expand=True)
        self.button=ttk.Button(tools,text='Search catalogue',command=self.lookup);self.button.pack(side='left',padx=8)
        entry.bind('<Return>',lambda e:self.lookup());entry.focus_set()
        providers=page.app.plugins.providers(page.current['game']);self.providers={p['name']:p['id'] for p in providers}
        self.provider=tk.StringVar(value=next(iter(self.providers),''))
        provider_row=ttk.Frame(self,padding=(14,0));provider_row.pack(fill='x')
        ttk.Label(provider_row,text='Catalogue provider').pack(side='left',padx=(0,10))
        ttk.Combobox(provider_row,textvariable=self.provider,values=list(self.providers),state='readonly',width=45).pack(side='left')
        self.status=tk.StringVar(value='Choose an exact card/set/artwork. Catalogue results never supply store prices or confirm listing identity.')
        ttk.Label(self,textvariable=self.status,style='Muted.TLabel',wraplength=950,padding=14).pack(fill='x')
        self.grid=VisualGrid(self,page.app,lambda key:None,self.choose);self.grid.pack(fill='both',expand=True,padx=14)
        self.grid.message='Search to see card artwork and available printings.'
        ttk.Button(self,text='Use selected artwork' if match else 'Add selected card…',command=lambda:self.choose(self.grid.selected)).pack(anchor='e',padx=14,pady=14)
        self.protocol('WM_DELETE_WINDOW',self.close)

    def close(self):self.token+=1;self.destroy()

    def lookup(self):
        if self.busy:return
        query=self.query.get().strip()
        provider_id=self.providers.get(self.provider.get());game=self.game
        if not provider_id:self.status.set('Choose an enabled catalogue provider.');return
        if len(query)<2:self.status.set('Enter at least two characters.');return
        self.busy=True;self.button.configure(state='disabled');self.token+=1;token=self.token
        self.status.set('Searching catalogue… Existing results remain available.')
        cache=self.page.app.db.path.parent/'catalogue_cache';cache.mkdir(exist_ok=True)
        ttl,provider_version=self.page.app.plugins.cache_policy(provider_id)
        path=cache/(hashlib.sha256((provider_id+':'+provider_version+':'+game+':'+query.casefold()).encode()).hexdigest()+'.json')
        def work():
            cached=None
            try:
                if path.exists():cached=json.loads(path.read_text())
                if cached is not None and time.time()-path.stat().st_mtime<ttl:return cached,'Saved search · within provider refresh window'
                rows=self.page.app.plugins.search(provider_id,game,query);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(rows));tmp.replace(path)
                # Keep a bounded number of search results; images have a separate bounded cache.
                for old in sorted(cache.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[100:]:old.unlink(missing_ok=True)
                return rows,'Updated from '+provider_id
            except Exception as e:
                if cached is not None:return cached,'Offline search results · refresh failed: '+str(e)[:180]
                return [],'Catalogue unavailable: '+str(e)[:220]+'. Local files and image URLs still work.'
        def worker():
            result=work();self.page.app.monitor.events.put(('catalogue_result',(self,token,*result)))
        threading.Thread(target=worker,daemon=True).start()

    def receive(self,token,rows,status):
        if not self.winfo_exists() or token!=self.token:return
        self.busy=False;self.button.configure(state='normal');self.rows={str(r['id']):r for r in rows};self.grid.set_items(rows)
        self.grid.message='No matching cards. Try a shorter card name.';self.status.set(f'{len(rows)} results · '+status)

    def choose(self,key):
        row=self.rows.get(str(key))
        if not row:return
        if not self.page.current or self.page.current['id']!=self.deck_id:
            self.status.set('The selected deck changed. Close this search and reopen it from the intended deck.');return
        if self.match:
            if not messagebox.askyesno('Confirm artwork',f"Use {row['name']} ({row['set_code']} #{row['collector']}) artwork for {self.match['name']}? This changes artwork only; verify the exact printing yourself.",parent=self):return
            fields={**self.match,'image_url':row['image_url']}
            try:self.page.store.save_entry(self.deck_id,fields,self.match['id'])
            except Exception as e:
                self.status.set('Could not apply artwork: '+str(e));return
            self.page.store.local_image(self.match['id'],'')
            self.page.refresh();self.page.table.selection_set(str(self.match['id']));self.page.select()
        else:
            from .decks_ui import CardEditor
            CardEditor(self.page,preset={**row,'section':'Main','quantity':1,'owned':0})
        self.close()
