"""Deck-list editor, price breakdowns, imports and optional private artwork."""
import csv
import json
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
from datetime import date
import sqlite3,threading
from pathlib import Path
from .decks import DeckStore,CURRENCIES,parse_list
from .catalog import GAMES
from .core import money
from .additions import Form
from .visuals import VisualGrid

SECTIONS=('Main','Sideboard','Legend','Champion','Runes','Battlefields','Other')


class CardEditor(tk.Toplevel):
    def __init__(self,page,existing=None,preset=None):
        super().__init__(page.app);self.page=page;self.existing=existing;self.title('Edit deck card' if existing else 'Add deck card');self.configure(bg='#0d1321');self.transient(page.app);self.grab_set()
        self.vars={};frame=ttk.Frame(self,padding=16);frame.pack(fill='both',expand=True)
        fields=[('name','Card name','',None),('section','Deck section','Main',SECTIONS),('quantity','Required copies',1,None),('owned','Owned / available for this deck',0,None),('set_code','Set code (optional)','',None),('collector','Collector number (optional)','',None),('printing','Printing / treatment','Standard',('Standard','Foil','Alternate art','Showcase','Promo','Other')),('language','Language','English',('English','Chinese','French','Japanese','Other')),('condition','Condition','Near mint',('Near mint','Lightly played','Moderately played','Heavily played','Damaged','Other')),('manual_price','Manual unit reference ('+page.current['currency']+')','',None),('reference_source','Reference source / evidence text','',None),('reference_checked','Manual reference source date YYYY-MM-DD',date.today().isoformat(),None),('image_url','Artwork HTTPS image URL (optional)','',None),('notes','Notes','',None)]
        for i,(key,label,default,choices) in enumerate(fields):
            cell=ttk.Frame(frame,padding=(0,0,12,8));cell.grid(row=i//2,column=i%2,sticky='ew')
            value=(existing or preset or {}).get(key,default)
            if key=='manual_price' and value not in (None,''):value=f'{value/100:.2f}'
            v=tk.StringVar(value='' if value is None else str(value));self.vars[key]=v
            ttk.Label(cell,text=label).pack(anchor='w')
            widget=ttk.Combobox(cell,textvariable=v,values=choices,width=42) if choices else ttk.Entry(cell,textvariable=v,width=45)
            widget.pack(fill='x')
        link=ttk.Frame(frame);link.grid(row=7,columnspan=2,sticky='ew',pady=8)
        ttk.Label(link,text='Preferred monitored ONE-copy listing (region/game filters above limit choices)').pack(anchor='w')
        watches=[w for w in page.app.scope() if w['game'] in ('Unspecified',page.current['game'])]
        if existing and existing['watch_id'] and all(w['id']!=existing['watch_id'] for w in watches):
            watches+=page.app.db.rows('SELECT * FROM watches WHERE id=?',(existing['watch_id'],))
        self.watches={f"#{w['id']} {w['label'] or w['title'] or w['url']}":w['id'] for w in watches}
        self.watch=tk.StringVar(value=next((k for k,v in self.watches.items() if existing and v==existing['watch_id']),'No linked listing'))
        self.watch_picker=ttk.Combobox(link,textvariable=self.watch,values=['No linked listing',*self.watches],state='readonly',width=93)
        self.watch_picker.pack(fill='x')
        self.confirm=tk.BooleanVar(value=bool((existing or {}).get('listing_confirmed',False)))
        self.watch_picker.bind('<<ComboboxSelected>>',lambda e:self.confirm.set(False))
        def identity_changed(*_):
            self.confirm.set(False)
            self.vars['manual_price'].set('')
            self.vars['reference_source'].set('')
            self.vars['reference_checked'].set(date.today().isoformat())
        for key in ('name','set_code','collector','printing','language','condition'):
            self.vars[key].trace_add('write',identity_changed)
        ttk.Checkbutton(link,text='I confirmed this listing is ONE copy of this exact printing, language and condition.',variable=self.confirm).pack(anchor='w',pady=6)
        ttk.Label(link,text='A stock flag does not verify the seller has every required copy. Manual references are not buying offers.',style='Muted.TLabel').pack(anchor='w')
        ttk.Button(frame,text='Save card',command=self.save,style='Accent.TButton').grid(row=8,column=1,sticky='e',pady=8)
    def save(self):
        try:
            v={k:value.get().strip() for k,value in self.vars.items()}
            for k in ('quantity','owned'):v[k]=int(v[k])
            v['manual_price']=money(v['manual_price']) if v['manual_price'] else None
            v['watch_id']=self.watches.get(self.watch.get());v['listing_confirmed']=self.confirm.get()
            self.page.store.save_entry(self.page.current['id'],v,self.existing['id'] if self.existing else None)
        except (ValueError,sqlite3.Error) as e:messagebox.showerror('Could not save card',str(e),parent=self);return
        self.page.refresh();self.destroy()


class ListImport(tk.Toplevel):
    def __init__(self,page):
        super().__init__(page.app);self.page=page;self.title('Import deck list');self.geometry('760x600');self.configure(bg='#0d1321');self.transient(page.app)
        ttk.Label(self,text='Append cards to the selected deck. Use “3 Card Name”, “3x Card Name”, or [Section].\nPrinting, ownership, references and store links can be edited afterwards. No names are silently matched to listings.',style='Muted.TLabel',padding=16).pack(anchor='w')
        self.text=tk.Text(self,bg='#151f32',fg='#e9effa',insertbackground='#e9effa',font=(page.app.font_family,11));self.text.pack(fill='both',expand=True,padx=16)
        buttons=ttk.Frame(self,padding=16);buttons.pack(fill='x')
        ttk.Button(buttons,text='Load text file',command=self.load).pack(side='left')
        ttk.Button(buttons,text='Append parsed cards',command=self.save,style='Accent.TButton').pack(side='right')
    def load(self):
        path=filedialog.askopenfilename(parent=self,filetypes=[('Text files','*.txt'),('All files','*')])
        if path:
            try:
                p=Path(path)
                if p.stat().st_size>1024*1024:raise ValueError('Text file exceeds 1 MB.')
                text=p.read_text(encoding='utf-8-sig');self.text.delete('1.0','end');self.text.insert('1.0',text)
            except (OSError,UnicodeError,ValueError) as e:messagebox.showerror('Import failed',str(e),parent=self)
    def save(self):
        try:count=self.page.store.import_rows(self.page.current['id'],parse_list(self.text.get('1.0','end')))
        except (ValueError,sqlite3.Error) as e:messagebox.showerror('Import failed',str(e),parent=self);return
        self.page.refresh();self.page.app.status.set(f'Appended {count} deck rows. Set printings and link singles listings explicitly.');self.destroy()


class DeckPage(ttk.Frame):
    def __init__(self,app,parent):
        super().__init__(parent,padding=12);self.app=app;self.store=DeckStore(app.db);self.current=None;self.rows={};self._art_key=None;self._art_token=0;self.art=None;self.photo=None;self._art_busy=False
        header=ttk.Frame(self);header.pack(fill='x',pady=(0,8))
        ttk.Label(header,text='Deck builder & cost tracker',style='Heading.TLabel').pack(side='left')
        self.choice=tk.StringVar();self.picker=ttk.Combobox(header,textvariable=self.choice,state='readonly',width=44);self.picker.pack(side='right');self.picker.bind('<<ComboboxSelected>>',lambda e:self.refresh())
        controls=ttk.Frame(self);controls.pack(fill='x',pady=(0,8))
        primary=[('New deck',lambda:self.edit_deck(False)),('Import list',self.import_text),('Add card',self.add),('Edit selected',self.edit),('Find missing in stores',lambda:find_in_stores(self))]
        for title,action in primary:ttk.Button(controls,text=title,command=action).pack(side='left',padx=(0,6))
        more=ttk.Menubutton(controls,text='More deck actions ▾');more.pack(side='left')
        menu=tk.Menu(more,tearoff=False,bg='#151f32',fg='#e9effa',activebackground='#2d4961',activeforeground='#e9effa')
        for title,action in [('Edit deck',lambda:self.edit_deck(True)),('Copy deck',self.copy),('Delete deck',self.delete),('Import CSV',self.import_csv),('Remove selected card',self.remove),('Export CSV',self.export),('Save price snapshot',self.snapshot),('Snapshot history',self.history),('Missing-card budget alert…',self.budget_alert)]:menu.add_command(label=title,command=action)
        more.configure(menu=menu)
        self.summary=tk.StringVar(value='Create a deck or import a list to start.');ttk.Label(self,textvariable=self.summary,style='Muted.TLabel',wraplength=1250).pack(anchor='w',pady=6)
        view_tools=ttk.Frame(self);view_tools.pack(fill='x',pady=(0,8))
        self.view=tk.StringVar(value=app.db.setting('deck_view','Artwork gallery'))
        self.card_search=tk.StringVar();self.section=tk.StringVar(value='All sections')
        ttk.Label(view_tools,text='View',style='Muted.TLabel').pack(side='left',padx=(0,6))
        for variable,values,width in ((self.view,('Artwork gallery','Price table'),17),(self.section,('All sections',*SECTIONS),15)):
            picker=ttk.Combobox(view_tools,textvariable=variable,values=values,state='readonly',width=width);picker.pack(side='left',padx=(0,8));picker.bind('<<ComboboxSelected>>',lambda e:self.update_gallery())
        ttk.Label(view_tools,text='Find card',style='Muted.TLabel').pack(side='left',padx=(0,5))
        ttk.Entry(view_tools,textvariable=self.card_search,width=16).pack(side='left')
        self.card_search.trace_add('write',lambda *_:self.update_gallery())
        ttk.Button(view_tools,text='Deck overview',command=self.overview).pack(side='right')
        ttk.Button(view_tools,text='Find card / artwork',command=self.find_card).pack(side='right',padx=6)
        body=ttk.Frame(self);body.pack(fill='both',expand=True)
        listing=ttk.Frame(body);listing.pack(side='left',fill='both',expand=True)
        self.table=app.make_table(listing,[('name','Card / printing',250),('section','Section',90),('quantity','Need',55),('owned','Owned',55),('missing','Missing',65),('ref','Unit ref',80),('line','Line ref',85),('ask','Fresh ask',85),('cost','Missing ask',90)])
        self.listing=listing
        self.gallery=VisualGrid(listing,app,self.gallery_select,lambda key:self.edit())
        self.table.configure(height=6)
        self.table.bind('<<TreeviewSelect>>',lambda e:self.select());self.table.bind('<Double-1>',lambda e:self.edit())
        preview=ttk.Frame(body,padding=(12,0,0,0));preview.pack(side='right',fill='y')
        self.art_title=tk.StringVar(value='Selected card artwork');ttk.Label(preview,textvariable=self.art_title,style='Muted.TLabel',wraplength=190).pack(anchor='w')
        self.canvas=tk.Canvas(preview,width=190,height=160,bg='#151f32',highlightthickness=0);self.canvas.pack(fill='both',expand=True,pady=6);self.canvas.bind('<Configure>',lambda e:self.draw_art())
        ttk.Button(preview,text='Enlarge artwork',command=self.enlarge_art).pack(fill='x',pady=2)
        ttk.Button(preview,text='Load artwork',command=self.load_art).pack(fill='x',pady=2)
        ttk.Button(preview,text='Choose local image',command=self.choose_local).pack(fill='x',pady=2)
        ttk.Button(preview,text='Use URL instead',command=self.use_url).pack(fill='x',pady=2)
        self.art_status=tk.StringVar(value='Optional URL or local file.');ttk.Label(preview,textvariable=self.art_status,style='Muted.TLabel',wraplength=190).pack(anchor='w',pady=4)
        self.detail=tk.StringVar(value='Game filter selects decks. Region filters never remove cards from deck totals.');ttk.Label(self,textvariable=self.detail,style='Muted.TLabel',wraplength=1250).pack(side='bottom',anchor='w',pady=6)
        body.pack_forget();body.pack(fill='both',expand=True)
    def refresh(self,select_id=None):
        old_id=self.current['id'] if self.current else None
        decks=[d for d in self.store.decks() if self.app.game_filter.get() in ('All games',d['game'])]
        self.deck_map={f"#{d['id']} {d['name']} · {d['game']} · {d['currency']}":d for d in decks};self.picker.configure(values=list(self.deck_map))
        if select_id is not None:self.choice.set(next((k for k,d in self.deck_map.items() if d['id']==select_id),''))
        if self.choice.get() not in self.deck_map:self.choice.set(next(iter(self.deck_map),''))
        self.current=self.deck_map.get(self.choice.get());selected=self.table.selection();self.table.delete(*self.table.get_children());self.rows={}
        if not self.current:
            self.summary.set('No decks in the selected game. Create one or reset the game filter.');self.art=None;self._art_key=None;self._art_token+=1;self.draw_art();self.gallery.set_items([]);self.update_gallery();return
        report=self.store.report(self.current['id']);self.report=report;s=report['summary'];currency=self.current['currency']
        def subtotal(key,count,total):return f"{currency} {s[key]/100:,.2f} ({s[count]}/{s[total]} copies priced)" if s[count] else ('Nothing missing' if s[total]==0 else 'Unpriced')
        self.summary.set(f"Required {s['required']} • owned/available {s['owned']} • missing {s['missing']}\nReference subtotal: {subtotal('reference_subtotal','reference_copies','required')} • Missing-copy reference: {subtotal('missing_reference_subtotal','missing_reference_copies','missing')}\nFresh missing-item asking subtotal: {subtotal('missing_ask_subtotal','missing_ask_copies','missing')} • excludes shipping; seller quantity unverified • {s['reference_old_copies']} copies use stale/failed/paused reference asks")
        for r in report['lines']:
            key=str(r['id']);self.rows[key]=r
            name=r['name']+' · '+r['printing']+' / '+r['language']+' / '+r['condition']
            if r['set_code'] or r['collector']:name+=' · '+r['set_code']+' '+r['collector']
            self.table.insert('','end',iid=key,values=(name,r['section'],r['quantity'],r['owned'],r['missing'],self.app.cash(r['reference']),self.app.cash(r['reference_line']),self.app.cash(r['fresh_ask']),self.app.cash(r['missing_ask'])))
        for key in selected:
            if self.table.exists(key):self.table.selection_set(key)
        if old_id!=self.current['id']:self._art_key=None;self._art_token+=1;self.art=None;self._requested_selected_art=None;self.draw_art()
        self.select()
        self.update_gallery()
    def update_gallery(self):
        if not hasattr(self,'gallery'):return
        query=self.card_search.get().casefold();section=self.section.get()
        items=[]
        for row in self.rows.values():
            if query not in row['name'].casefold() or section not in ('All sections',row['section']):continue
            items.append(dict(id=row['id'],title=row['name'],image_url=row['image_url'],image_path=row['image_path'],
                subtitle=f"Need {row['quantity']} · Own {row['owned']} · Missing {row['missing']}\nUnit ref {self.current['currency']} {self.app.cash(row['reference'])}",fallback=row['section'].upper()))
        self.gallery.message='No matching cards. Clear the card search, or add/import cards into your deck.'
        self.gallery.set_items(items)
        if self.view.get()=='Artwork gallery':
            self.table.master.pack_forget();self.gallery.pack(fill='both',expand=True)
        else:
            self.gallery.pack_forget();self.table.master.pack(fill='both',expand=True)
        self.app.db.set_setting('deck_view',self.view.get())
    def gallery_select(self,key):
        if self.table.exists(key):self.table.selection_set(key);self.select()
    def budget_alert(self):
        from .deck_alerts import configure
        return configure(self)
    def overview(self):
        from .deck_charts import show
        return show(self)
    def find_card(self):
        if not self.current:return
        if not self.app.plugins.providers(self.current['game']):
            messagebox.showinfo('Add a catalogue provider','This game works with manual cards, image URLs, local artwork and compatible store watches. Install a catalogue provider in Settings → Game / store plugins to add card search.',parent=self);return self.app.manage_plugins()
        from .catalogue_ui import CatalogueSearch
        return CatalogueSearch(self,match=bool(self.selected()))
    def enlarge_art(self):
        if self.art is None:self.art_status.set('Select a card with artwork first.');return
        from PIL import ImageTk
        window=tk.Toplevel(self.app);window.title(self.art_title.get());window.configure(bg='#151f32')
        photo=ImageTk.PhotoImage(self.art,master=window);label=ttk.Label(window,image=photo);label.image=photo;label.pack(padx=18,pady=18)
        ttk.Label(window,text=self.art_title.get(),wraplength=450).pack(pady=(0,14))
        window.bind('<Escape>',lambda e:window.destroy())
    def selected(self):
        ids=self.table.selection();return self.rows.get(ids[0]) if ids else None
    def select(self):
        r=self.selected()
        self.gallery.selected=str(r['id']) if r else None;self.gallery.schedule()
        if not r:
            self._requested_selected_art=None
            self.detail.set('Owned counts are per-deck plans, not a shared collection reservation. Estimates are not sale valuations or verified complete shopping baskets.')
            if self._art_key is not None or self.art is not None:self._art_key=None;self._art_token+=1;self.art=None;self.draw_art()
            return
        self.detail.set(r['reference_basis']+' • '+r['offer_status']+'\n'+(r['listing_url'] or 'No linked store offer')+' • Last price check: '+(r['price_checked'] or 'never')+' • Manual source date: '+(r['reference_checked'] or 'not set'))
        key=(r['id'],self.app.images.key(r['image_url'],r['image_path']))
        if key!=self._art_key:self._art_key=key;self._art_token+=1;self.art=None;self.art_title.set(r['name']);self.art_status.set('Local image saved.' if r['image_path'] else 'URL available.' if r['image_url'] else 'Add an artwork URL or choose a file.');self.draw_art()
        if key!=getattr(self,'_requested_selected_art',None) and (r['image_url'] or r['image_path']):
            self._requested_selected_art=key;self.load_art()
    def edit_deck(self,existing):
        if existing and not self.current:return
        d=self.current if existing else {};game=self.app.game_filter.get() if self.app.game_filter.get()!='All games' else 'Riftbound'
        fields=[('name','Deck name',d.get('name',''),None),('game','Game',d.get('game',game),tuple(dict.fromkeys((*GAMES,*self.app.plugins.games())))),('currency','Pricing currency',d.get('currency','AUD'),CURRENCIES),('notes','Deck notes',d.get('notes',''),None)]
        def save(v):
            deck_id=self.store.save_deck(v['name'],v['game'],v['currency'],v['notes'],d.get('id'))
            if self.app.game_filter.get() not in ('All games',v['game']):self.app.game_filter.set('All games')
            self.app.refresh()
            self.refresh(deck_id)
        return Form(self.app,'Deck details (game/currency lock once cards exist)',fields,save)
    def add(self):
        if self.current:return CardEditor(self)
    def edit(self):
        if r:=self.selected():return CardEditor(self,r)
    def copy(self):
        if self.current:self.refresh(self.store.clone(self.current['id']))
    def delete(self):
        if self.current and messagebox.askyesno('Delete deck','Delete this deck, its card rows and saved snapshots? Store watches remain.',parent=self):self.store.delete_deck(self.current['id']);self.choice.set('');self.refresh()
    def remove(self):
        if (r:=self.selected()) and messagebox.askyesno('Remove card row','Remove this row from the deck? Its linked store watch remains.',parent=self):self.store.remove_entry(self.current['id'],r['id']);self.refresh()
    def import_text(self):
        if self.current:return ListImport(self)
    def import_csv(self):
        if not self.current:return
        path=filedialog.askopenfilename(parent=self,filetypes=[('CSV','*.csv')])
        if path:
            try:
                p=Path(path)
                if p.stat().st_size>2*1024*1024:raise ValueError('CSV exceeds 2 MB.')
                count=self.store.csv_import(self.current['id'],p.read_text(encoding='utf-8-sig'));self.refresh();self.app.status.set(f'Appended {count} rows. CSV watch links and local file paths are not imported; confirm links explicitly.')
            except (OSError,UnicodeError,ValueError,csv.Error,sqlite3.Error) as e:messagebox.showerror('CSV import failed',str(e),parent=self)
    def export(self):
        if not self.current:return
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.csv',initialfile='deck_list.csv')
        if path:
            try:Path(path).write_text(self.store.csv_export(self.current['id']),encoding='utf-8-sig');self.app.status.set('Deck CSV exported. Reference amounts are manual values; watch links require confirmation on import.')
            except OSError as e:messagebox.showerror('Export failed',str(e),parent=self)
    def snapshot(self):
        if self.current:self.store.snapshot(self.current['id']);self.app.status.set('Saved a deck price snapshot with copy coverage and underlying price evidence.')
    def history(self):
        if not self.current:return
        snapshots=self.store.snapshots(self.current['id']);window=tk.Toplevel(self.app);window.title('Deck snapshot history — '+self.current['name']);window.geometry('1050x650');window.configure(bg='#0d1321')
        ttk.Label(window,text='Explicit saved estimates; deck composition and ownership may change. Unknown prices are partial subtotals.\nChart uses the current deck currency only and omits snapshots with no priced copies.',style='Muted.TLabel',padding=14).pack(anchor='w')
        canvas=tk.Canvas(window,bg='#151f32',height=180,highlightthickness=0);canvas.pack(fill='x',padx=14,pady=8)
        points=[]
        for snapshot in reversed(snapshots):
            s=json.loads(snapshot['summary'])
            if snapshot['currency']==self.current['currency'] and s['reference_copies']:points.append((snapshot,s))
        if points:
            values=[s['reference_subtotal']/100 for _,s in points];lo,hi=min(values),max(values)
            xy=[(50+i*900/max(1,len(values)-1),145-(v-lo)*100/max(1,hi-lo)) for i,v in enumerate(values)]
            if len(xy)>1:canvas.create_line(*[v for p in xy for v in p],fill='#6ce3b4',width=2)
            for x,y in xy:canvas.create_oval(x-3,y-3,x+3,y+3,fill='#6ce3b4')
            canvas.create_text(20,18,anchor='w',fill='#e9effa',text=f"Reference subtotal {self.current['currency']} • observed snapshot range {lo:.2f}–{hi:.2f}")
        else:canvas.create_text(30,80,anchor='w',fill='#95a8c8',text='Save priced snapshots to build a history.')
        table=self.app.make_table(window,[('at','Saved (UTC)',190),('currency','Currency',70),('ref','Reference subtotal',150),('coverage','Priced copies',100),('missing','Fresh missing ask subtotal',180)])
        snapshot_map={}
        for snap in snapshots:
            s=json.loads(snap['summary']);key=str(snap['id']);snapshot_map[key]=snap
            table.insert('','end',iid=key,values=(snap['at'],snap['currency'],self.app.cash(s['reference_subtotal']) if s['reference_copies'] else 'Unpriced',f"{s['reference_copies']}/{s['required']}",self.app.cash(s['missing_ask_subtotal']) if s['missing_ask_copies'] else 'No priced missing copies'))
        def inspect():
            if ids:=table.selection():
                snap=snapshot_map[ids[0]];view=tk.Toplevel(window);view.title('Saved snapshot evidence');view.geometry('1000x500')
                t=self.app.make_table(view,[('name','Card',250),('qty','Copies',65),('ref','Unit reference',100),('source','Basis',250),('checked','Listing checked',230)])
                for r in json.loads(snap['evidence']):t.insert('','end',values=(r['name'],r['quantity'],self.app.cash(r['reference']),r['reference_basis'],r['price_checked'] or 'Not checked'))
        ttk.Button(window,text='Inspect selected snapshot',command=inspect).pack(anchor='e',padx=14,pady=10)
        return window
    def choose_local(self):
        if not (r:=self.selected()):return
        path=filedialog.askopenfilename(parent=self,filetypes=[('Card images','*.png *.jpg *.jpeg *.webp *.avif *.gif'),('All files','*')])
        if path:self.store.local_image(r['id'],path);self.refresh();self.table.selection_set(str(r['id']));self.select();self.load_art()
    def use_url(self):
        if r:=self.selected():self.store.local_image(r['id'],'');self.refresh();self.table.selection_set(str(r['id']));self.select();self.load_art()
    def load_art(self):
        if not (r:=self.selected()):return
        if not r['image_url'] and not r['image_path']:self.art_status.set('Set a URL in Edit card, or choose a local image.');return
        self._art_token+=1;token=self._art_token;entry_id=r['id'];self.art_status.set('Loading artwork…')
        def received(image,status):
            if self.winfo_exists():
                self.art_received(entry_id,token,image,None if image is not None else status)
                if self.selected() and self.selected()['id']==entry_id and token==self._art_token:self.art_status.set(status)
        self.app.images.request(r['image_url'],r['image_path'],received)
    def art_received(self,entry_id,token,image,error):
        self._art_busy=False
        row=self.selected()
        if not row or row['id']!=entry_id or token!=self._art_token:return
        self.art=image;self.art_status.set('Artwork preview loaded.' if not error else 'Artwork unavailable: '+error);self.draw_art()
    def draw_art(self):
        self.canvas.delete('all')
        if self.art is None:self.photo=None;self.canvas.create_text(95,70,text='Optional artwork',fill='#95a8c8');return
        from PIL import ImageTk,Image
        image=self.art.copy();image.thumbnail((max(1,self.canvas.winfo_width()-8),max(1,self.canvas.winfo_height()-8)),Image.Resampling.LANCZOS);self.photo=ImageTk.PhotoImage(image,master=self.app)
        self.canvas.create_image(self.canvas.winfo_width()/2,self.canvas.winfo_height()/2,image=self.photo)


def find_in_stores(page):
    """Window listing catalogue matches for the current deck's missing, unlinked cards."""
    from .product_catalogue import deck_matches, link_entry
    if not page.current:
        page.app.status.set('Choose a deck first.'); return
    deck = page.current
    matches = deck_matches(page.app.db, deck['id'])
    win = tk.Toplevel(page); win.title('Find missing cards in your stores'); win.geometry('1000x520'); win.transient(page.app)
    frame = ttk.Frame(win, padding=14); frame.pack(fill='both', expand=True)
    if not matches:
        ttk.Label(frame, text='No catalogue matches for missing, unlinked cards.\nSync stores on the Discover page first, or check the card names.', style='Muted.TLabel').pack(anchor='w')
        return win
    ttk.Label(frame, text='Cheapest in-stock match is preselected for each card. Check the printing and language before linking.', style='Muted.TLabel').pack(anchor='w', pady=(0, 8))
    cols = [('card', 'Deck card', 180), ('title', 'Store listing', 420), ('store', 'Store', 140), ('price', 'Price', 80), ('stock', 'Stock', 80)]
    tree = ttk.Treeview(frame, columns=[c[0] for c in cols], show='headings', selectmode='extended')
    for key, label, width in cols:
        tree.heading(key, text=label); tree.column(key, width=width, stretch=True)
    tree.pack(fill='both', expand=True)
    lookup = {}
    for m in matches:
        for i, c in enumerate(m['candidates']):
            iid = tree.insert('', 'end', values=(m['entry']['name'] if i == 0 else '', c['title'], c['store'],
                                                 '' if c['price'] is None else f"{c['price']/100:,.2f}",
                                                 {1: 'In stock', 0: 'Sold out'}.get(c['available'], 'Unknown')))
            lookup[iid] = (m['entry'], c)
            if i == 0:
                tree.selection_add(iid)
    def link():
        done, seen = 0, set()
        for iid in tree.selection():
            entry, cand = lookup[iid]
            if entry['id'] in seen:
                continue
            seen.add(entry['id'])
            try:
                link_entry(page.app.db, deck['id'], entry['id'], cand, deck['game']); done += 1
            except ValueError as e:
                page.app.status.set(f"{entry['name']}: {e}")
        page.app.changed(); page.refresh()
        page.app.status.set(f'Linked {done} cards. Prices appear after the first check.')
        win.destroy()
    ttk.Button(frame, text='Link selected (one per card)', style='Accent.TButton', command=link).pack(anchor='e', pady=8)
    return win
