"""GitHub release downloads, checked archives and atomic version directories."""
from .tls import https_handler
from contextlib import closing
import hashlib,json,os,re,shutil,stat,tarfile,tempfile,threading,time,zipfile
from pathlib import Path,PurePosixPath
from urllib import request,error
from urllib.parse import urlsplit

APP_REPO='ArcturusForge/TCG_Alerts'
HELPER_REPO='FlareSolverr/FlareSolverr'


def version(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',str(value))
    if not match:raise ValueError('Only stable major.minor.patch releases can auto-update.')
    return tuple(map(int,match.groups()))


def repo_name(value):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',str(value)):raise ValueError('Use a GitHub owner/repository name.')
    return value


class ReleaseRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if urlsplit(newurl).scheme!='https':raise ValueError('Update redirects must use HTTPS.')
        next_request=super().redirect_request(req,fp,code,msg,headers,newurl)
        if next_request and urlsplit(newurl).netloc!=urlsplit(req.full_url).netloc:next_request.remove_header('Authorization')
        return next_request


class Releases:
    def __init__(self,token=None):
        self.token=os.environ.get('TCG_ALERTS_GITHUB_TOKEN','') if token is None else token
        self.opener=request.build_opener(https_handler(), ReleaseRedirect())
    def open(self,url,binary=False):
        p=urlsplit(url)
        if p.scheme!='https' or p.hostname not in ('api.github.com','github.com'):raise ValueError('Release requests must start on GitHub.')
        headers={'User-Agent':'TCGAlerts-updater/0.6','Accept':'application/octet-stream' if binary else 'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
        if self.token and p.hostname=='api.github.com':headers['Authorization']='Bearer '+self.token
        return self.opener.open(request.Request(url,headers=headers),timeout=30)
    def latest(self,repo):
        try:
            with self.open('https://api.github.com/repos/'+repo_name(repo)+'/releases/latest') as response:
                data=response.read(2*1024*1024+1)
                if len(data)>2*1024*1024:raise ValueError('Release metadata exceeds limit.')
                result=json.loads(data)
        except error.HTTPError as e:
            if e.code==403 and e.headers and e.headers.get('X-RateLimit-Remaining')=='0':raise ValueError('GitHub API rate limit reached; try later or configure TCG_ALERTS_GITHUB_TOKEN for authenticated checks.') from None
            if e.code==404:raise ValueError('No visible stable release. Private repositories need TCG_ALERTS_GITHUB_TOKEN with repository read access.') from None
            raise ValueError('GitHub release check failed (HTTP '+str(e.code)+').') from None
        if result.get('draft') or result.get('prerelease'):raise ValueError('Only published stable releases can auto-update.')
        version(result.get('tag_name'));return result
    def download(self,repo,asset,destination,limit=600*1024*1024):
        digest=asset.get('digest','') or ''
        if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}',digest):raise ValueError('Release asset has no GitHub SHA-256 digest; automatic installation paused.')
        if not isinstance(asset.get('size'),int) or not 0<asset['size']<=limit:raise ValueError('Release asset is empty or too large.')
        expected='https://api.github.com/repos/'+repo_name(repo)+'/releases/assets/'+str(asset.get('id'))
        if asset.get('url')!=expected:raise ValueError('Release asset belongs to a different repository.')
        destination=Path(destination);temporary=destination.with_suffix('.partial');count=0;checksum=hashlib.sha256()
        try:
            with self.open(expected,binary=True) as response,temporary.open('wb') as output:
                while True:
                    block=response.read(1024*1024)
                    if not block:break
                    count+=len(block)
                    if count>limit or count>asset['size']:raise ValueError('Release download exceeds its declared size.')
                    checksum.update(block);output.write(block)
            if count!=asset['size'] or checksum.hexdigest().lower()!=digest[7:].lower():raise ValueError('Release download checksum/size mismatch.')
            temporary.replace(destination);return destination
        finally:temporary.unlink(missing_ok=True)


def extract(archive,destination,max_size=1500*1024*1024):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True);total=0;count=0;names=set()
    def checked(name,size):
        nonlocal total,count
        path=PurePosixPath(name.replace('\\','/'));count+=1;total+=size
        if path.is_absolute() or '..' in path.parts or any(':' in p for p in path.parts) or not path.parts:raise ValueError('Unsafe archive path.')
        if count>15000 or total>max_size:raise ValueError('Archive extraction limit exceeded.')
        key=str(path).casefold()
        if key in names:raise ValueError('Duplicate archive path.')
        names.add(key);return destination.joinpath(*path.parts)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for entry in source.infolist():
                target=checked(entry.filename,entry.file_size)
                if stat.S_ISLNK(entry.external_attr>>16):raise ValueError('Archive symlinks are not accepted.')
                if entry.is_dir():target.mkdir(parents=True,exist_ok=True);continue
                target.parent.mkdir(parents=True,exist_ok=True)
                with source.open(entry) as old,target.open('wb') as new:shutil.copyfileobj(old,new)
                if os.name!='nt':target.chmod((entry.external_attr>>16)&0o777 or 0o644)
    else:
        with tarfile.open(archive) as source:
            for entry in source:
                target=checked(entry.name,entry.size)
                if entry.isdir():target.mkdir(parents=True,exist_ok=True);continue
                if not entry.isfile():raise ValueError('Archive links/devices are not accepted.')
                target.parent.mkdir(parents=True,exist_ok=True)
                with source.extractfile(entry) as old,target.open('wb') as new:shutil.copyfileobj(old,new)
                target.chmod(entry.mode&0o777)
    return destination


def select_asset(release,name):
    matches=[a for a in release.get('assets',[]) if a.get('name')==name]
    if len(matches)!=1:raise ValueError('This release does not contain exactly one '+name)
    return matches[0]


def install_version(client,repo,release,asset,root,validator=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);tag=release['tag_name'];version(tag)
    target=root/tag
    if target.exists():return target
    with tempfile.TemporaryDirectory(prefix='.stage-',dir=root) as temporary:
        temporary=Path(temporary);archive=client.download(repo,asset,temporary/'package.bin');stage=extract(archive,temporary/'unpacked')
        if validator:validator(stage)
        (stage/'release.json').write_text(json.dumps(dict(repo=repo,version=tag,asset=asset['name'],digest=asset['digest'])))
        stage.rename(target)
    return target


def atomic_json(path,value):
    path=Path(path);temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2));temporary.replace(path)


class UpdateCoordinator:
    def __init__(self,app):
        self.app=app;self.root=app.db.path.parent/'updates';self.root.mkdir(exist_ok=True);self.busy=False;self.check_lock=threading.Lock();self.stop=threading.Event();self.pending=None
        self.status='Automatic checks run every six hours while the app is open.'
        try:
            from . import __version__
            saved=json.loads((self.root/'pending.json').read_text(encoding='utf-8'))
            if version(saved['version'])>version(__version__) and Path(saved['executable']).is_file():self.pending=saved
        except (OSError,ValueError,KeyError,TypeError):pass
    def start(self):
        def loop():
            while not self.stop.is_set():
                if any(self.app.db.setting(key,True) for key in ('auto_updates','plugin_auto_updates','browser_helper_enabled')):self.check(app_updates=self.app.db.setting('auto_updates',True))
                self.stop.wait(21600)
        threading.Thread(target=loop,daemon=True,name='release-checks').start()
    def close(self):self.stop.set()
    def check(self,app_updates=True):
        if not self.check_lock.acquire(blocking=False):return
        self.busy=True
        def perform():
            messages=[]
            try:
                from . import __version__
                client=Releases();release=client.latest(APP_REPO) if app_updates else None
                if release and version(release['tag_name'])>version(__version__):
                    import sys
                    asset_name='TCGAlerts-Windows.zip' if sys.platform=='win32' else 'TCGAlerts-Linux.zip'
                    name='TCGAlerts.exe' if sys.platform=='win32' else 'TCGAlerts'
                    def validate(folder):
                        if len([p for p in folder.rglob(name) if p.is_file()])!=1:raise ValueError('App package must contain one executable.')
                    folder=install_version(client,APP_REPO,release,select_asset(release,asset_name),self.root/'app',validate)
                    pending=dict(version=release['tag_name'],executable=str(next(folder.rglob(name))))
                    atomic_json(self.root/'pending.json',pending);self.app.monitor.events.put(('update_ready',pending));messages.append('App update downloaded: '+release['tag_name'])
                elif release:messages.append('App is up to date.')
            except Exception as e:messages.append('App: '+str(e))
            try:messages.extend(self.update_plugins())
            except Exception as e:messages.append('Plugins: '+str(e))
            if self.app.db.setting('browser_helper_enabled',True):
                try:
                    from .browser_helper import BrowserHelper
                    if (self.app.db.path.parent/'browser_helper'/'current.json').exists():
                        self.app.browser_helper.ensure(update=True);messages.append('Browser helper checked.')
                except Exception as e:messages.append('Browser helper: '+str(e))
            self.app.monitor.events.put(('update_status',' '.join(messages)))
        def worker():
            try:perform()
            except Exception as e:self.app.monitor.events.put(('update_status','Update check interrupted: '+str(e)))
            finally:self.busy=False;self.check_lock.release()
        threading.Thread(target=worker,daemon=True,name='download-updates').start()
    def update_plugins(self):
        messages=[]
        for record in tuple(self.app.plugins.entries):
            setting=record.get('update')
            if not setting or not self.app.db.setting('plugin_auto_updates',True):continue
            try:
                repo=repo_name(setting['repository']);release=Releases().latest(repo)
                rejected=self.app.db.setting('failed_plugin_updates',{}).get(record['id'])
                if rejected and version(rejected)==version(release['tag_name']):
                    messages.append(record['name']+': this version previously failed and was rolled back.');continue
                installed=json.loads(Path(record['path']).read_text(encoding='utf-8'))
                if version(release['tag_name'])<=version(installed.get('version','0.0.0')):continue
                from .plugins import validate_manifest
                def validate(folder):
                    manifests=list(folder.rglob('plugin.json'))
                    if len(manifests)!=1:raise ValueError('Plugin package needs one manifest.')
                    m=validate_manifest(json.loads(manifests[0].read_text(encoding='utf-8')))
                    if m['id']!=record['id'] or version(m.get('version',''))!=version(release['tag_name']):raise ValueError('Plugin id/version differs from installed provider/release.')
                    if m.get('update')!=setting:raise ValueError('Plugin cannot silently change its update source.')
                    # Keep capability/host/game changes explicit rather than granting new permissions during an update.
                    for key in ('kind','games','capabilities','hosts'):
                        if m.get(key)!=record.get(key):raise ValueError('Plugin scope changed; install this version manually.')
                folder=install_version(Releases(),repo,release,select_asset(release,setting['asset']),self.root/('plugin-'+record['id']),validate)
                source=next(folder.rglob('plugin.json')).parent;target=Path(record['path']).parent
                backup=target.with_name(target.name+'.previous');stage=target.with_name(target.name+'.updating')
                if stage.exists():shutil.rmtree(stage)
                shutil.copytree(source,stage)
                if (target/'data').exists():shutil.copytree(target/'data',stage/'data',dirs_exist_ok=True)
                if backup.exists():shutil.rmtree(backup)
                target.rename(backup)
                try:stage.rename(target)
                except Exception:backup.rename(target);raise
                messages.append(record['name']+' updated; active code reloads on restart.')
            except Exception as e:messages.append(record.get('name','Plugin')+': '+str(e))
        return messages


def schedule_windows_update(pending,target,process_id,directory,database,restart=True):
    """An external PowerShell process replaces the closed executable, retaining rollback."""
    import subprocess
    directory=Path(directory);directory.mkdir(exist_ok=True);source=Path(pending['executable']).resolve();target=Path(target).resolve()
    if not source.is_file() or source==target:raise ValueError('No distinct downloaded app executable is ready.')
    config=dict(source=str(source),target=str(target),pid=process_id,database=str(database),restart=restart,sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    config_path=directory/'apply-update.json';atomic_json(config_path,config)
    script=directory/'apply-update.ps1'
    script.write_text(r'''param([string]$ConfigPath)
$ErrorActionPreference = 'Stop'
$c = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$backup = $c.target + '.previous'
$log = Join-Path (Split-Path $ConfigPath) 'apply-result.txt'
$swapped = $false
try {
    $until = (Get-Date).AddSeconds(120)
    while (Get-Process -Id $c.pid -ErrorAction SilentlyContinue) {
        if ((Get-Date) -gt $until) { throw 'App did not exit; update remains staged.' }
        Start-Sleep -Milliseconds 300
    }
    $stream = [System.IO.File]::OpenRead($c.source)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try { $digest = [System.BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLower() }
    finally { $stream.Dispose(); $hasher.Dispose() }
    if ($digest -ne $c.sha256) { throw 'Staged executable changed.' }
    $probe = Start-Process -FilePath $c.source -ArgumentList '--smoke-test' -PassThru
    if (-not $probe.WaitForExit(30000)) { $probe.Kill(); throw 'New app launch check timed out.' }
    if ($probe.ExitCode -ne 0) { throw 'New app launch check failed.' }
    Copy-Item -LiteralPath $c.target -Destination $backup -Force
    $localStage = $c.target + '.updating'
    Copy-Item -LiteralPath $c.source -Destination $localStage -Force
    $until = (Get-Date).AddSeconds(30)
    while ($true) {
        try { [System.IO.File]::Replace($localStage, $c.target, [NullString]::Value); break }
        catch {
            if ((Get-Date) -gt $until) { throw }
            Start-Sleep -Milliseconds 300
        }
    }
    $swapped = $true
    if ($c.restart) { Start-Process -FilePath $c.target -ArgumentList @('--database', ('"' + $c.database + '"')) }
    'Updated successfully. Previous executable: ' + $backup | Set-Content -LiteralPath $log
    Remove-Item -LiteralPath (Join-Path (Split-Path $ConfigPath) 'pending.json') -ErrorAction SilentlyContinue
} catch {
    if ($swapped -and (Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $backup -Destination $c.target -Force }
    ('Update not applied: ' + $_.Exception.Message) | Set-Content -LiteralPath $log
}
''',encoding='utf-8')
    from .processes import spawn
    return spawn(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),'-ConfigPath',str(config_path)],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
