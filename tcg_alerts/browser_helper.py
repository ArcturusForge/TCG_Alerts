"""On-demand, loopback-only FlareSolverr sidecar from checked GitHub releases."""
import json,os,platform,socket,subprocess,sys,threading,time
from pathlib import Path
from urllib import request
from urllib.parse import urlsplit
from .updates import Releases,HELPER_REPO,select_asset,install_version,atomic_json
from .sources import validate_url,LIMIT
from .processes import spawn


def challenge(text):
    sample=text[:200000].casefold()
    return any(marker in sample for marker in ('cf-chl-','challenge-platform','just a moment...','verify you are human','ddos-guard'))


class BrowserHelper:
    def __init__(self,directory,status=lambda text:None):
        self.root=Path(directory);self.root.mkdir(parents=True,exist_ok=True);self.status=status;self.lock=threading.RLock()
        self.process=None;self.port=None;self.active=None;self.closed=False
    def install(self):
        with self.lock:
            machine=platform.machine().lower()
            if machine not in ('amd64','x86_64'):raise ValueError('Automatic browser-helper binaries currently require Windows/Linux x64.')
            if sys.platform not in ('win32','linux'):raise ValueError('This OS needs an externally managed browser helper.')
            self.status('Checking browser helper release…')
            release=Releases().latest(HELPER_REPO)
            name='flaresolverr_windows_x64.zip' if sys.platform=='win32' else 'flaresolverr_linux_x64.tar.gz'
            binary='flaresolverr.exe' if sys.platform=='win32' else 'flaresolverr'
            def validate(folder):
                if len([p for p in folder.rglob(binary) if p.is_file()])!=1:raise ValueError('Helper archive is missing its executable.')
            self.status('Preparing browser helper (first download is roughly 250–400 MB)…')
            folder=install_version(Releases(),HELPER_REPO,release,select_asset(release,name),self.root/'versions',validate)
            return folder
    def ensure(self,update=False):
        with self.lock:
            if self.process and self.process.poll() is None and not update:return
            previous=None;pointer=self.root/'current.json'
            if pointer.exists():
                try:previous=json.loads(pointer.read_text())
                except (ValueError,OSError):pass
            folder=self.install() if update or not previous else Path(previous['folder'])
            if self.process and self.process.poll() is None and self.active==str(folder):return
            if self.closed:raise ValueError('App is closing; helper installation remains saved.')
            binary='flaresolverr.exe' if sys.platform=='win32' else 'flaresolverr'
            binaries=[p for p in folder.rglob(binary) if p.is_file()]
            if len(binaries)!=1:raise ValueError('Browser helper is incomplete; install/update it again.')
            with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            env=dict(os.environ,HOST='127.0.0.1',PORT=str(port),LOG_LEVEL='error',LOG_HTML='false',TEST_URL='https://example.com/',PYINSTALLER_RESET_ENVIRONMENT='1')
            env.pop('TCG_ALERTS_GITHUB_TOKEN',None)
            process=spawn([str(binaries[0])],cwd=binaries[0].parent,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),start_new_session=sys.platform!='win32')
            try:
                deadline=time.monotonic()+45
                opener=request.build_opener(request.ProxyHandler({}))
                while time.monotonic()<deadline:
                    if self.closed:raise ValueError('App is closing.')
                    if process.poll() is not None:raise ValueError('Browser helper exited; its browser or OS dependencies may be unavailable.')
                    try:
                        with opener.open(f'http://127.0.0.1:{port}/',timeout=1) as response:
                            info=json.loads(response.read(8192))
                            if response.status==200 and info.get('version'):break
                    except Exception:time.sleep(.2)
                else:raise ValueError('Browser helper did not become ready. Previous installation retained.')
                old=self.process;self.process=process;self.port=port;self.active=str(folder)
                atomic_json(pointer,dict(folder=str(folder),previous=previous.get('folder') if previous else None))
                if old:self._stop(old)
                keep={str(folder),previous.get('folder') if previous else None}
                for old_folder in (self.root/'versions').iterdir():
                    if old_folder.is_dir() and str(old_folder) not in keep and not old_folder.name.startswith('.'):
                        import shutil
                        try:shutil.rmtree(old_folder)
                        except OSError:pass
                self.status('Browser helper ready on this PC.')
            except Exception:self._stop(process);raise
    def solve(self,url):
        url=validate_url(url)
        with self.lock:
            self.ensure();self.status('Browser helper is rendering a blocked public page…')
            body=json.dumps(dict(cmd='request.get',url=url,maxTimeout=45000,disableMedia=True)).encode()
            opener=request.build_opener(request.ProxyHandler({}))
            req=request.Request(f'http://127.0.0.1:{self.port}/v1',data=body,headers={'Content-Type':'application/json'})
            with opener.open(req,timeout=50) as response:
                data=response.read(6*1024*1024+1)
                if len(data)>6*1024*1024:raise ValueError('Browser helper response exceeds limit.')
                result=json.loads(data)
            solution=result.get('solution') or {};final=validate_url(solution.get('url',url));text=solution.get('response','')
            if result.get('status')!='ok' or solution.get('status')!=200:raise ValueError('Browser helper could not open this page; last good observation retained.')
            if urlsplit(final).netloc!=urlsplit(url).netloc:raise ValueError('Browser helper returned a different storefront.')
            if not isinstance(text,str) or len(text.encode())>LIMIT or challenge(text):raise ValueError('Browser helper returned a challenge or oversized page, not product evidence.')
            return text
    @staticmethod
    def _stop(process):
        if process.poll() is None:
            try:
                if sys.platform=='win32':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
                else:
                    import signal
                    os.killpg(process.pid,signal.SIGTERM)
            except (OSError,subprocess.TimeoutExpired):process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill()
    def close(self):
        self.closed=True
        if self.process:self._stop(self.process)
