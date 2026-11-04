"""Native Windows tray and Linux desktop notifications.

OS callbacks only enqueue commands for the GUI thread.
"""
import shutil
import subprocess
import sys
import threading

class Desktop:
    def __init__(self,events):self.events=events;self.icon=None;self.ready=threading.Event();self.error=''
    def start(self):
        if self.icon:return
        if sys.platform!='win32':
            self.error='' if shutil.which('notify-send') else 'Install libnotify (notify-send) for desktop notifications; in-app alerts remain active.'
            return
        try:
            import pystray
            from PIL import Image,ImageDraw
            image=Image.new('RGBA',(64,64),(13,19,33,255));draw=ImageDraw.Draw(image)
            draw.rounded_rectangle((12,8,50,55),radius=8,outline=(108,227,180),width=4)
            draw.line((23,22,40,22,23,40,40,40),fill=(108,227,180),width=4)
            def callback(action):return lambda icon,item:self.events.put(('desktop_action',action))
            menu=pystray.Menu(pystray.MenuItem('Show TCG Alerts',callback('show'),default=True),pystray.MenuItem('Check due watches',callback('check')),pystray.MenuItem('Exit',callback('exit')))
            self.icon=pystray.Icon('TCGAlerts',image,'TCG Alerts',menu)
            def setup(icon):
                try:icon.visible=True;self.ready.set()
                except Exception as e:self.error='Could not show tray icon: '+str(e)
            self.icon.run_detached(setup)
        except Exception as e:self.error='Tray unavailable: '+str(e);self.icon=None
    def available(self):return bool(self.icon and self.ready.is_set() and self.icon.visible)
    def notify(self,message):
        if sys.platform!='win32':return self.notify_linux(message)
        if not self.available():return False
        try:self.icon.notify(message[:240],'TCG Alerts');return True
        except Exception as e:self.error='Notification failed: '+str(e);return False
    def stop(self):
        if self.icon:self.icon.stop();self.icon=None
        self.ready.clear()

    def notify_linux(self,message):
        exe=shutil.which('notify-send')
        if not exe:
            self.error='Install libnotify (notify-send) for desktop notifications; in-app alerts remain active.';return False
        try:
            subprocess.Popen([exe,'--app-name=TCG Alerts','TCG Alerts',message[:240]],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return True
        except OSError as e:
            self.error='Notification failed: '+str(e);return False
