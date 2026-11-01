"""First-use guide and non-destructive backup opening for source and packaged builds."""
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import ttk,filedialog,messagebox


def restore_copy(source,directory):
    source=Path(source).resolve();directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    handle=tempfile.NamedTemporaryFile(prefix='restored_',suffix='.sqlite3',dir=directory,delete=False);destination=Path(handle.name);handle.close()
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as old,closing(sqlite3.connect(destination)) as new:
            if old.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Backup integrity check failed.')
            tables={row[0] for row in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'watches','observations','alerts'}<=tables:raise ValueError('This file is not a TCG Alerts backup.')
            if old.execute('PRAGMA user_version').fetchone()[0]>5:raise ValueError('This backup needs a newer TCG Alerts version.')
            old.backup(new)
        from .core import Database
        Database(destination) # Validate/migrate the copy; never modify the supplied backup.
        return destination
    except Exception:
        for p in (destination,Path(str(destination)+'-wal'),Path(str(destination)+'-shm')):p.unlink(missing_ok=True)
        raise


def open_backup(app):
    source=filedialog.askopenfilename(parent=app,title='Open a backup as a separate copy',filetypes=[('SQLite backup','*.sqlite3 *.db'),('All files','*')])
    if not source:return
    try:
        destination=restore_copy(source,app.db.path.parent/'restored_backups')
        args=[sys.executable]
        if not getattr(sys,'frozen',False):args.append(str(Path(__file__).resolve().parents[1]/'run.py'))
        subprocess.Popen([*args,'--database',str(destination)])
        app.status.set('Opened a separate restored copy. This window and your current database remain unchanged.')
    except (OSError,sqlite3.Error,ValueError) as e:messagebox.showerror('Could not open backup',str(e),parent=app)


def guide(app):
    window=tk.Toplevel(app);window.title('Welcome to your collector’s desk');window.geometry('760x560');window.configure(bg='#0d1321')
    ttk.Label(window,text='Make your first great find.',style='Heading.TLabel',padding=20).pack(anchor='w')
    ttk.Label(window,text='Start with a product you want, or a deck you love. Everything stays on this PC.',style='Muted.TLabel',padding=(20,0)).pack(anchor='w')
    steps=[('01  Find a product','Paste an exact store product URL. Choose the variant, game and store region.',lambda:app.add()),
           ('02  Build your deck','Create a deck, import a list, then choose artwork and link exact singles listings.',lambda:app.tabs.select(app.decks_page)),
           ('03  Follow the evidence','Explore recorded price charts and check sources. Monitoring runs while the PC and app are awake.',lambda:app.tabs.select(app.analytics_page))]
    for title,detail,action in steps:
        cell=ttk.Frame(window,padding=12,style='Card.TFrame');cell.pack(fill='x',padx=20,pady=10)
        ttk.Label(cell,text=title,style='Card.TLabel',font=(app.font_family,13,'bold')).pack(anchor='w')
        ttk.Label(cell,text=detail,style='Card.TLabel',wraplength=650).pack(anchor='w',pady=6)
        def go(action=action):window.destroy();action()
        ttk.Button(cell,text='Get started',command=go).pack(anchor='e')
    ttk.Button(window,text='Explore on my own',command=window.destroy).pack(anchor='e',padx=20,pady=12)
    window.bind('<Escape>',lambda e:window.destroy());return window
