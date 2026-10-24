"""Strict bounded newline JSON framing. MAX_LINE excludes the newline."""
import json
import re

MAX_LINE = 96
UID = re.compile(r'^(?:[0-9A-F]{8}|[0-9A-F]{14}|[0-9A-F]{20})$')
TYPES = {'BOOT','SCAN','SESSION','FAIL','BUSY','ALARM','ALARM_OFF','HB',
         'AUTH','REMOVAL','ACK','SYNC','CFG','TEST'}

def parse(line: bytes) -> dict:
    raw = line.rstrip(b'\r\n')
    if len(raw) > MAX_LINE:
        raise ValueError('oversized protocol line')
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError('malformed JSON') from exc
    if not isinstance(obj, dict) or obj.get('t') not in TYPES:
        raise ValueError('unknown message')
    if 'uid' in obj and not UID.fullmatch(str(obj['uid'])):
        raise ValueError('invalid UID')
    if obj['t'] in {'AUTH','SCAN'} and (type(obj.get('seq')) is not int or not 0 <= obj['seq'] <= 65535):
        raise ValueError('invalid sequence')
    if obj['t'] == 'AUTH' and obj.get('ok') not in (0, 1):
        raise ValueError('invalid authorization')
    if obj['t'] in {'SESSION','SYNC'} and obj.get('state') not in {'IN','OUT'}:
        raise ValueError('invalid session')
    if obj['t'] in {'SCAN','FAIL','BUSY'} and 'uid' not in obj:
        raise ValueError('missing UID')
    if obj['t'] in {'SESSION','SYNC'} and obj.get('state') == 'IN' and 'uid' not in obj:
        raise ValueError('missing session UID')
    return obj

def encode(obj: dict) -> bytes:
    raw = json.dumps(obj, separators=(',', ':')).encode()
    parse(raw)
    return raw + b'\n'
