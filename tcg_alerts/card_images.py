"""On-demand private artwork previews; no artwork is bundled or scraped in bulk."""
from .tls import https_handler
from io import BytesIO
from urllib import request
from pathlib import Path
from .sources import validate_url

LIMIT=8*1024*1024

class ImageRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return super().redirect_request(req,fp,code,msg,headers,validate_url(newurl))


def decode(data):
    from PIL import Image,ImageOps
    if len(data)>LIMIT:raise ValueError('Artwork exceeds the 8 MB limit.')
    with Image.open(BytesIO(data)) as source:
        if source.width*source.height>20000000:raise ValueError('Artwork exceeds the 20 megapixel limit.')
        image=ImageOps.exif_transpose(source).convert('RGB')
        image.thumbnail((240,330),Image.Resampling.LANCZOS)
        return image.copy()


def load(url='',path=''):
    if path:
        p=Path(path)
        if p.stat().st_size>LIMIT:raise ValueError('Artwork exceeds the 8 MB limit.')
        return decode(p.read_bytes())
    url=validate_url(url)
    opener=request.build_opener(https_handler(), ImageRedirect())
    req=request.Request(url,headers={'User-Agent':'TCGAlerts/0.4 (user-requested artwork preview)','Accept':'image/*'})
    with opener.open(req,timeout=15) as response:data=response.read(LIMIT+1)
    return decode(data)
