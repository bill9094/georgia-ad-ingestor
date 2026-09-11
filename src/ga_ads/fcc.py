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
        self.base=cfg.get('base_url','https://publicfiles.fcc.gov').rstrip('/'); self.delay=float(cfg.get('request_delay_seconds',0.75)); self.timeout=int(cfg.get('timeout_seconds',30)); self.page_size=int(cfg.get('history_page_size',100)); self.session=requests.Session(); self.session.headers['User-Agent']=cfg.get('user_agent','GeorgiaPoliticalAdResearch/1.0'); self._last=0.0; self.last_discovery_diagnostic={}
    def _wait(self):
        d=self.delay-(time.monotonic()-self._last)
        if d>0: time.sleep(d)
    def get(self,path,params=None,stream=False):
        self._wait(); r=self.session.get(self.base+path,params=params,timeout=self.timeout,stream=stream,allow_redirects=True); self._last=time.monotonic(); r.raise_for_status(); return r
    @staticmethod
    def _looks_like_facility(x):
        if not isinstance(x,dict): return False
        keys={str(k).lower() for k in x.keys()}
        return bool(keys & {'facilityid','facility_id','entityid','entity_id'}) and bool(keys & {'callsign','callsigncode','call_sign','facilityname','name'})
    @classmethod
    def _results(cls,payload):
        if isinstance(payload,list):
            if payload and all(isinstance(x,dict) for x in payload): return payload
            for x in payload:
                found=cls._results(x)
                if found: return found
            return []
        if not isinstance(payload,dict): return []
        for k in ('results','data','items','files','facilities','content','response'):
            v=payload.get(k)
            if isinstance(v,list) and v and all(isinstance(x,dict) for x in v): return v
            if isinstance(v,(dict,list)):
                found=cls._results(v)
                if found: return found
        candidates=[]
        for v in payload.values():
            if isinstance(v,list):
                dicts=[x for x in v if isinstance(x,dict)]
                if dicts and any(cls._looks_like_facility(x) for x in dicts): return dicts
                for x in v:
                    found=cls._results(x)
                    if found: return found
            elif isinstance(v,dict):
                if cls._looks_like_facility(v): candidates.append(v)
                found=cls._results(v)
                if found: return found
        return candidates
    def search_tv_facilities(self,state='GA'):
        path=f'/api/service/tv/facility/search/{state}.json'
        r=self.get(path)
        ctype=r.headers.get('content-type','')
        diag={'url':r.url,'status':r.status_code,'content_type':ctype,'text_prefix':r.text[:1200]}
        try:
            payload=r.json(); diag['top_type']=type(payload).__name__; diag['top_keys']=list(payload.keys())[:50] if isinstance(payload,dict) else None
        except Exception as err:
            self.last_discovery_diagnostic={**diag,'json_error':str(err)}
            raise RuntimeError(f'FCC facility discovery did not return JSON: {self.last_discovery_diagnostic}')
        rows=self._results(payload)
        diag['parsed_rows']=len(rows)
        if rows: diag['sample_keys']=list(rows[0].keys())[:50]
        self.last_discovery_diagnostic=diag
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
        r=self.get(f'/api/manager/download/{doc.folder_id}/{doc.file_manager_id}.pdf',stream=True); dest=Path(destination); dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open('wb') as f:
            for chunk in r.iter_content(1024*256):
                if chunk: f.write(chunk)
        return str(dest),r.url
