"""Windows CI: exercise real staged executable verification and replacement without launching monitoring."""
import sys,tempfile,shutil,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tcg_alerts.updates import schedule_windows_update
with tempfile.TemporaryDirectory(prefix='TCG update check ') as directory:
    root=Path(directory);source=root/'downloaded.exe';target=root/'installed.exe'
    shutil.copy2('dist/TCGAlerts.exe',source);shutil.copy2(source,target)
    process=schedule_windows_update(dict(executable=str(source)),target,2147483647,root,root/'db.sqlite3',restart=False)
    process.wait(timeout=55)
    result=(root/'apply-result.txt').read_text()
    if 'Updated successfully' not in result:raise SystemExit(result)
    if not Path(str(target)+'.previous').is_file():raise SystemExit('Missing rollback executable')
    if hashlib.sha256(source.read_bytes()).digest()!=hashlib.sha256(target.read_bytes()).digest():raise SystemExit('Replacement differs')
print('Windows update handoff passed')
