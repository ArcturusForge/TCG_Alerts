import threading
import tkinter as tk
from tkinter import ttk


def show(app):
    window=tk.Toplevel(app);window.title('Updates and browser helper');window.geometry('850x580');window.configure(bg='#0d1321')
    ttk.Label(window,text='Keep your collector’s desk current',style='Heading.TLabel',padding=18).pack(anchor='w')
    ttk.Label(window,text='Stable GitHub releases only. Downloads are checked before installation.\nApp updates apply after closing the packaged Windows app; plugin code reloads on restart.',style='Muted.TLabel',padding=(18,0),wraplength=790).pack(anchor='w')
    body=ttk.Frame(window,padding=18);body.pack(fill='both',expand=True)
    for key,label in [('auto_updates','Automatically check/download app updates (every six hours)'),('plugin_auto_updates','Automatically update installed providers with a pinned GitHub release source'),('browser_helper_enabled','Install/use the browser helper when a public product page is blocked')]:
        variable=tk.BooleanVar(value=app.db.setting(key,True))
        def save(key=key,variable=variable):
            app.db.set_setting(key,variable.get())
            app.monitor.client.browser_helper=app.browser_helper if app.db.setting('browser_helper_enabled',True) else None
        ttk.Checkbutton(body,text=label,variable=variable,command=save).pack(anchor='w',pady=9)
    ttk.Label(body,text='Browser helper: FlareSolverr, downloaded from its official GitHub releases (roughly 250–400 MB).\nIt runs on a private loopback port and closes with this app. It cannot guarantee access to every store.\n\nPrivate repository updates require the environment variable TCG_ALERTS_GITHUB_TOKEN with read access.\nNo GitHub credentials are shipped with this application.',style='Muted.TLabel',wraplength=790).pack(anchor='w',pady=15)
    ttk.Label(body,textvariable=app.update_status,style='Muted.TLabel',wraplength=790).pack(anchor='w',pady=12)
    buttons=ttk.Frame(body);buttons.pack(fill='x',pady=12)
    ttk.Button(buttons,text='Check updates now',command=app.updates.check).pack(side='left')
    def helper():
        def run():
            try:app.browser_helper.ensure(update=True);text='Browser helper installed and ready.'
            except Exception as e:text='Browser helper: '+str(e)
            app.monitor.events.put(('update_status',text))
        threading.Thread(target=run,daemon=True).start()
    ttk.Button(buttons,text='Install/update browser helper',command=helper).pack(side='left',padx=8)
    ttk.Button(buttons,text='Restart into downloaded update',command=app.apply_update).pack(side='left')
    return window
