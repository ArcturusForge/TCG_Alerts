"""Bounded background image loading and a virtual, keyboard-accessible image gallery."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import hashlib
import math
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk,font as tkfont
from .card_images import load, decode


class ImageService:
    def __init__(self, directory, events, loader=load, ttl=86400, limit=96*1024*1024):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.events=events;self.loader=loader;self.ttl=ttl;self.limit=limit
        self.pool=ThreadPoolExecutor(max_workers=3,thread_name_prefix='artwork')
        self.pending={};self.memory=OrderedDict();self.failures={};self.closed=False
        self.prune()

    @staticmethod
    def key(url,path):
        stamp=''
        if path:
            try:
                s=Path(path).stat();stamp=f'{s.st_mtime_ns}:{s.st_size}'
            except OSError:stamp='missing'
        return hashlib.sha256((url+'\0'+str(path)+'\0'+stamp).encode()).hexdigest()

    def request(self,url,path,callback):
        if self.closed:return
        key=self.key(url,path)
        if key in self.memory:
            image,checked,status=self.memory[key]
            if 0<=time.time()-checked<self.ttl:
                self.memory.move_to_end(key);callback(image,status);return
        if key in self.pending:
            self.pending[key].append(callback);return
        if self.failures.get(key,0)>time.time():
            cached=self.memory.get(key)
            callback(cached[0] if cached else None,'Saved image · refresh unavailable' if cached else 'Image unavailable · retry in a minute');return
        if len(self.pending)>=40:
            callback(None,'Image queue busy · scroll to retry');return
        self.pending[key]=[callback]
        def work():
            cache=self.directory/(key+'.png');image=None;status='';checked=time.time()
            try:
                if cache.exists():
                    try:
                        image=decode(cache.read_bytes())
                        if 0<=time.time()-cache.stat().st_mtime<self.ttl:return image,'Saved image',cache.stat().st_mtime
                    except Exception:cache.unlink(missing_ok=True)
                fresh=self.loader(url,path)
                tmp=cache.with_suffix('.tmp');fresh.save(tmp,format='PNG');tmp.replace(cache)
                return fresh,'Image updated',checked
            except Exception:
                return image,'Saved image · refresh unavailable' if image else 'Image unavailable · text remains available',0
        def done(future):
            if not self.closed:
                try:result=future.result()
                except Exception:result=(None,'Image unavailable',0)
                self.events.put(('visual_image',(key,*result)))
        self.pool.submit(work).add_done_callback(done)

    def receive(self,key,image,status,checked):
        callbacks=self.pending.pop(key,[])
        if not checked:self.failures[key]=time.time()+60
        if image is not None:
            self.memory[key]=(image,checked,status);self.memory.move_to_end(key)
            while len(self.memory)>128:self.memory.popitem(last=False)
        for callback in callbacks:
            callback(image,status)
        self.prune()

    def prune(self):
        files=sorted(self.directory.glob('*.png'),key=lambda p:p.stat().st_mtime,reverse=True)
        total=0
        for p in files:
            try:
                total+=p.stat().st_size
                if total>self.limit:p.unlink(missing_ok=True)
            except OSError:pass

    def close(self):
        self.closed=True;self.pending.clear();self.pool.shutdown(wait=False,cancel_futures=True)


def fit_text(text,width,font,lines=2):
    output=[];line=''
    for word in str(text).split():
        candidate=(line+' '+word).strip()
        if font.measure(candidate)>width and line:
            output.append(line);line=word
        else:line=candidate
    if line:output.append(line)
    if len(output)>lines:
        output=output[:lines];output[-1]+='…'
    for i,line in enumerate(output):
        while line and font.measure(line)>width:
            line=line[:-2]+'…' if len(line)>2 else ''
        output[i]=line
    return '\n'.join(output)


class VisualGrid(ttk.Frame):
    """Only visible tiles allocate Tk images or request remote artwork."""
    def __init__(self,parent,app,on_select,on_open,landscape=False):
        super().__init__(parent);self.app=app;self.on_select=on_select;self.on_open=on_open
        self.landscape=landscape;self.items=[];self.selected=None;self.images={};self.requested=set();self.boxes=[]
        self.generation=0;self.job=None
        self.canvas=tk.Canvas(self,bg='#0d1321',highlightthickness=1,highlightbackground='#203049',highlightcolor='#6ce3b4',takefocus=True)
        scroll=ttk.Scrollbar(self,orient='vertical',command=self.scroll)
        scroll.pack(side='right',fill='y');self.canvas.pack(fill='both',expand=True)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.bind('<Configure>',lambda e:self.schedule())
        self.canvas.bind('<Map>',lambda e:self.schedule())
        self.canvas.bind('<MouseWheel>',self.wheel)
        self.canvas.bind('<Button-4>',lambda e:self.scroll(-3,'units'))
        self.canvas.bind('<Button-5>',lambda e:self.scroll(3,'units'))
        self.canvas.bind('<Button-1>',self.click)
        self.canvas.bind('<Double-1>',lambda e:self.open_selected())
        self.canvas.bind('<Return>',lambda e:self.open_selected())
        for key,delta in (('Left',-1),('Right',1),('Up',-10000),('Down',10000)):
            self.canvas.bind('<'+key+'>',lambda e,d=delta:self.move(d))
        self.title_font=tkfont.Font(root=self.app,family=self.app.font_family,size=10,weight='bold')
        self.caption_font=tkfont.Font(root=self.app,family=self.app.font_family,size=9)
        self.small_font=tkfont.Font(root=self.app,family=self.app.font_family,size=8)
        self.message='No cards yet. Import a deck list or add your first card.'

    def set_items(self,items):
        # Values/prices update independently of image identity.
        previous={str(i['id']):(i.get('image_url',''),i.get('image_path','')) for i in self.items}
        current={str(i['id']):(i.get('image_url',''),i.get('image_path','')) for i in items}
        if current!=previous:
            self.generation+=1;self.images.clear();self.requested.clear()
        self.requested.clear()
        self.items=items
        if self.selected not in current:self.selected=None
        self.schedule()

    def schedule(self):
        if self.job is None and self.winfo_exists():self.job=self.after_idle(self.draw)

    def scroll(self,*args):
        self.canvas.yview(*args);self.schedule()

    def wheel(self,event):
        self.scroll(int(-event.delta/120) or (-1 if event.delta>0 else 1),'units');return 'break'

    def select(self,key,notify=True):
        self.selected=str(key)
        if notify:self.on_select(self.selected)
        self.schedule()

    def click(self,event):
        self.canvas.focus_set();x,y=self.canvas.canvasx(event.x),self.canvas.canvasy(event.y)
        for left,top,right,bottom,key in self.boxes:
            if left<=x<=right and top<=y<=bottom:self.select(key);break

    def open_selected(self):
        if self.selected:self.on_open(self.selected)
        return 'break'

    def move(self,delta):
        if not self.items:return 'break'
        keys=[str(i['id']) for i in self.items];index=keys.index(self.selected) if self.selected in keys else 0
        if abs(delta)==10000:delta=self.columns*(1 if delta>0 else -1)
        index=max(0,min(len(keys)-1,index+delta));self.select(keys[index])
        top=(index//self.columns)*self.tile_h
        if top<self.canvas.canvasy(0) or top+self.tile_h>self.canvas.canvasy(self.canvas.winfo_height()):
            self.canvas.yview_moveto(top/max(self.total_height,1));self.schedule()
        return 'break'

    def draw(self):
        self.job=None;c=self.canvas;c.delete('all');self.boxes=[];self.photos=[]
        width=max(200,c.winfo_width());height=max(100,c.winfo_height())
        self.columns=max(1,width//(290 if self.landscape else 190));tile_w=width/self.columns
        self.tile_h=245 if self.landscape else 292
        self.total_height=max(height,math.ceil(len(self.items)/self.columns)*self.tile_h)
        c.configure(scrollregion=(0,0,width,self.total_height))
        if not self.items:
            c.create_text(width/2,height/2,text=self.message,fill='#95a8c8',width=width-50,font=(self.app.font_family,12));return
        start=max(0,int(c.canvasy(0)//self.tile_h)*self.columns)
        end=min(len(self.items),start+(math.ceil(height/self.tile_h)+2)*self.columns)
        for index in range(start,end):
            item=self.items[index];key=str(item['id']);x=(index%self.columns)*tile_w+6;y=(index//self.columns)*self.tile_h+6
            w=tile_w-12;h=self.tile_h-12
            c.create_rectangle(x,y,x+w,y+h,fill='#1b2c3c',outline='#6ce3b4' if key==self.selected else '#2c4054',width=2 if key==self.selected else 1)
            self.boxes.append((x,y,x+w,y+h,key))
            art_h=112 if self.landscape else 174
            c.create_rectangle(x+8,y+8,x+w-8,y+8+art_h,fill='#142231',outline='')
            image,status=self.images.get(key,(None,'Artwork not linked' if not item.get('image_url') and not item.get('image_path') else 'Loading image…'))
            if image is not None:
                from PIL import ImageTk,Image
                preview=image.copy();preview.thumbnail((int(w)-18,art_h),Image.Resampling.LANCZOS)
                photo=ImageTk.PhotoImage(preview,master=self.app);self.photos.append(photo)
                c.create_image(x+w/2,y+8+art_h/2,image=photo)
            else:
                c.create_text(x+w/2,y+art_h/2,text=item.get('fallback','CARD ART'),fill='#8fabaf',width=w-25,font=(self.app.font_family,11,'bold'))
            c.create_text(x+10,y+art_h+18,text=fit_text(item['title'],w-20,self.title_font),anchor='nw',fill='#e9effa',width=w-20,font=(self.app.font_family,10,'bold'))
            c.create_text(x+10,y+h-53,text='\n'.join(fit_text(line,w-20,self.caption_font,1) for line in item.get('subtitle','').splitlines()[:2]),anchor='nw',fill='#b7d1cb',width=w-20,font=(self.app.font_family,9))
            c.create_text(x+10,y+h-17,text=fit_text(status,w-20,self.small_font,1),anchor='w',fill='#95a8c8',width=w-20,font=(self.app.font_family,8))
            if key not in self.requested and (item.get('image_url') or item.get('image_path')) and c.winfo_ismapped():
                self.requested.add(key);generation=self.generation
                def received(image,status,key=key,generation=generation):
                    if self.winfo_exists() and generation==self.generation:
                        self.images[key]=(image,status);self.schedule()
                self.app.images.request(item.get('image_url',''),item.get('image_path',''),received)
        visible={str(i['id']) for i in self.items[start:end]}
        for key in list(self.images):
            if key not in visible:self.images.pop(key,None);self.requested.discard(key)
