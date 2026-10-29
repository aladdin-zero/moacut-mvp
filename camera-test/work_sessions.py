"""Local daily work records. The current session remains the authoritative file."""
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
import os


def today():
    return datetime.now().astimezone().date().isoformat()


def write_record(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def identify(data, legacy=False):
    data.setdefault('work_id', uuid.uuid4().hex)
    last_capture=next((e['at'] for e in reversed(data['events']) if e['event']=='capture'),data.get('created',''))
    date = str(last_capture if legacy else data.get('created',''))[:10]
    data.setdefault('work_date', date if re.fullmatch(r'\d{4}-\d{2}-\d{2}', date) else today())
    data.setdefault('work_name', '기존 작업' if legacy else data['work_date']+' 촬영')
    if legacy:
        data['legacy_work'] = True
    return data


def summary(data):
    return {key:data[key] for key in ('work_id','work_date','work_name')} | {
        'photos': sum(not p.get('deleted_at') for g in data['groups'] for p in g['photos']),
        'groups': sum(any(not p.get('deleted_at') for p in g['photos']) for g in data['groups']),
        'legacy_work': data.get('legacy_work',False)}


class WorkSessions:
    def __init__(self, directory):
        self.directory = Path(directory)/'work-sessions'
        self.directory.mkdir(exist_ok=True)
        self.records = {}
        for path in self.directory.glob('*.json'):
            data = json.loads(path.read_text(encoding='utf-8'))
            self.records[data['work_id']] = summary(data)

    def list(self, current):
        records = {**self.records, current['work_id']:summary(current)}
        return sorted(records.values(), key=lambda s:(s['work_date'],s['work_id']), reverse=True)

    def archive(self, data):
        write_record(self.directory/(data['work_id']+'.json'), data)
        self.records[data['work_id']] = summary(data)

    def load(self, work_id):
        if not isinstance(work_id,str) or not re.fullmatch(r'[0-9a-f]{32}',work_id) or work_id not in self.records:
            raise ValueError('작업을 찾지 못했습니다.')
        return json.loads((self.directory/(work_id+'.json')).read_text(encoding='utf-8'))
