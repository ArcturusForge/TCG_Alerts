"""Deck planning charts calculated from the same price-evidence report as the table."""
from collections import Counter
import tkinter as tk
from tkinter import ttk


def breakdown(report):
    sections=Counter();costs=[];unpriced=0
    for row in report['lines']:
        sections[row['section']]+=row['quantity']
        if row['reference_line'] is None:unpriced+=row['quantity']
        else:costs.append((row['name'],row['reference_line'],row['reference_basis']))
    return dict(sections=list(sections.items()),costs=sorted(costs,key=lambda r:r[1],reverse=True)[:8],unpriced=unpriced)


def show(page):
    if not page.current:return
    deck_id=page.current['id'];window=tk.Toplevel(page.app);window.title('Deck overview');window.geometry('980x680');window.configure(bg='#0d1321')
    ttk.Label(window,text='Deck at a glance',style='Heading.TLabel',padding=14).pack(anchor='w')
    status=tk.StringVar();ttk.Label(window,textvariable=status,style='Muted.TLabel',wraplength=900,padding=14).pack(anchor='w')
    canvas=tk.Canvas(window,bg='#151f32',highlightthickness=0);canvas.pack(fill='both',expand=True,padx=14,pady=8)
    points=[]
    def draw(event=None):
        canvas.delete('all');points.clear()
        if not page.store.deck(deck_id):return
        report=page.store.report(deck_id);data=breakdown(report);s=report['summary'];currency=report['deck']['currency']
        status.set(f"{report['deck']['name']} · {s['required']} required · {s['missing']} missing · {s['reference_copies']}/{s['required']} copies have a reference price.\nReference subtotals exclude unpriced copies. Ownership is a per-deck plan; prices are not verified sale values.")
        width=max(500,canvas.winfo_width());height=max(280,canvas.winfo_height());left=24;right=width-24
        canvas.create_text(left,24,anchor='w',text='COLLECTION PROGRESS',fill='#e9effa',font=(page.app.font_family,11,'bold'))
        canvas.create_rectangle(left,48,right,70,fill='#304253',outline='')
        fraction=s['owned']/max(1,s['required'])
        if fraction:canvas.create_rectangle(left,48,left+(right-left)*fraction,70,fill='#6ce3b4',outline='')
        canvas.create_text(left,86,anchor='w',text=f"{s['owned']} owned / {s['missing']} missing",fill='#b7d1cb')
        canvas.create_text(left,125,anchor='w',text='LARGEST PRICED LINES · '+currency,fill='#e9effa',font=(page.app.font_family,11,'bold'))
        maxcost=max((r[1] for r in data['costs']),default=1) or 1
        rowh=min(31,max(18,(height-200)/max(8,len(data['costs']))))
        for i,(name,cost,basis) in enumerate(data['costs']):
            y=155+i*rowh;bar_start=width*.34;bar_end=width*.69
            canvas.create_text(left,y,anchor='w',text=name[:33],fill='#e9effa',width=width*.29)
            canvas.create_rectangle(bar_start,y-7,bar_start+(bar_end-bar_start)*cost/maxcost,y+7,fill='#87b7cb',outline='')
            canvas.create_text(width*.73,y,anchor='w',text=f'{cost/100:,.2f}',fill='#e9effa')
            points.append((y,name+' · '+basis+f' · {currency} {cost/100:,.2f}'))
        if not data['costs']:canvas.create_text(left,158,anchor='w',text='Add reference prices or link exact singles listings to see a cost breakdown.',fill='#95a8c8')
        label='Sections: '+ ' · '.join(f'{k} {v}' for k,v in data['sections'])
        canvas.create_text(left,height-35,anchor='w',text=label or 'No cards yet',fill='#b7d1cb',width=width-48)
    hover=tk.StringVar(value='Hover a cost bar to inspect its reference source.');ttk.Label(window,textvariable=hover,style='Muted.TLabel',padding=14,wraplength=900).pack(anchor='w')
    def motion(event):
        nearby=min(points,key=lambda p:abs(p[0]-event.y),default=None)
        hover.set(nearby[1] if nearby and abs(nearby[0]-event.y)<16 else 'Hover a cost bar to inspect its reference source.')
    canvas.bind('<Configure>',draw);canvas.bind('<Motion>',motion)
    ttk.Button(window,text='Refresh from current deck data',command=draw).pack(anchor='e',padx=14,pady=8)
    draw();return window
