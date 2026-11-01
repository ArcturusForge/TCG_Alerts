"""Windows release gate: download/check official helper, launch it and render a public test page."""
import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tcg_alerts.browser_helper import BrowserHelper
if True:
    helper=BrowserHelper(Path('.browser-helper-check').resolve(),lambda message:print(message,flush=True))
    try:
        helper.ensure(update=True)
        html=helper.solve('https://example.com/')
        if 'Example Domain' not in html:raise SystemExit('Helper returned an unexpected page')
        print('Official browser helper download/start/render passed',flush=True)
    finally:helper.close()
