"""Source-linked release dates with explicit precision; no guessed seasonal dates."""
from datetime import date,datetime,timezone,timedelta
import re
from .sources import validate_url


def checked_day(value):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('Use YYYY-MM-DD dates.')
    date.fromisoformat(value)
    return value


def validate(fields):
    keys=('title','game','kind','start','end','precision','window','region','status','source_url','checked','notes')
    v={k:str(fields.get(k) or '').strip() for k in keys}
    if not v['title'] or not v['game'] or not v['region']:raise ValueError('Title, game and region are required.')
    if v['precision'] not in ('Day','Range','Window','TBA') or v['status'] not in ('Confirmed','Tentative','Rumour','Cancelled') or v['kind'] not in ('Release','Prerelease','Event','Promo'):raise ValueError('Choose valid type, precision and status.')
    v['source_url']=validate_url(v['source_url']);checked_day(v['checked'])
    if v['precision'] in ('Day','Range'):
        checked_day(v['start']);v['end']=v['start'] if v['precision']=='Day' else checked_day(v['end'])
        if v['end']<v['start']:raise ValueError('End cannot precede start.')
        v['window']=''
    else:
        if v['start'] or v['end']:raise ValueError('Window/TBA entries cannot contain invented exact dates.')
        if v['precision']=='Window' and not v['window']:raise ValueError('Enter the publisher’s announced window.')
        v['start']=v['end']=None
    return v


def label(row):
    return row['start'] if row['precision']=='Day' else row['start']+' – '+row['end'] if row['precision']=='Range' else row['window'] or 'Date unannounced'


def upcoming(row,today=None):
    return row['status']!='Cancelled' and (not row['end'] or row['end']>=(today or date.today()).isoformat())


def escape(text):
    return str(text).replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(',','\\,').replace(';','\\;')


def fold(line):
    lines=[];current=''
    for char in line:
        if len((current+char).encode('utf-8'))>75:lines.append(current);current=' '+char
        else:current+=char
    return '\r\n'.join([*lines,current])


def icalendar(rows):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//TCG Alerts//Release Calendar//EN','CALSCALE:GREGORIAN'];count=skipped=0
    for r in rows:
        if r['precision'] not in ('Day','Range') or r['status']=='Cancelled':skipped+=1;continue
        end=date.fromisoformat(r['end'])+timedelta(days=1)
        description=f"{r['game']} / {r['kind']} / {r['status']}\nRegion: {r['region']}\nSource checked: {r['checked']}\n{r['notes']}"
        lines+=['BEGIN:VEVENT',f"UID:release-{r['id']}@tcgalerts.local",'DTSTAMP:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),'DTSTART;VALUE=DATE:'+r['start'].replace('-',''),'DTEND;VALUE=DATE:'+end.strftime('%Y%m%d'),'SUMMARY:'+escape(r['title']),'DESCRIPTION:'+escape(description),'LOCATION:'+escape(r['region']),'URL:'+r['source_url'],'STATUS:'+('CONFIRMED' if r['status']=='Confirmed' else 'TENTATIVE'),'END:VEVENT'];count+=1
    return '\r\n'.join(fold(line) for line in [*lines,'END:VCALENDAR'])+'\r\n',count,skipped
