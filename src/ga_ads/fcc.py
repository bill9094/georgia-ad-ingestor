import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
import requests

@dataclass
class FCCDocument:
    entity_id:str; folder_id:str; file_manager_id:str; file_name:str|None=None; file_folder_path:str|None=None; create_ts:str|None=None; last_update_ts:str|None=None; history_status:str|None=None; file_status:str|None=None; source_service_code:str|None=None
    @property
    def key(self): return (self.folder_id,self.file_manager_id)

class FCCClient:
    def __init__(self,cfg):
        self.base=cfg.get('base_url','https://publicfiles.fcc.gov').rstrip('/')
        self.delay=float(cfg.get('request_delay_seconds',0.75))
        self.timeout=int(cfg.get('timeout_seconds',30))
        self.page_size=int(cfg.get('history_page_size',100))
        self.session=requests.Session()
        self.session.headers['User-Agent']=cfg.get('user_agent','GeorgiaPoliticalAdResearch/1.0')
        self._last=0.0

    def _wait(self):
        d=self.delay-(time.monotonic()-self._last)
        if d>0: time.sleep(d)

    def get(self,path,params=None,stream=False):
        self._wait()
        r=self.session.get(self.base+path,params=params,timeout=self.timeout,stream=stream,allow_redirects=True)
        self._last=time.monotonic()
        r.raise_for_status()
        return r

    @staticmethod
    def _results(payload):
        """Find a record list in OPIF responses without assuming one wrapper shape."""
        if isinstance(payload,list):
            return payload
        if not isinstance(payload,dict):
            return []
        preferred=('results','data','items','files','facilities','tv','TV','records','content')
        for k in preferred:
            v=payload.get(k)
            if isinstance(v,list):
                return v
            if isinstance(v,dict):
                nested=FCCClient._results(v)
                if nested:
                    return nested
        # FCC has changed response envelopes over time. Walk all nested objects as
        # a final deterministic fallback, preferring lists of dictionaries.
        for v in payload.values():
            if isinstance(v,list) and v and isinstance(v[0],dict):
                return v
            if isinstance(v,dict):
                nested=FCCClient._results(v)
                if nested:
                    return nested
        return []

    def search_tv_facilities(self,state='GA'):
        r=self.get(f'/api/service/tv/facility/search/{state}.json')
        payload=r.json()
        rows=self._results(payload)
        if not rows:
            # Preserve enough response detail in CI logs to diagnose FCC schema/API changes.
            preview=str(payload)
            if len(preview)>2000:
                preview=preview[:2000]+'...'
            raise RuntimeError(f'FCC TV facility discovery returned zero parseable records for {state}; response={preview}')
        return rows

    def file_history(self,entity_id,source_service=None,start_date=None,end_date=None)->Iterator[FCCDocument]:
        offset=0
        while True:
            params={'entityId':entity_id,'count':self.page_size,'offset':offset}
            if source_service: params['sourceService']=source_service
            if start_date: params['startDate']=start_date
            if end_date: params['endDate']=end_date
            rows=self._results(self.get('/api/manager/file/history.json',params=params).json())
            if not rows: break
            for x in rows:
                yield FCCDocument(str(entity_id),str(x.get('folder_id') or x.get('folderId') or ''),str(x.get('file_manager_id') or x.get('fileManagerId') or x.get('Id') or x.get('id') or ''),x.get('file_name') or x.get('fileName'),x.get('file_folder_path') or x.get('fileFolderPath'),x.get('create_ts') or x.get('createTs'),x.get('last_update_ts') or x.get('lastUpdateTs'),x.get('history_status') or x.get('historyStatus'),x.get('file_status') or x.get('fileStatus'),x.get('source_service_code') or x.get('sourceServiceCode') or source_service)
            if len(rows)<self.page_size: break
            offset+=len(rows)

    def download(self,doc,destination):
        if not doc.folder_id or not doc.file_manager_id: raise ValueError('FCC document lacks folder/file manager id')
        r=self.get(f'/api/manager/download/{doc.folder_id}/{doc.file_manager_id}.pdf',stream=True)
        dest=Path(destination)
        dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('wb') as f:
            for chunk in r.iter_content(1024*256):
                if chunk: f.write(chunk)
        return str(dest),r.url
