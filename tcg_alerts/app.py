"""Desktop UI. All widget access stays on the main thread."""
from __future__ import annotations
import argparse
import csv
import queue
import threading
import time
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font as tkfont
import webbrowser
from datetime import datetime, timezone
from urllib.parse import urlsplit
from .core import Database, data_dir, money
from .monitor import Monitor
from .catalog import GAMES, COUNTRIES, AU_STATES, matches
from .news import NewsMonitor
from .panels import NewsPage, AnalyticsPage
from .additions import Directory,Compare,Calendar,VariantPicker,delivery_editor
from .desktop import Desktop
from .decks_ui import DeckPage
from .shell import CollectorShell

BG = '#0d1321'
PANEL = '#151f32'
TEXT = '#e9effa'
MUTED = '#95a8c8'
ACCENT = '#6ce3b4'


class WatchDialog(tk.Toplevel):
    def __init__(self, parent, db, callback, existing=None):
        super().__init__(parent)
        self.db, self.callback, self.existing = db, callback, existing
        self.title('Edit watch' if existing else 'Track a product')
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        frame = ttk.Frame(self, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Keep an eye on the right box.', style='Heading.TLabel').grid(row=0, columnspan=2, sticky='w', pady=(0, 16))
        fields = [('url', 'Exact product URL'), ('label', 'Display name (optional)'),
                  ('group_name', 'Comparison group (optional)'), ('target', 'Alert at or below (same currency)'),
                  ('shipping', 'Shipping (blank = unknown, 0 = free)')]
        self.vars = {}
        for i, (key, label) in enumerate(fields, 1):
            ttk.Label(frame, text=label).grid(row=i * 2 - 1, columnspan=2, sticky='w', pady=(8, 3))
            val = (existing or {}).get(key)
            if key in ('target', 'shipping') and val is not None:
                val = f'{val / 100:.2f}'
            v = tk.StringVar(value=val if val is not None else '')
            self.vars[key] = v
            entry = ttk.Entry(frame, textvariable=v, width=66)
            entry.grid(row=i * 2, columnspan=2, sticky='ew')
            if key == 'url' and existing:
                entry.configure(state='readonly')
        tags = ttk.Frame(frame)
        tags.grid(row=11, columnspan=2, sticky='ew', pady=(12, 0))
        for key, label, values in (('game', 'Game', GAMES), ('country', 'Store country', COUNTRIES), ('state', 'Store state / region', ('Unspecified', *AU_STATES))):
            cell = ttk.Frame(tags)
            cell.pack(side='left', padx=(0, 8))
            ttk.Label(cell, text=label).pack(anchor='w')
            v = tk.StringVar(value=(existing or {}).get(key, 'Unspecified'))
            self.vars[key] = v
            ttk.Combobox(cell, textvariable=v, values=values, width=20).pack()
        self.restock = tk.BooleanVar(value=bool((existing or {}).get('restock', True)))
        ttk.Checkbutton(frame, text='Notify on confirmed sold out → in stock', variable=self.restock).grid(row=12, columnspan=2, sticky='w', pady=15)
        ttk.Label(frame, text='Group only identical set, language, edition and pack quantity.\nTargets use item + shipping when shipping is known.\nStore tags describe location, not delivery eligibility.\nFor Shopify options, copy the URL after choosing a variant.', style='Muted.TLabel').grid(row=13, columnspan=2, sticky='w')
        if not existing:
            ttk.Button(frame,text='Pick Shopify variant',command=self.pick_variant).grid(row=14,column=0,sticky='w',pady=8)
        ttk.Button(frame, text='Save watch', command=self.save, style='Accent.TButton').grid(row=14, column=1, sticky='e', pady=(18, 0))

    def pick_variant(self):
        def chosen(option):
            if self.winfo_exists():
                self.vars['url'].set(option['url'])
                if not self.vars['label'].get():self.vars['label'].set(option['title'])
        VariantPicker(self.master,self.vars['url'].get(),chosen,owner=self)

    def save(self):
        try:
            fields = {k: v.get().strip() for k, v in self.vars.items()}
            for key in ('target', 'shipping'):
                fields[key] = money(fields[key]) if fields[key] else None
            fields['restock'] = self.restock.get()
            if self.existing:
                fields.pop('url')
                self.db.update(self.existing['id'], **fields)
            else:
                self.db.add(**fields)
        except (ValueError, sqlite3.Error) as e:
            messagebox.showerror('Could not save', str(e), parent=self)
            return
        self.callback()
        self.destroy()


class App(tk.Tk):
    def __init__(self, db, start_monitor=True):
        super().__init__()
        self.db = db
        self.monitor = Monitor(db)
        self.news_monitor = NewsMonitor(db, self.monitor.events)
        self.desktop=Desktop(self.monitor.events)
        self._closing=False
        self.title('TCG Alerts • sealed product radar')
        self.geometry(f'{min(1500, max(1180, self.winfo_screenwidth()-60))}x{min(940, max(700, self.winfo_screenheight()-80))}')
        self.minsize(1180, 700)
        self.configure(bg=BG)
        self.style_ui()
        self.rows = {}
        self.last_refresh = time.monotonic()
        self.search = tk.StringVar()
        self.filter = tk.StringVar(value='All watches')
        self.game_filter = tk.StringVar(value='All games')
        self.country_filter = tk.StringVar(value='All countries')
        self.state_filter = tk.StringVar(value='All states')
        self.status = tk.StringVar(value='Ready • add your first product URL')
        self.search.trace_add('write', lambda *_: self.refresh())
        self.build()
        self.refresh()
        self.protocol('WM_DELETE_WINDOW', self.request_close)
        if start_monitor:
            self.monitor.start()
            self.news_monitor.start()
            self.desktop.start()
        self.after(250, self.drain)

    def style_ui(self):
        families = set(tkfont.families(self))
        self.font_family = next((f for f in ('Segoe UI', 'DejaVu Sans', 'Liberation Sans', 'Arial', 'Helvetica', 'helvetica') if f in families), tkfont.nametofont('TkDefaultFont').actual('family'))
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('.', background=BG, foreground=TEXT, font=(self.font_family, 10))
        s.configure('TFrame', background=BG)
        s.configure('TLabel', background=BG)
        s.configure('Muted.TLabel', foreground=MUTED)
        s.configure('Heading.TLabel', font=(self.font_family, 20, 'bold'))
        s.configure('Title.TLabel', font=(self.font_family, 29, 'bold'))
        s.configure('Metric.TLabel', font=(self.font_family, 22, 'bold'), foreground=ACCENT)
        s.configure('TButton', background=PANEL, foreground=TEXT, padding=(14, 9), borderwidth=0)
        s.map('TButton', background=[('active', '#283953')])
        s.configure('Accent.TButton', background=ACCENT, foreground=BG)
        s.map('Accent.TButton', background=[('active', '#9cefcf')])
        s.configure('TEntry', fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, padding=8)
        s.configure('TCombobox', fieldbackground=PANEL, foreground=TEXT, arrowcolor=ACCENT, padding=7)
        s.map('TCombobox', fieldbackground=[('readonly', PANEL)], foreground=[('readonly', TEXT)])
        s.configure('TNotebook', background=BG, borderwidth=0)
        s.layout('Desk.TNotebook.Tab', [])
        s.configure('Desk.TNotebook', background=BG, borderwidth=0)
        s.configure('Card.TFrame', background='#1b2c3c')
        s.configure('Card.TLabel', background='#1b2c3c', foreground=MUTED)
        s.configure('CardMetric.TLabel', background='#1b2c3c', foreground='#d5e5c8', font=(self.font_family, 22, 'bold'))
        s.configure('TNotebook.Tab', background=PANEL, foreground=MUTED, padding=(20, 12))
        s.map('TNotebook.Tab', background=[('selected', '#24364d')], foreground=[('selected', ACCENT)])
        s.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=42, borderwidth=0)
        s.configure('Treeview.Heading', background='#203049', foreground=MUTED, padding=10, relief='flat')
        s.map('Treeview', background=[('selected', '#2d4961')])
        s.configure('TCheckbutton', background=BG, foreground=TEXT)

    def build(self):
        self.shell = CollectorShell(self)
        outer = self.shell.main
        regions = ttk.Frame(outer)
        regions.pack(fill='x', pady=(0, 16))
        self.tag_boxes = {}
        for label, key, var, values in (
            ('Game', 'game', self.game_filter, ['All games', *GAMES]),
            ('Store country', 'country', self.country_filter, ['All countries', *COUNTRIES]),
            ('State / region', 'state', self.state_filter, ['All states', *AU_STATES, 'Unspecified'])):
            cell = ttk.Frame(regions)
            cell.pack(side='left', fill='x', expand=True, padx=(0, 14))
            ttk.Label(cell, text=label, style='Muted.TLabel').pack(anchor='w', pady=(0, 5))
            box = ttk.Combobox(cell, textvariable=var, values=values, state='readonly', width=19)
            box.pack(fill='x')
            box.bind('<<ComboboxSelected>>', lambda e, k=key: self.tags_changed(k))
            self.tag_boxes[key] = box
        ttk.Button(regions, text='Clear filters', command=self.reset_filters).pack(side='right', anchor='s')
        self.tabs = ttk.Notebook(outer, style='Desk.TNotebook', takefocus=False)
        self.tabs.pack(fill='both', expand=True)
        watch_page = ttk.Frame(self.tabs)
        self.tabs.add(watch_page, text='Watchlist')
        self.watch_page = watch_page
        metrics = ttk.Frame(watch_page)
        metrics.pack(fill='x', pady=(0, 16))
        self.metrics = []
        for i, name in enumerate(('Watching', 'In stock', 'At your target', 'Needs attention')):
            metrics.columnconfigure(i, weight=1, uniform='metric')
            cell = ttk.Frame(metrics, padding=(16, 10), style='Card.TFrame')
            cell.grid(row=0, column=i, sticky='ew', padx=(0, 10 if i<3 else 0))
            value = ttk.Label(cell, text='0', style='CardMetric.TLabel')
            value.pack(anchor='w')
            ttk.Label(cell, text=name, style='Card.TLabel').pack(anchor='w')
            self.metrics.append(value)
        tools = ttk.Frame(watch_page)
        tools.pack(fill='x', pady=(0, 14))
        search = ttk.Frame(tools)
        search.pack(side='left', fill='x', expand=True, padx=(0, 12))
        ttk.Label(search, text='Search your watchlist', style='Muted.TLabel').pack(anchor='w', pady=(0, 5))
        ttk.Entry(search, textvariable=self.search, width=25).pack(fill='x')
        mode = ttk.Frame(tools)
        mode.pack(side='left', padx=(0, 12))
        ttk.Label(mode, text='Show', style='Muted.TLabel').pack(anchor='w', pady=(0, 5))
        picker = ttk.Combobox(mode, textvariable=self.filter, values=['All watches', 'In stock', 'At target', 'Needs attention', 'Paused'], state='readonly', width=18)
        picker.pack()
        picker.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        ttk.Button(tools, text='+ Track a product', style='Accent.TButton', command=self.add).pack(side='right', anchor='s')
        ttk.Button(tools, text='Check prices', command=self.monitor.check_now).pack(side='right', anchor='s', padx=(0, 10))
        self.table = self.make_table(watch_page, [('product', 'Product / group', 300), ('store', 'Store', 165), ('price', 'Item price', 100),
                                               ('stock', 'Availability', 110), ('target', 'Target', 90), ('check', 'Last success / health', 220)])
        self.table.bind('<<TreeviewSelect>>', lambda e: self.selection())
        self.table.bind('<Double-1>', lambda e: self.open_store())
        actions = ttk.Frame(watch_page)
        actions.pack(side='bottom', fill='x', pady=10)
        self.watch_actions = []
        for text, command in [('Open store ↗', self.open_store), ('Edit', self.edit), ('Delivery & units',self.edit_delivery), ('Pause / resume', self.toggle), ('History', self.show_history), ('Remove', self.remove)]:
            button = ttk.Button(actions, text=text, command=command, state='disabled')
            button.pack(side='left', padx=(0, 8))
            self.watch_actions.append(button)
        self.detail = tk.StringVar(value='Add a product URL to start. No sample prices are shown as live data.')
        ttk.Label(watch_page, textvariable=self.detail, style='Muted.TLabel', wraplength=1000).pack(side='bottom', anchor='w', pady=8)
        self.table.master.pack_forget()
        self.table.master.pack(fill='both', expand=True)
        self.empty_watch = ttk.Frame(self.table, padding=25, style='Card.TFrame')
        self.empty_title = ttk.Label(self.empty_watch, text='Your next find starts here', style='CardMetric.TLabel')
        self.empty_title.pack(pady=(0, 10))
        self.empty_text = ttk.Label(self.empty_watch, text='Paste a store product link, choose a target price, and we’ll watch it for you.', style='Card.TLabel', wraplength=500, justify='center')
        self.empty_text.pack(pady=(0, 16))
        ttk.Button(self.empty_watch, text='+ Track your first product', style='Accent.TButton', command=self.add).pack()
        alerts_page = ttk.Frame(self.tabs)
        self.tabs.add(alerts_page, text='Alerts')
        self.alert_table = self.make_table(alerts_page, [('at', 'Time (local)', 170), ('kind', 'Trigger', 90), ('message', 'Alert', 800)])
        self.compare_page=Compare(self,self.tabs)
        self.tabs.add(self.compare_page,text='Compare')
        self.compare_table=self.compare_page.table
        self.decks_page=DeckPage(self,self.tabs)
        self.tabs.add(self.decks_page,text='Decks')
        self.analytics_page = AnalyticsPage(self, self.tabs)
        self.tabs.add(self.analytics_page, text='Analytics')
        self.news_page = NewsPage(self, self.tabs)
        self.tabs.add(self.news_page, text='News')
        self.calendar_page=Calendar(self,self.tabs)
        self.tabs.add(self.calendar_page,text='Calendar')
        self.directory_page=Directory(self,self.tabs)
        self.tabs.add(self.directory_page,text='Stores')
        discovery = ttk.Frame(self.tabs, padding=18)
        self.discovery_page=discovery
        self.tabs.add(discovery, text='Discover')
        ttk.Label(discovery, text='Find products on a store page', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(discovery, text='Paste a collection URL. This reads one page, then lets you choose exact listings to track.\nResults are links, not verified products or prices. Pagination and JavaScript-only pages need manual URLs.', style='Muted.TLabel').pack(anchor='w', pady=10)
        discovery_tools = ttk.Frame(discovery)
        discovery_tools.pack(fill='x', pady=10)
        self.discovery_url = tk.StringVar(value='https://onlypackstcg.com.au/collections/riftbound')
        ttk.Entry(discovery_tools, textvariable=self.discovery_url, width=70).pack(side='left', fill='x', expand=True)
        self.discover_button = ttk.Button(discovery_tools, text='Find links', command=self.start_discovery)
        self.discover_button.pack(side='right', padx=10)
        self.discovery_table = self.make_table(discovery, [('title', 'Store title', 400), ('url', 'Product URL', 600)])
        ttk.Button(discovery, text='Track selected listing', command=self.track_discovery).pack(anchor='e', pady=10)
        settings = ttk.Frame(self.tabs, padding=20)
        self.tabs.add(settings, text='Settings & data')
        ttk.Label(settings, text='Private by default.', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(settings, text='Checks run every 15 minutes while this app is open. Sleeping or closing the PC stops checks.\nFailures back off automatically. Manual checks respect the scheduled cooldown.\nAlerts are saved here and ring the bell. Windows native tray notifications are supported; email/Telegram are not configured.\nThe app reads public Shopify product data and single-offer JSON-LD pages.\nIt respects robots.txt and does not bypass login, CAPTCHA or blocked storefronts.\n\nYour database: ' + str(self.db.path), style='Muted.TLabel', wraplength=1000).pack(anchor='w', pady=18)
        self.native_enabled=tk.BooleanVar(value=self.db.setting('native_notifications',True))
        self.close_to_tray=tk.BooleanVar(value=self.db.setting('close_to_tray',False))
        ttk.Checkbutton(settings,text='Native Windows notifications',variable=self.native_enabled,command=self.save_native).pack(anchor='w',pady=4)
        ttk.Checkbutton(settings,text='Closing minimizes to tray (when ready)',variable=self.close_to_tray,command=self.save_native).pack(anchor='w',pady=4)
        buttons=ttk.Frame(settings);buttons.pack(anchor='w',pady=8)
        for title,action in [('Minimize to tray',self.minimize_to_tray),('Test notification',self.test_notification),('Exit application',self.close)]:ttk.Button(buttons,text=title,command=action).pack(side='left',padx=(0,8))
        self.native_status=tk.StringVar(value='Closing exits by default. Tray initializes on Windows when monitoring starts.')
        ttk.Label(settings,textvariable=self.native_status,style='Muted.TLabel',wraplength=1050).pack(anchor='w',pady=4)
        ttk.Button(settings, text='Export watchlist CSV', command=self.export).pack(anchor='w', pady=6)
        ttk.Button(settings, text='Back up complete database', command=self.backup).pack(anchor='w', pady=6)
        ttk.Label(outer, textvariable=self.status, style='Muted.TLabel').pack(side='bottom',anchor='w', pady=(12, 0))
        self.tabs.pack_forget()
        self.tabs.pack(fill='both',expand=True)
        self.tabs.bind('<<NotebookTabChanged>>', self.shell.changed)
        self.shell.changed()
        self.bind('<Control-1>', lambda e: self.tabs.select(self.watch_page))
        self.bind('<Control-f>', self.focus_search)

    def focus_search(self, event=None):
        self.tabs.select(self.watch_page)
        def focus(widget):
            if isinstance(widget, ttk.Entry) and str(widget.cget('textvariable')) == str(self.search):
                widget.focus_set()
                widget.selection_range(0, 'end')
            for child in widget.winfo_children():
                focus(child)
        focus(self.watch_page)
        return 'break'

    def start_discovery(self):
        from .sources import Client, discover
        url = self.discovery_url.get().strip()
        self.discover_button.configure(state='disabled')
        self.status.set('Discovering product links…')
        def worker():
            try:
                self.monitor.events.put(('discovered', discover(url, Client())))
            except Exception as e:
                self.monitor.events.put(('discovery_error', str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def track_discovery(self):
        selection = self.discovery_table.selection()
        if selection:
            values = self.discovery_table.item(selection[0], 'values')
            dialog = WatchDialog(self, self.db, self.changed)
            dialog.vars['url'].set(values[1])
            dialog.vars['label'].set(values[0])
            self.prefill_tags(dialog)

    def scope(self):
        return [w for w in self.db.watches() if matches(w, self.game_filter.get(), self.country_filter.get(), self.state_filter.get())]

    def tags_changed(self, key):
        if key == 'state' and self.state_filter.get() in AU_STATES:
            self.country_filter.set('Australia')
        elif key == 'country':
            self.state_filter.set('All states')
        self.refresh()

    def reset_filters(self):
        self.game_filter.set('All games')
        self.country_filter.set('All countries')
        self.state_filter.set('All states')
        self.filter.set('All watches')
        self.search.set('')
        self.refresh()

    def prefill_tags(self, dialog):
        for key, var, all_value in (('game', self.game_filter, 'All games'), ('country', self.country_filter, 'All countries'), ('state', self.state_filter, 'All states')):
            if var.get() != all_value:
                dialog.vars[key].set(var.get())

    def make_table(self, parent, columns):
        wrap = ttk.Frame(parent)
        wrap.pack(fill='both', expand=True)
        table = ttk.Treeview(wrap, columns=[c[0] for c in columns], show='headings', selectmode='browse')
        for key, label, width in columns:
            table.heading(key, text=label)
            table.column(key, width=width, minwidth=60, stretch=True)
        scroll = ttk.Scrollbar(wrap, orient='vertical', command=table.yview)
        horizontal = ttk.Scrollbar(wrap, orient='horizontal', command=table.xview)
        horizontal.pack(side='bottom', fill='x')
        table.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        table.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        return table

    @staticmethod
    def cash(value, currency=''):
        return f'{currency} {value / 100:,.2f}'.strip() if value is not None else '—'

    @staticmethod
    def local(value):
        return datetime.fromisoformat(value).astimezone().strftime('%d %b %H:%M') if value else 'Not checked'

    @staticmethod
    def stale(w):
        return not w['checked'] or (datetime.now(timezone.utc) - datetime.fromisoformat(w['checked'])).total_seconds() > 1800

    def healthy(self, w):
        return w['enabled'] and not w['error'] and not self.stale(w)

    def at_target(self, w):
        return self.healthy(w) and w['stock'] == 'in_stock' and w['target'] is not None and w['price'] is not None and w['price'] + (w['shipping'] or 0) <= w['target']

    def refresh(self):
        selected = self.table.selection() if hasattr(self, 'table') else ()
        all_watches = self.db.watches()
        for key, all_value, defaults in (('game', 'All games', GAMES), ('country', 'All countries', COUNTRIES), ('state', 'All states', AU_STATES)):
            extra_games=[d['game'] for d in self.decks_page.store.decks()] if key=='game' else []
            self.tag_boxes[key].configure(values=[all_value, *dict.fromkeys([*defaults, *extra_games, *(w[key] for w in all_watches)])])
        watches = self.scope()
        self.rows = {str(w['id']): w for w in watches}
        counts = [sum(bool(w['enabled']) for w in watches), sum(self.healthy(w) and w['stock'] == 'in_stock' for w in watches), sum(self.at_target(w) for w in watches), sum(w['enabled'] and (bool(w['error']) or self.stale(w)) for w in watches)]
        for label, count in zip(self.metrics, counts):
            label.configure(text=str(count))
        self.table.delete(*self.table.get_children())
        for w in watches:
            query = self.search.get().lower()
            if query not in ' '.join(str(w[k] or '') for k in ('label', 'title', 'url', 'group_name')).lower():
                continue
            mode = self.filter.get()
            if mode == 'In stock' and not (self.healthy(w) and w['stock'] == 'in_stock'):
                continue
            if mode == 'At target' and not self.at_target(w):
                continue
            if mode == 'Needs attention' and not (w['enabled'] and (w['error'] or self.stale(w))):
                continue
            if mode == 'Paused' and w['enabled']:
                continue
            title = w['label'] or w['title'] or 'Awaiting first check'
            title += ' [' + w['game'] + ']'
            if w['group_name']:
                title += ' · ' + w['group_name']
            state = (w['stock'] or 'unknown').replace('_', ' ')
            health = 'Paused' if not w['enabled'] else 'Check failed' if w['error'] else 'Stale' if self.stale(w) else 'OK'
            store_label = urlsplit(w['url']).netloc + ' · ' + w['country'] + ' / ' + w['state']
            self.table.insert('', 'end', iid=str(w['id']), values=(title, store_label, self.cash(w['price'], w['currency'] or ''), state, self.cash(w['target']), self.local(w['checked']) + ' / ' + health))
        for item in selected:
            if self.table.exists(item):
                self.table.selection_set(item)
        if self.table.get_children():
            self.empty_watch.place_forget()
        else:
            self.empty_title.configure(text='Your next find starts here' if not all_watches else 'No matching products')
            self.empty_text.configure(text='Paste a store product link, choose a target price, and we’ll watch it for you.' if not all_watches else 'Try another search or clear the game and region filters.')
            self.empty_watch.place(relx=.5, rely=.5, anchor='center')
        self.alert_table.delete(*self.alert_table.get_children())
        for a in self.db.alerts():
            if str(a['watch_id']) not in self.rows:
                continue
            self.alert_table.insert('', 'end', values=(self.local(a['at']), a['kind'], a['message']))
        self.compare_page.refresh()
        self.decks_page.refresh()
        self.calendar_page.refresh()
        self.directory_page.refresh()
        self.selection()
        self.analytics_page.refresh()
        self.news_page.refresh()

    def selected(self):
        selection = self.table.selection()
        return self.rows.get(selection[0]) if selection else None

    def selection(self):
        w = self.selected()
        for button in self.watch_actions:
            button.configure(state='normal' if w else 'disabled')
        if not w:
            self.detail.set('Select a product to see its source, delivery details, and latest check.')
        if w:
            self.detail.set(w['game'] + ' • Store: ' + w['country'] + ' / ' + w['state'] + ' • ' + w['url'] + '\n' + (w['error'] or f"Source: {w['source'] or 'pending'} • Shipping: {self.cash(w['shipping']) if w['shipping'] is not None else 'unknown'} • Last attempt: {self.local(w['attempted'])}"))

    def edit_delivery(self):
        if w:=self.selected():delivery_editor(self,w)

    def changed(self):
        self.refresh()
        self.monitor.check_now()

    def add(self):
        dialog = WatchDialog(self, self.db, self.changed)
        self.prefill_tags(dialog)

    def edit(self):
        if w := self.selected():
            WatchDialog(self, self.db, self.changed, w)

    def toggle(self):
        if w := self.selected():
            self.db.update(w['id'], enabled=not w['enabled'])
            self.changed()

    def remove(self):
        if (w := self.selected()) and messagebox.askyesno('Remove watch', 'Remove this watch and its price history?', parent=self):
            self.db.delete(w['id'])
            self.refresh()

    def open_store(self):
        if w := self.selected():
            if webbrowser.open(w['url']):
                self.db.log_open(w['id'])
                self.analytics_page.refresh()

    def show_history(self):
        if not (w := self.selected()):
            return
        window = tk.Toplevel(self)
        window.title('Price history • ' + (w['label'] or w['title'] or w['url']))
        window.geometry('850x600')
        window.configure(bg=BG)
        rows = self.db.history(w['id'])
        canvas = tk.Canvas(window, background=PANEL, height=200, highlightthickness=0)
        canvas.pack(fill='x', padx=20, pady=20)
        if rows:
            prices = [r['price'] for r in reversed(rows)]
            lo, hi = min(prices), max(prices)
            canvas.create_text(20, 16, anchor='w', text=f"{w['currency']}  low {lo / 100:.2f} / high {hi / 100:.2f} • observations in order", fill=TEXT)
            points = [(30 + i * 740 / max(1, len(prices) - 1), 170 - (p - lo) * 125 / max(1, hi - lo)) for i, p in enumerate(prices)]
            if len(points) > 1:
                canvas.create_line(*[v for point in points for v in point], fill=ACCENT, width=3)
            else:
                x, y = points[0]
                canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=ACCENT)
        else:
            canvas.create_text(30, 80, anchor='w', text='History appears after the first successful check.', fill=MUTED)
        table = self.make_table(window, [('at', 'Time (local)', 180), ('price', 'Item price', 140), ('stock', 'Availability', 130), ('source', 'Source', 150)])
        for r in rows:
            table.insert('', 'end', values=(self.local(r['at']), self.cash(r['price'], r['currency']), r['stock'].replace('_', ' '), r['source']))

    def export(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.csv', initialfile='tcg_watchlist.csv', filetypes=[('CSV', '*.csv')])
        if path:
            try:
                rows = self.db.watches()
                keys = ['url', 'label', 'group_name', 'game', 'country', 'state', 'pack_count', 'shipping_postcode', 'shipping_country', 'pickup', 'currency', 'price', 'stock', 'target', 'shipping', 'checked', 'error']
                with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow([k + '_minor_units' if k in ('price', 'target', 'shipping') else k for k in keys])
                    for row in rows:
                        # Prevent spreadsheet formula execution in store-provided titles.
                        writer.writerow([("'" + str(row[k])) if isinstance(row[k], str) and row[k].startswith(('=', '+', '-', '@', '\t', '\r')) else row[k] for k in keys])
                self.status.set('Watchlist exported.')
            except OSError as e:
                messagebox.showerror('Export failed', str(e), parent=self)

    def backup(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension='.sqlite3', initialfile='tcg_alerts_backup.sqlite3')
        if path:
            try:
                self.db.backup(path)
                self.status.set('Database backup saved. Restore with: python run.py --database PATH')
            except (OSError, sqlite3.Error, ValueError) as e:
                messagebox.showerror('Backup failed', str(e), parent=self)

    def drain(self):
        changed = False
        try:
            while True:
                kind, payload = self.monitor.events.get_nowait()
                if kind == 'alert':
                    self.bell()
                    if self.native_enabled.get():self.desktop.notify(payload)
                    self.status.set('ALERT • ' + payload)
                    changed = True
                elif kind == 'deck_art':
                    self.decks_page.art_received(*payload)
                elif kind == 'variant_options':
                    dialog,requested,options,error=payload
                    if dialog.winfo_exists():dialog.receive(requested,options,error)
                elif kind == 'desktop_action':
                    if payload=='show':self.deiconify();self.lift()
                    elif payload=='check':self.monitor.check_now()
                    elif payload=='exit':self.close();return
                elif kind == 'news_updated':
                    changed = True
                elif kind == 'discovered':
                    self.discovery_table.delete(*self.discovery_table.get_children())
                    for url, title in payload:
                        self.discovery_table.insert('', 'end', values=(title, url))
                    self.discover_button.configure(state='normal')
                    self.status.set(f'{len(payload)} product links found. Select one to track.')
                elif kind == 'discovery_error':
                    self.discover_button.configure(state='normal')
                    self.status.set('Discovery failed: ' + payload)
                elif kind in ('updated', 'error'):
                    changed = True
                elif kind == 'status':
                    self.status.set(payload)
                elif kind == 'idle' and not self.status.get().startswith('ALERT'):
                    self.status.set(payload)
        except queue.Empty:
            pass
        if changed or time.monotonic() - self.last_refresh > 60:
            self.refresh()
            self.last_refresh = time.monotonic()
        self.native_status.set('Native tray ready; visibility depends on Windows settings.' if self.desktop.available() else self.desktop.error or 'Tray is not ready. The window remains accessible.')
        self.after(500, self.drain)

    def save_native(self):
        self.db.set_setting('native_notifications',self.native_enabled.get())
        self.db.set_setting('close_to_tray',self.close_to_tray.get())

    def test_notification(self):
        if not self.desktop.available():self.desktop.start()
        self.bell()
        self.status.set('Test notification requested.' if self.desktop.notify('This is a TCG Alerts test.') else self.desktop.error or 'Tray is starting; try again shortly.')

    def minimize_to_tray(self):
        if self.desktop.available():self.withdraw();return True
        self.status.set(self.desktop.error or 'Tray is not ready; the window remains visible.')
        return False

    def request_close(self):
        if self.close_to_tray.get() and self.minimize_to_tray():return
        self.close()

    def close(self):
        if self._closing:return
        self._closing=True
        self.desktop.stop()
        self.monitor.close()
        self.news_monitor.close()
        self.destroy()


def main():
    parser = argparse.ArgumentParser(description='TCG Alerts desktop tracker')
    parser.add_argument('--database', type=str)
    parser.add_argument('--smoke-test', action='store_true', help='Open and close a temporary empty GUI without network checks')
    args = parser.parse_args()
    if args.smoke_test:
        import sys
        if sys.platform=='win32':
            import pystray
            from PIL import Image
            pystray.Icon('TCGAlertsSmoke',Image.new('RGBA',(16,16)))
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            app = App(Database(Path(directory) / 'smoke.sqlite3'), start_monitor=False)
            from PIL import Image
            app.tabs.select(app.decks_page)
            app.update_idletasks()
            app.decks_page.art=Image.new('RGB',(40,60),'navy')
            app.decks_page.draw_art()
            app.after(500, app.close)
            app.mainloop()
        return
    db = Database(args.database or data_dir() / 'alerts.sqlite3')
    App(db).mainloop()
