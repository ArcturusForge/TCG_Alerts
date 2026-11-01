"""Collector's desk navigation and original, resolution-independent banner art."""
import tkinter as tk
from tkinter import ttk

PAGES = (
    ('Watchlist', 'Your next great find', 'Track products, set a target, and let your collection come to you.'),
    ('Alerts', 'Catch the moment', 'Review price drops and restocks from your watched products.'),
    ('Compare', 'Find your best option', 'Compare matching listings, delivery costs, and price per pack.'),
    ('Decks', 'Build something brilliant', 'Plan your deck, see what you own, and price the cards you still need.'),
    ('Analytics', 'See the bigger picture', 'Explore recorded prices and activity, with the evidence behind each chart.'),
    ('News', 'Around the card table', 'Catch up on publisher announcements and your chosen news feeds.'),
    ('Calendar', 'Something to look forward to', 'Keep upcoming releases and events together in one place.'),
    ('Stores', 'Find your local favourites', 'Explore your store directory and open a store to discover its products.'),
    ('Discover', 'Start your next search', 'Find product links on a store collection page, then choose what to track.'),
    ('Settings & data', 'Make yourself at home', 'Choose notifications, protect your data, and manage the desktop app.'),
)


class CollectorShell:
    def __init__(self, app):
        self.app = app
        outer = ttk.Frame(app, padding=18)
        outer.pack(fill='both', expand=True)
        self.rail = tk.Frame(outer, bg='#111b29', width=186)
        self.rail.pack(side='left', fill='y', padx=(0, 22))
        self.rail.pack_propagate(False)
        tk.Label(self.rail, text='TCG / ALERTS', bg='#111b29', fg='#f4eee1',
                 font=(app.font_family, 17, 'bold'), anchor='w').pack(fill='x', padx=16, pady=(25, 3))
        tk.Label(self.rail, text='THE COLLECTOR’S DESK', bg='#111b29', fg='#a6b8bd',
                 font=(app.font_family, 8), anchor='w').pack(fill='x', padx=16, pady=(0, 25))
        self.buttons = []
        for index, (label, _, _) in enumerate(PAGES):
            if index in (0, 5, 9):
                category = {0:'YOUR COLLECTION', 5:'EXPLORE', 9:'PREFERENCES'}[index]
                tk.Label(self.rail, text=category, bg='#111b29', fg='#869ca7', anchor='w',
                         font=(app.font_family, 8, 'bold')).pack(fill='x', padx=16, pady=(14, 7))
            button = tk.Button(self.rail, text=label, anchor='w', relief='flat', bd=0,
                               bg='#111b29', fg='#c1ced1', activebackground='#314749',
                               activeforeground='#fff6df', cursor='hand2', padx=16, pady=10,
                               font=(app.font_family, 10), takefocus=True, highlightthickness=1,
                               highlightbackground='#111b29', highlightcolor='#d5e5c8',
                               command=lambda i=index: app.tabs.select(i))
            button.pack(fill='x', padx=7, pady=2)
            self.buttons.append(button)
        tk.Label(self.rail, text='PRIVATE DESKTOP\nYour collection. Your pace.', bg='#111b29',
                 fg='#93aaa9', justify='left', anchor='w', font=(app.font_family, 9)).pack(side='bottom', fill='x', padx=16, pady=22)
        self.main = ttk.Frame(outer)
        self.main.pack(side='left', fill='both', expand=True)
        self.banner = tk.Canvas(self.main, height=135, bg='#1b3036', highlightthickness=0)
        self.banner.pack(fill='x', pady=(0, 16))
        self.index = 0
        self.banner.bind('<Configure>', self.draw)
        app.bind('<Configure>',self.resize,add='+')

    def resize(self,event):
        if event.widget is not self.app:return
        height=85 if event.height<820 else 135
        if int(self.banner.cget('height'))!=height:self.banner.configure(height=height)

    def draw(self, event=None):
        c = self.banner
        c.delete('all')
        w = c.winfo_width()
        compact=c.winfo_height()<110
        c.create_rectangle(0,0,w,c.winfo_height(),fill='#1b3036',outline='')
        # Original paper-strip and card motifs echo the reference without shipping borrowed art.
        c.create_polygon(0, 12, w*.75, 0, w*.68, 135, 0, 135, fill='#243e42', outline='')
        c.create_polygon(0, 16, min(w-35, 535), 8, min(w-65, 505), 34, 0, 43, fill='#c7d2bc', outline='')
        c.create_line(0, 45, w*.56, 36, fill='#7b9c91', width=1)
        if w > 850:
            for dx, dy, color in ((-12, -6, '#37565a'), (8, 5, '#527875'), (28, 17, '#92b5a0')):
                x = w-130+dx
                c.create_polygon(x, 12+dy, x+75, 24+dy, x+55, 121+dy, x-20, 109+dy, fill=color, outline='#acc8b2')
                c.create_polygon(x+12, 40+dy, x+45, 46+dy, x+34, 83+dy, x+2, 77+dy, fill='#243e42', outline='')
        _, title, subtitle = PAGES[self.index]
        c.create_text(20, 25, text='YOUR COLLECTION, CONNECTED', anchor='w', fill='#1b3036', font=(self.app.font_family, 9, 'bold'))
        c.create_text(20, 52 if compact else 69, text=title, anchor='w', fill='#f7f1e5', font=(self.app.font_family, 17 if compact else 24, 'bold'))
        c.create_text(20, 74 if compact else 109, text=subtitle, anchor='w', fill='#c7d9d5', font=(self.app.font_family, 9 if compact else 10), width=max(300,w-215))

    def changed(self, event=None):
        self.index = self.app.tabs.index(self.app.tabs.select())
        for i, button in enumerate(self.buttons):
            selected = i == self.index
            button.configure(bg='#c7d2bc' if selected else '#111b29', highlightbackground='#c7d2bc' if selected else '#111b29', fg='#172d31' if selected else '#c1ced1',
                             text=('›  ' if selected else '   ') + PAGES[i][0])
        self.draw()

