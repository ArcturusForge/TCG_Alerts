"""News and analytical desktop views; every plotted point has inspectable evidence."""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import sqlite3
import webbrowser
from .catalog import GAMES
from .analytics import report, timestamp

PANEL, TEXT, MUTED, ACCENT, RED = '#151f32', '#e9effa', '#95a8c8', '#6ce3b4', '#f0949b'


class NewsSources(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title('News sources')
        self.geometry('1000x580')
        self.configure(bg='#0d1321')
        self.table = app.make_table(self, [('name', 'Publisher / source', 190), ('game', 'Game', 100), ('status', 'Health', 200), ('url', 'Source URL', 400)])
        form = ttk.Frame(self, padding=16)
        form.pack(fill='x')
        self.name, self.url, self.game = tk.StringVar(), tk.StringVar(), tk.StringVar(value='Unspecified')
        for label, var, width in [('Name', self.name, 20), ('RSS / Atom HTTPS URL', self.url, 42)]:
            cell = ttk.Frame(form)
            cell.pack(side='left', padx=5)
            ttk.Label(cell, text=label).pack(anchor='w')
            ttk.Entry(cell, textvariable=var, width=width).pack()
        game = ttk.Frame(form)
        game.pack(side='left', padx=5)
        ttk.Label(game, text='Game / custom tag').pack(anchor='w')
        ttk.Combobox(game, textvariable=self.game, values=GAMES, width=18).pack()
        buttons = ttk.Frame(self, padding=16)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Add feed', command=self.add).pack(side='left', padx=5)
        ttk.Button(buttons, text='Pause / resume selected', command=self.toggle).pack(side='left', padx=5)
        ttk.Label(buttons, text='Added feeds are labelled as user sources, not verified official publishers.', style='Muted.TLabel').pack(side='left', padx=10)
        self.refresh()

    def refresh(self):
        self.table.delete(*self.table.get_children())
        self.rows = {str(s['id']): s for s in self.app.db.news_sources()}
        for key, s in self.rows.items():
            status = 'Paused' if not s['enabled'] else s['error'] or ('Checked ' + self.app.local(s['checked']) if s['checked'] else 'Awaiting check')
            self.table.insert('', 'end', iid=key, values=(s['name'], s['game'], status, s['url']))

    def add(self):
        try:
            self.app.db.add_news_source(self.name.get(), self.url.get(), self.game.get())
        except (ValueError, sqlite3.Error) as e:
            messagebox.showerror('Could not add feed', str(e), parent=self)
            return
        self.app.news_monitor.refresh()
        self.refresh()

    def toggle(self):
        selection = self.table.selection()
        if selection:
            s = self.rows[selection[0]]
            self.app.db.set_news_enabled(s['id'], not s['enabled'])
            self.app.news_monitor.refresh()
            self.app.refresh()
            self.refresh()


class NewsPage(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent, padding=16)
        self.app = app
        ttk.Label(self, text='Publisher news & announcements', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(self, text='Official Riftbound and Cyberpunk headlines, plus your RSS/Atom feeds. Game filter applies; store region does not.\nPublication dates are not release dates. Global/unspecified scope is not an Australian availability promise.', style='Muted.TLabel').pack(anchor='w', pady=(5, 10))
        controls = ttk.Frame(self)
        controls.pack(fill='x', pady=8)
        self.topic = tk.StringVar(value='All topics')
        picker = ttk.Combobox(controls, textvariable=self.topic, state='readonly', width=26, values=('All topics', 'Release / announcement', 'Rules', 'Events / play', 'News'))
        picker.pack(side='left')
        picker.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        ttk.Button(controls, text='Refresh due sources', command=app.news_monitor.refresh).pack(side='right')
        ttk.Button(controls, text='Manage sources / add RSS', command=lambda: NewsSources(app)).pack(side='right', padx=10)
        self.table = app.make_table(self, [('date', 'Published', 100), ('game', 'Game', 100), ('title', 'Headline', 500), ('source', 'Publisher / source', 180), ('topic', 'Topic tag', 170)])
        self.table.bind('<<TreeviewSelect>>', lambda e: self.select())
        self.table.bind('<Double-1>', lambda e: self.open())
        bottom = ttk.Frame(self)
        bottom.pack(fill='x', pady=8)
        ttk.Button(bottom, text='Open original story ↗', command=self.open).pack(side='right')
        self.detail = tk.StringVar(value='News is cached locally. First refresh runs while the app is open.')
        ttk.Label(bottom, textvariable=self.detail, style='Muted.TLabel', wraplength=850).pack(side='left', anchor='w')

    def refresh(self):
        selected = self.table.selection()
        self.table.delete(*self.table.get_children())
        self.rows = {}
        for n in self.app.db.news():
            if self.app.game_filter.get() != 'All games' and self.app.game_filter.get() != n['game']:
                continue
            if self.topic.get() != 'All topics' and self.topic.get() != n['topic']:
                continue
            key = str(n['id'])
            self.rows[key] = n
            date = n['published'][:10] if n['published'] else 'Not reported'
            self.table.insert('', 'end', iid=key, values=(date, n['game'], n['title'], n['source_name'], n['topic']))
        for key in selected:
            if self.table.exists(key):
                self.table.selection_set(key)
        sources = self.app.db.news_sources()
        failures = sum(bool(s['error']) for s in sources if s['enabled'])
        self.detail.set(f'{len(self.rows)} cached headlines • {failures} source errors. Check source health in Manage sources. Topic tags use headline keywords.')

    def select(self):
        selection = self.table.selection()
        if selection:
            n = self.rows[selection[0]]
            health = n['error'] or ('last refreshed ' + self.app.local(n['checked']))
            self.detail.set(n['url'] + '\n' + health + ' • publication date shown; release details remain in the original story')

    def open(self):
        if self.table.selection():
            webbrowser.open(self.rows[self.table.selection()[0]]['url'])


class AnalyticsPage(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent, padding=16)
        self.app = app
        self.data = None
        self.watch_map = {}
        self.points = []
        ttk.Label(self, text='Prices & local activity', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(self, text='Scope: country, state and game filters above. Prices belong to one exact listing; currencies are never pooled.\nStore-link opens measure this installation only. Retailer visitors, sales and wider market traffic are unavailable.', style='Muted.TLabel').pack(anchor='w', pady=(5, 10))
        controls = ttk.Frame(self)
        controls.pack(fill='x', pady=8)
        self.metric = tk.StringVar(value='Item price')
        self.period = tk.StringVar(value='30 days')
        self.watch = tk.StringVar()
        self.metric_box = ttk.Combobox(controls, textvariable=self.metric, state='readonly', values=('Item price', 'Checks per UTC day', 'Store-link opens per UTC day'), width=28)
        self.metric_box.pack(side='left', padx=(0, 8))
        self.period_box = ttk.Combobox(controls, textvariable=self.period, state='readonly', values=('7 days', '30 days', '90 days'), width=10)
        self.period_box.pack(side='left', padx=(0, 8))
        self.watch_box = ttk.Combobox(controls, textvariable=self.watch, state='readonly', width=38)
        self.watch_box.pack(side='left')
        for picker in (self.metric_box, self.period_box, self.watch_box):
            picker.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        ttk.Button(controls, text='Inspect plotted data', command=self.evidence).pack(side='right')
        self.summary = tk.StringVar()
        ttk.Label(self, textvariable=self.summary, style='Muted.TLabel', wraplength=1100).pack(anchor='w', pady=8)
        self.canvas = tk.Canvas(self, background=PANEL, highlightthickness=0, height=220)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self.draw())
        self.canvas.bind('<Motion>', self.hover)
        self.hover_text = tk.StringVar(value='Hover over a point or bar for its exact values.')
        ttk.Label(self, textvariable=self.hover_text, style='Muted.TLabel').pack(anchor='w', pady=8)
        ttk.Label(self, text='Evidence: successful listing observations + check attempts and link-open requests recorded by this app.\nActivity collection begins with v0.2. No historical traffic is invented. A 10,000-row cap per series is disclosed when reached.', style='Muted.TLabel').pack(anchor='w')

    def refresh(self):
        watches = self.app.scope()
        self.watch_map = {f"#{w['id']} {w['label'] or w['title'] or w['url']}": w for w in watches}
        labels = list(self.watch_map)
        self.watch_box.configure(values=labels)
        if self.watch.get() not in self.watch_map:
            self.watch.set(labels[0] if labels else '')
        w = self.watch_map.get(self.watch.get())
        watch_id = w['id'] if w else None
        self.watch_box.configure(state='readonly' if self.metric.get() == 'Item price' else 'disabled')
        self.data = report(self.app.db, [w['id'] for w in watches], watch_id, int(self.period.get().split()[0]))
        prices = self.data['prices']
        attempts = sum(d['check_ok'] + d['check_failed'] for d in self.data['daily'])
        ok = sum(d['check_ok'] for d in self.data['daily'])
        opens = sum(d['store_open'] for d in self.data['daily'])
        reliability = f'{ok / attempts:.1%}' if attempts else 'no checks yet'
        text = f'{len(watches)} scoped listings • check success {ok}/{attempts} ({reliability}) • {opens} local link-open requests'
        if prices and self.metric.get() == 'Item price':
            values = [p['price'] for p in prices]
            text += f"\n{w['currency'] or prices[-1]['currency']} item price • low {min(values)/100:,.2f} • last observed {values[-1]/100:,.2f} • {len(values)} observations"
            if len(values) > 1 and values[0] > 0:
                text += f' • first-to-last change {(values[-1]/values[0]-1):+.1%}'
            text += ' (includes sold-out/preorder observations; shipping excluded)'
        if self.data['capped']:
            text += ' • CAPPED: latest 10,000 rows per series only'
        self.summary.set(text)
        self.draw()

    def draw(self):
        self.canvas.delete('all')
        self.points = []
        if not self.data:
            return
        width, height = max(600, self.canvas.winfo_width()), max(180, self.canvas.winfo_height())
        left, right, top, bottom = 75, width - 30, 40, height - 42
        mode = self.metric.get()
        if mode == 'Item price':
            records = self.data['prices']
            if not records:
                self.canvas.create_text(width / 2, height / 2, text='No observations for this listing in the selected window.', fill=MUTED)
                return
            values = [r['price']/100 for r in records]
            xs = [timestamp(r['at']).timestamp() for r in records]
            lo, hi = min(values), max(values)
            pad = max((hi-lo)*.12, max(1, hi*.01))
            ymin, ymax = max(0, lo-pad), hi+pad
            xmin, xmax = min(xs), max(xs)
            if xmin == xmax:
                xmin, xmax = xmin - 60, xmax + 60
            points = []
            for x, value, r in zip(xs, values, records):
                px = left + (x-xmin)/(xmax-xmin)*(right-left)
                py = bottom - (value-ymin)/(ymax-ymin)*(bottom-top)
                points.append((px, py))
                label = f"{r['at']} • {r['currency']} {value:,.2f} • {r['stock']} • {r['source']}"
                self.points.append((px, py, label))
            self.axes(left, right, top, bottom, ymin, ymax, lambda v: f'{v:,.2f}')
            if len(points) > 1:
                self.canvas.create_line(*[v for p in points for v in p], fill=ACCENT, width=2)
            # Preserve every observation in the line and hover index; draw fewer visible dots for large series.
            for px, py in points[::max(1,len(points)//200)]:
                self.canvas.create_oval(px-3, py-3, px+3, py+3, fill=ACCENT, outline='')
            self.canvas.create_text(left, 16, anchor='w', fill=TEXT, text=f"{records[-1]['currency']} • item price • observation time (UTC)")
            first_label, last_label = records[0]['at'][:16], records[-1]['at'][:16]
        else:
            daily = self.data['daily']
            if not daily:
                self.canvas.create_text(width/2, height/2, text='No listings match the selected region/game filters.', fill=MUTED)
                return
            checks = mode == 'Checks per UTC day'
            totals = [d['check_ok']+d['check_failed'] if checks else d['store_open'] for d in daily]
            ymax = max(1, max(totals, default=0))
            self.axes(left, right, top, bottom, 0, ymax, lambda v: f'{v:,.0f}', integer=True)
            step = (right-left)/max(1,len(daily))
            for i, (d, total) in enumerate(zip(daily, totals)):
                x = left + (i+.5)*step
                def ypos(v):
                    return bottom - v/ymax*(bottom-top)
                if checks:
                    self.canvas.create_rectangle(x-step*.35, ypos(d['check_ok']), x+step*.35, bottom, fill=ACCENT, outline='')
                    self.canvas.create_rectangle(x-step*.35, ypos(total), x+step*.35, ypos(d['check_ok']), fill=RED, outline='')
                    label = f"{d['day']} UTC • successful checks {d['check_ok']} • failed checks {d['check_failed']}"
                else:
                    self.canvas.create_rectangle(x-step*.35, ypos(total), x+step*.35, bottom, fill=ACCENT, outline='')
                    label = f"{d['day']} UTC • {total} local store-link open requests (not retailer visitors)"
                self.points.append((x,ypos(total),label))
            self.canvas.create_text(left, 16, anchor='w', fill=TEXT, text='Green: successful checks   Pink: failed checks' if checks else 'Local store-link opens • counts from this installation')
            first_label, last_label = daily[0]['day'], daily[-1]['day']
            if not any(totals):
                self.canvas.create_text((left+right)/2, (top+bottom)/2, fill=MUTED, text='No recorded activity in this window.')
        self.canvas.create_text(left, bottom+20, anchor='w', text=first_label, fill=MUTED)
        self.canvas.create_text(right, bottom+20, anchor='e', text=last_label, fill=MUTED)

    def axes(self, left, right, top, bottom, lo, hi, formatter, integer=False):
        steps = min(4, int(hi)) if integer else 4
        steps = max(1, steps)
        for i in range(steps+1):
            y = top+(bottom-top)*i/steps
            value = hi-(hi-lo)*i/steps
            self.canvas.create_line(left,y,right,y,fill='#26354b')
            self.canvas.create_text(left-10,y,anchor='e',text=formatter(value),fill=MUTED)

    def hover(self, event):
        if self.points:
            point = min(self.points, key=lambda p: abs(p[0]-event.x))
            self.hover_text.set(point[2])

    def evidence(self):
        if not self.data:
            return
        window = tk.Toplevel(self.app)
        window.title('Analytics evidence • current filters')
        window.geometry('1100x600')
        window.configure(bg='#0d1321')
        ttk.Label(window, text=f"Window: {self.data['since'].isoformat()} to {self.data['until'].isoformat()}\nActivity: current tagged listings in country/state/game scope. Prices: selected exact listing only. Deleted-watch activity is excluded.", style='Muted.TLabel', padding=14).pack(anchor='w')
        if self.metric.get() == 'Item price':
            table = self.app.make_table(window, [('at','Observation (UTC)',220),('price','Item price',100),('currency','Currency',80),('stock','Availability',130),('source','Adapter',160)])
            for p in self.data['prices']:
                table.insert('', 'end', values=(p['at'], f"{p['price']/100:.2f}",p['currency'],p['stock'],p['source']))
        else:
            table = self.app.make_table(window, [('at','Event (UTC)',220),('watch','Watch ID',80),('kind','Event type',150),('detail','Detail',500)])
            for e in self.data['activity']:
                table.insert('', 'end', values=(e['at'],e['watch_id'],e['kind'],e['detail']))
