"""User-facing directory, destination comparison, calendar, and exact variant controls."""
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
from datetime import date
import sqlite3,threading,webbrowser
from .catalog import GAMES,COUNTRIES,AU_STATES
from .core import money
from .commerce import quote,postcode
from .releases import label,upcoming,icalendar

class Form(tk.Toplevel):
    def __init__(self,parent,title,fields,save):
        super().__init__(parent);self.title(title);self.configure(bg='#0d1321');self.transient(parent);self.grab_set();self.action=save;self.vars={}
        frame=ttk.Frame(self,padding=18);frame.pack(fill='both',expand=True)
        for i,(key,text,value,choices) in enumerate(fields):
            cell=ttk.Frame(frame,padding=(0,0,12,10));cell.grid(row=i//2,column=i%2,sticky='ew')
            ttk.Label(cell,text=text).pack(anchor='w');v=tk.StringVar(value='' if value is None else str(value));self.vars[key]=v
            widget=ttk.Combobox(cell,textvariable=v,values=choices,width=39) if choices else ttk.Entry(cell,textvariable=v,width=42)
            widget.pack(fill='x')
        ttk.Button(frame,text='Save',command=self.save,style='Accent.TButton').grid(row=(len(fields)+1)//2,column=1,sticky='e')
    def save(self):
        try:self.action({k:v.get().strip() for k,v in self.vars.items()})
        except (ValueError,sqlite3.Error) as e:messagebox.showerror('Could not save',str(e),parent=self);return
        self.destroy()


def delivery_editor(app,w):
    fields=[('pack_count','Packs in ONE listed unit (blank = unknown)',w['pack_count'],None),('shipping','Fixed shipping quote (0 = free; blank = unknown)',f"{w['shipping']/100:.2f}" if w['shipping'] is not None else '',None),('shipping_country','Fixed quote destination country',w['shipping_country'],COUNTRIES),('shipping_postcode','Exact quote postcode (blank = unscoped)',w['shipping_postcode'],None),('pickup','This listing eligible for pickup?',w['pickup'],('Unspecified','Yes','No'))]
    def save(v):
        v['pack_count']=int(v['pack_count']) if v['pack_count'] else None;v['shipping']=money(v['shipping']) if v['shipping'] else None
        app.db.update(w['id'],**v);app.refresh()
    return Form(app,'Delivery & units — estimates for this listing',fields,save)


class VariantPicker(tk.Toplevel):
    def __init__(self,app,url,chosen,owner=None):
        super().__init__(app);self.app=app;self.chosen=chosen;self.owner=owner;self.transient(owner or app);self.grab_set();self.protocol('WM_DELETE_WINDOW',self.close);self.title('Select an exact Shopify variant');self.geometry('1000x500');self.configure(bg='#0d1321')
        self.url=tk.StringVar(value=url);top=ttk.Frame(self,padding=16);top.pack(fill='x')
        ttk.Entry(top,textvariable=self.url,width=78).pack(side='left',fill='x',expand=True)
        self.button=ttk.Button(top,text='Load options',command=self.load);self.button.pack(side='right',padx=8)
        self.table=app.make_table(self,[('title','Variant',500),('price','Item price',120),('stock','Availability',120),('id','Variant ID',160)])
        self.note=tk.StringVar(value='No option is selected automatically. Choosing an option updates its exact variant URL; saving triggers a fresh check.')
        ttk.Label(self,textvariable=self.note,style='Muted.TLabel',padding=12,wraplength=950).pack(anchor='w')
        ttk.Button(self,text='Use selected variant',command=self.select).pack(anchor='e',padx=16,pady=12);self.options={}
    def load(self):
        requested=self.url.get().strip();self.button.configure(state='disabled');self.note.set('Loading public product data and currency…')
        def worker():
            from .sources import variant_options,Client
            try:options,error=variant_options(requested,Client()),None
            except Exception as e:options,error=[],str(e)
            self.app.monitor.events.put(('variant_options',(self,requested,options,error)))
        threading.Thread(target=worker,daemon=True).start()
    def receive(self,requested,options,error):
        self.button.configure(state='normal')
        if self.url.get().strip()!=requested:self.note.set('URL changed. Load again.');return
        if error:self.note.set('Could not load variants: '+error);return
        self.table.delete(*self.table.get_children());self.options={str(o['id']):o for o in options}
        for key,o in self.options.items():self.table.insert('','end',iid=key,values=(o['title'],f"{o['currency']} {o['price']/100:.2f}",o['stock'],key))
        self.note.set('Select the exact pack, box or case. Pack count must be verified separately under Delivery & units.')
    def select(self):
        if ids:=self.table.selection():self.chosen(self.options[ids[0]]);self.close()
    def close(self):
        self.destroy()
        if self.owner and self.owner.winfo_exists():self.owner.grab_set()


class Directory(ttk.Frame):
    def __init__(self,app,parent):
        super().__init__(parent,padding=16);self.app=app
        ttk.Label(self,text='Sourced Australian store directory',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(self,text='Location evidence and product adapter support are separate. Country/state filters apply; games stocked are not inferred.\nInitial sources checked 1 Nov 2026. This is a starting directory, not merchant certification or a branch stock feed.',style='Muted.TLabel').pack(anchor='w',pady=10)
        self.table=app.make_table(self,[('name','Store',200),('location','Country / state',180),('date','Source checked',110),('support','Adapter support notes',540)])
        self.detail=tk.StringVar();ttk.Label(self,textvariable=self.detail,style='Muted.TLabel',wraplength=1100).pack(anchor='w',pady=10)
        self.table.bind('<<TreeviewSelect>>',lambda e:self.details())
        buttons=ttk.Frame(self);buttons.pack(fill='x')
        for title,action in [('Open store',lambda:self.open('url')),('Location source',lambda:self.open('source_url')),('Find products',self.discover),('Add store',lambda:self.edit(False)),('Edit',lambda:self.edit(True)),('Shipping rules',self.rules),('Apply location to watches',self.apply)]:ttk.Button(buttons,text=title,command=action).pack(side='left',padx=(0,4))
    def selected(self):
        ids=self.table.selection();return self.rows.get(ids[0]) if ids else None
    def refresh(self):
        selected=self.table.selection();self.table.delete(*self.table.get_children());self.rows={}
        for s in self.app.db.stores():
            if self.app.country_filter.get() not in ('All countries',s['country']) or self.app.state_filter.get() not in ('All states',s['state']):continue
            key=str(s['id']);self.rows[key]=s;self.table.insert('','end',iid=key,values=(s['name'],s['country']+' / '+s['state'],s['checked'],s['support']))
        for key in selected:
            if self.table.exists(key):self.table.selection_set(key)
        self.details()
    def details(self):
        s=self.selected();self.detail.set(s['address']+'\n'+s['source_url']+' • Pickup policy: '+s['pickup'] if s else 'Select a store. Apply location explicitly replaces location tags on linked watches.')
    def open(self,key):
        if s:=self.selected():webbrowser.open(s[key])
    def discover(self):
        if s:=self.selected():self.app.discovery_url.set(s['catalog_url']);self.app.tabs.select(self.app.discovery_page)
    def apply(self):
        if s:=self.selected():self.app.db.apply_store(s['id']);self.app.refresh()
    def edit(self,existing):
        s=self.selected() if existing else {}
        if existing and not s:return
        fields=[]
        for key,title,default,choices in [('name','Name','',None),('url','Store HTTPS URL','',None),('country','Country','Australia',COUNTRIES),('state','State','Victoria',AU_STATES),('address','Address / branch description','',None),('source_url','Location evidence URL','',None),('checked','Source checked YYYY-MM-DD',date.today().isoformat(),None),('catalog_url','Catalog URL','',None),('support','Adapter support note','Product support untested',None),('pickup','Pickup policy confirmed?','Unspecified',('Unspecified','Yes','No'))]:fields.append((key,title,s.get(key,default),choices))
        def save(v):self.app.db.save_store(v,s.get('id'));self.app.refresh()
        Form(self.app,'Store directory entry',fields,save)
    def rules(self):
        if s:=self.selected():Rules(self.app,s)


class Rules(tk.Toplevel):
    def __init__(self,app,store):
        super().__init__(app);self.app=app;self.store=store;self.title('Shipping rules — '+store['name']);self.geometry('1000x480');self.configure(bg='#0d1321')
        ttk.Label(self,text='One listed unit. Enter a checked policy/quote, not an assumed promotional rate.\nExact postcode beats whole-country rules. Below a free threshold, a blank rate stays unknown.',style='Muted.TLabel',padding=14).pack(anchor='w')
        self.table=app.make_table(self,[('scope','Destination',180),('currency','Currency',80),('flat','Flat',100),('free','Free at/above',110),('date','Entered',100),('source','Source',400)])
        b=ttk.Frame(self,padding=14);b.pack(fill='x');ttk.Button(b,text='Add / replace rule',command=self.add).pack(side='left');ttk.Button(b,text='Remove selected',command=self.remove).pack(side='left',padx=8);ttk.Button(b,text='Open source',command=self.source).pack(side='left');self.refresh()
    def refresh(self):
        self.table.delete(*self.table.get_children());self.rows={str(r['id']):r for r in self.app.db.rules(self.store['id'])}
        for key,r in self.rows.items():self.table.insert('','end',iid=key,values=(r['country']+' / '+(r['postcode'] or 'all postcodes'),r['currency'],self.app.cash(r['flat']),self.app.cash(r['free_over']),r['checked'],r['source_url']))
    def add(self):
        fields=[('country','Destination country','Australia',COUNTRIES),('postcode','Exact postcode (blank = all)','',None),('currency','Currency','AUD',None),('flat','Flat shipping (blank = unknown)','',None),('free_over','Free at/above amount (optional)','',None),('source_url','Checked policy / quote URL',self.store['url'],None)]
        def save(v):
            for k in ('flat','free_over'):v[k]=money(v[k]) if v[k] else None
            self.app.db.save_rule(self.store['id'],v);self.refresh();self.app.refresh()
        Form(self,'Shipping estimate rule',fields,save)
    def remove(self):
        if ids:=self.table.selection():self.app.db.delete_rule(int(ids[0]));self.refresh();self.app.refresh()
    def source(self):
        if ids:=self.table.selection():webbrowser.open(self.rows[ids[0]]['source_url'])


class Compare(ttk.Frame):
    def __init__(self,app,parent):
        super().__init__(parent,padding=16);self.app=app
        ttk.Label(self,text='Delivered cost & price per pack',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(self,text='One listed unit per row. Match set, edition, language and contents manually. Unknown shipping remains unknown.\nPickup is a policy estimate; confirm item eligibility/readiness. These destination settings do not change alert targets.',style='Muted.TLabel').pack(anchor='w',pady=10)
        controls=ttk.Frame(self);controls.pack(fill='x',pady=8)
        self.country=tk.StringVar(value=app.db.setting('destination_country','Australia'));self.destination=tk.StringVar(value=app.db.setting('destination_postcode',''));self.mode=tk.StringVar(value='Delivery')
        for title,var,values,width in [('Country',self.country,COUNTRIES,20),('Postcode',self.destination,None,10),('Mode',self.mode,('Delivery','Pickup'),12)]:
            ttk.Label(controls,text=title).pack(side='left',padx=5)
            widget=ttk.Combobox(controls,textvariable=var,values=values,state='readonly',width=width) if values else ttk.Entry(controls,textvariable=var,width=width);widget.pack(side='left')
        ttk.Button(controls,text='Apply destination',command=self.apply).pack(side='left',padx=10)
        ttk.Button(controls,text='Edit delivery & units',command=self.edit).pack(side='right')
        self.table=app.make_table(self,[('group','Match group / currency',240),('store','Store',180),('item','Item',90),('shipping','Shipping',90),('total','Total estimate',110),('packs','Packs',70),('unit','Total / pack',100)])
        self.detail=tk.StringVar(value='Set a known pack count and shipping quote under Delivery & units. Add store rules in Stores.');ttk.Label(self,textvariable=self.detail,style='Muted.TLabel',wraplength=1120).pack(anchor='w',pady=10)
        self.table.bind('<<TreeviewSelect>>',lambda e:self.select());ttk.Button(self,text='Open quote evidence',command=self.evidence).pack(anchor='e')
    def apply(self):
        try:self.destination.set(postcode(self.destination.get(),self.country.get()))
        except ValueError as e:messagebox.showerror('Destination',str(e),parent=self);return
        self.app.db.set_setting('destination_country',self.country.get());self.app.db.set_setting('destination_postcode',self.destination.get());self.refresh()
    def refresh(self):
        selected=self.table.selection();self.table.delete(*self.table.get_children());self.rows={};stores={s['id']:s for s in self.app.db.stores()};records=[]
        for w in self.app.scope():
            if not w['group_name'] or not self.app.healthy(w) or w['stock']!='in_stock':continue
            try:q=quote(w,self.app.db.rules(w['store_id']) if w['store_id'] else [],self.country.get(),self.destination.get(),self.mode.get(),stores.get(w['store_id']))
            except ValueError:self.detail.set('Apply a valid destination postcode.');return
            records.append((w,q))
        records.sort(key=lambda p:(p[0]['group_name'],p[0]['currency'],p[1]['total'] is None,p[1]['total'] or 0))
        for w,q in records:
            key=str(w['id']);self.rows[key]=(w,q);self.table.insert('','end',iid=key,values=(w['group_name']+' / '+w['currency'],stores.get(w['store_id'],{}).get('name') or w['url'].split('/')[2],self.app.cash(w['price']),self.app.cash(q['shipping']),self.app.cash(q['total']),w['pack_count'] or 'Unknown',f"{q['per_pack']/100:.2f}" if q['per_pack'] is not None else 'Unknown'))
        for key in selected:
            if self.table.exists(key):self.table.selection_set(key)
    def select(self):
        if ids:=self.table.selection():
            q=self.rows[ids[0]][1];self.detail.set(q['basis']+'\n'+(q['source'] or 'No shipping evidence for this destination.')+' • Excludes extra fees and basket-only discounts; pack count is user supplied.')
    def edit(self):
        if ids:=self.table.selection():delivery_editor(self.app,self.rows[ids[0]][0])
    def evidence(self):
        if ids:=self.table.selection():
            if source:=self.rows[ids[0]][1]['source']:webbrowser.open(source)


class Calendar(ttk.Frame):
    def __init__(self,app,parent):
        super().__init__(parent,padding=16);self.app=app
        ttk.Label(self,text='Release & prerelease calendar',style='Heading.TLabel').pack(anchor='w')
        ttk.Label(self,text='Curated source snapshots plus your entries. Publication dates never become release dates.\nGlobal scope does not confirm Australian stock. Seasonal windows retain publisher wording; sources are not auto-reverified.',style='Muted.TLabel').pack(anchor='w',pady=10)
        controls=ttk.Frame(self);controls.pack(fill='x',pady=8);self.view=tk.StringVar(value='Upcoming / undated');self.region=tk.StringVar(value='All scopes')
        for var,values in [(self.view,('Upcoming / undated','All entries')),(self.region,('All scopes','Australia','Victoria','Global / unspecified'))]:
            box=ttk.Combobox(controls,textvariable=var,values=values,width=24);box.pack(side='left',padx=(0,10));box.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        ttk.Button(controls,text='Apply scope',command=self.refresh).pack(side='left');ttk.Button(controls,text='Export visible dates (.ics)',command=self.export).pack(side='right')
        self.table=app.make_table(self,[('date','Date / announced window',300),('game','Game',100),('title','Release / event',300),('region','Scope',150),('status','Status / precision',160),('checked','Checked',100)])
        self.detail=tk.StringVar();ttk.Label(self,textvariable=self.detail,style='Muted.TLabel',wraplength=1120).pack(anchor='w',pady=10);self.table.bind('<<TreeviewSelect>>',lambda e:self.select())
        buttons=ttk.Frame(self);buttons.pack(fill='x')
        for title,action in [('Add entry',lambda:self.edit(False)),('Edit selected',lambda:self.edit(True)),('Open original source',self.source)]:ttk.Button(buttons,text=title,command=action).pack(side='left',padx=(0,8))
    def refresh(self):
        selected=self.table.selection();self.table.delete(*self.table.get_children());self.rows={}
        for r in self.app.db.releases():
            if self.app.game_filter.get() not in ('All games',r['game']):continue
            if self.view.get()=='Upcoming / undated' and not upcoming(r):continue
            if self.region.get() not in ('All scopes',r['region']):continue
            key=str(r['id']);self.rows[key]=r;self.table.insert('','end',iid=key,values=(label(r),r['game'],r['title'],r['region'],r['status']+' / '+r['precision'],r['checked']))
        for key in selected:
            if self.table.exists(key):self.table.selection_set(key)
        self.detail.set('Game filter applies. Calendar region is independent of store location. Add/edit entries for local events and promotional details.')
    def select(self):
        if ids:=self.table.selection():
            r=self.rows[ids[0]];self.detail.set(r['notes']+'\n'+r['source_url']+' • Source checked '+r['checked'])
    def source(self):
        if ids:=self.table.selection():webbrowser.open(self.rows[ids[0]]['source_url'])
    def edit(self,existing):
        ids=self.table.selection()
        if existing and not ids:return
        r=self.rows[ids[0]] if existing else {};fields=[]
        for key,title,default,choices in [('title','Title','',None),('game','Game','Riftbound',GAMES),('kind','Type','Release',('Release','Prerelease','Event','Promo')),('precision','Date precision','Day',('Day','Range','Window','TBA')),('start','Start YYYY-MM-DD (exact dates only)','',None),('end','End YYYY-MM-DD (range only)','',None),('window','Publisher window wording (Window only)','',None),('region','Regional scope','Global / unspecified',('Global / unspecified','Australia','Victoria')),('status','Status','Confirmed',('Confirmed','Tentative','Rumour','Cancelled')),('source_url','Source HTTPS URL','',None),('checked','Source checked YYYY-MM-DD',date.today().isoformat(),None),('notes','Notes / local event / promo details','',None)]:fields.append((key,title,r.get(key,default),choices))
        def save(v):self.app.db.save_release(v,r.get('id'));self.refresh()
        Form(self.app,'Release / event calendar entry',fields,save)
    def export(self):
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.ics',initialfile='tcg_releases.ics')
        if path:
            try:
                text,count,skipped=icalendar(self.rows.values())
                with open(path,'w',encoding='utf-8',newline='') as f:f.write(text)
                self.app.status.set(f'Exported {count} all-day events; skipped {skipped} undated/window/cancelled entries.')
            except OSError as e:messagebox.showerror('Export failed',str(e),parent=self)
