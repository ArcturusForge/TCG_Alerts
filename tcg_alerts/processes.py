"""Launch independent helpers without inheriting a frozen app's temporary runtime."""
import os,sys,subprocess,threading
_lock=threading.RLock()


def spawn(args,**options):
    env=dict(options.pop('env',os.environ));env['PYINSTALLER_RESET_ENVIRONMENT']='1'
    if getattr(sys,'frozen',False):
        if 'LD_LIBRARY_PATH_ORIG' in env:env['LD_LIBRARY_PATH']=env['LD_LIBRARY_PATH_ORIG']
        else:env.pop('LD_LIBRARY_PATH',None)
        env.pop('PYTHONHOME',None);env.pop('PYTHONPATH',None)
    with _lock:
        reset=bool(getattr(sys,'frozen',False) and sys.platform=='win32')
        if reset:
            import ctypes
            set_directory=ctypes.windll.kernel32.SetDllDirectoryW
            set_directory.argtypes=[ctypes.c_wchar_p];set_directory.restype=ctypes.c_int
            set_directory(None)
        try:return subprocess.Popen(args,env=env,**options)
        finally:
            if reset:set_directory(str(sys._MEIPASS))
