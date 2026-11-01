"""Create the exact GitHub release asset names consumed by the desktop updater."""
import json,zipfile,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'release-assets';out.mkdir(exist_ok=True)
for platform,binary in [('Windows','TCGAlerts.exe'),('Linux','TCGAlerts')]:
    matches=list((root/'downloads').rglob(binary))
    if len(matches)!=1:raise SystemExit('Expected one '+binary)
    if platform=='Linux':matches[0].chmod(0o755)
    with zipfile.ZipFile(out/('TCGAlerts-'+platform+'.zip'),'w',zipfile.ZIP_DEFLATED) as package:
        package.write(matches[0],binary)
for folder in (root/'examples/plugins').iterdir():
    if not (folder/'plugin.json').exists():continue
    manifest=json.loads((folder/'plugin.json').read_text())
    with zipfile.ZipFile(out/('TCGAlerts-plugin-'+manifest['id']+'.zip'),'w',zipfile.ZIP_DEFLATED) as package:
        for path in folder.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:package.write(path,str(path.relative_to(folder)))
