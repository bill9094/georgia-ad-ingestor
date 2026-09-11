import re,time
from dataclasses import dataclass
from difflib import SequenceMatcher
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
    def _file_record(x):
        if not isinstance(x,dict): return False
        keys={str(k).lower() for k in x.keys()}
        return bool(keys & {'filename','file_name'}) and bool(keys & {'filemanagerid','file_manager_id','id','folderid','folder_id'})
    @classmethod
    def _file_rows(cls,payload):
        out=[]
        def walk(v):
            if isinstance(v,dict):
                if cls._file_record(v): out.append(v)
                for child in v.values(): walk(child)
            elif isinstance(v,list):
                for child in v: walk(child)
        walk(payload); seen=set(); result=[]
        for x in out:
            sig=(str(x.get('folder_id') or x.get('folderId') or ''),str(x.get('file_manager_id') or x.get('fileManagerId') or x.get('Id') or x.get('id') or ''),str(x.get('file_name') or x.get('fileName') or ''))
            if sig not in seen: seen.add(sig); result.append(x)
        return result
    @staticmethod
    def _to_document(entity_id,x,source_service=None):
        return FCCDocument(str(entity_id),str(x.get('folder_id') or x.get('folderId') or ''),str(x.get('file_manager_id') or x.get('fileManagerId') or x.get('Id') or x.get('id') or ''),x.get('file_name') or x.get('fileName'),x.get('file_folder_path') or x.get('fileFolderPath'),x.get('create_ts') or x.get('createTs') or x.get('createDate'),x.get('last_update_ts') or x.get('lastUpdateTs') or x.get('lastUpdateDate'),x.get('history_status') or x.get('historyStatus'),x.get('file_status') or x.get('fileStatus'),x.get('source_service_code') or x.get('sourceServiceCode') or source_service)
    def _history_page(self,entity_id,source_service=None,start_date=None,end_date=None,offset=0,use_dates=True):
        params={'entityId':entity_id,'count':self.page_size,'offset':offset}
        if source_service: params['sourceService']=source_service
        if use_dates and start_date: params['startDate']=start_date
        if use_dates and end_date: params['endDate']=end_date
        payload=self.get('/api/manager/file/history.json',params=params).json(); return self._file_rows(payload),payload
    def file_history(self,entity_id,source_service=None,start_date=None,end_date=None)->Iterator[FCCDocument]:
        offset=0
        while True:
            rows,_=self._history_page(entity_id,source_service,start_date,end_date,offset,True)
            if not rows: break
            for x in rows: yield self._to_document(entity_id,x,source_service)
            if len(rows)<self.page_size: break
            offset+=len(rows)
    @staticmethod
    def _normalize_filename(name):
        s=(name or '').lower(); s=re.sub(r'\.pdf$','',s); s=s.replace('&',' and ')
        s=re.sub(r'\b(?:rev(?:ision)?|order|contract|invoice|nab|form|political|file)\b',' ',s)
        return ' '.join(re.findall(r'[a-z0-9]+',s))
    @classmethod
    def _filename_score(cls,target,candidate):
        a=cls._normalize_filename(target); b=cls._normalize_filename(candidate)
        if not a or not b:return 0.0
        if a==b:return 1.0
        at=set(a.split()); bt=set(b.split()); overlap=len(at&bt)/max(1,len(at|bt)); seq=SequenceMatcher(None,a,b).ratio()
        nums_a={t for t in at if t.isdigit() and len(t)>=4}; nums_b={t for t in bt if t.isdigit() and len(t)>=4}
        stable=1.0 if nums_a & nums_b else 0.0
        return .50*seq+.30*overlap+.20*stable
    def find_exact_file(self,entity_id,file_name,source_service=None,start_date=None,end_date=None):
        attempts=[(source_service,True),(None,True),(source_service,False),(None,False)]; tried=set(); diagnostics=[]; target=str(file_name).strip()
        for service,use_dates in attempts:
            key=(service,use_dates)
            if key in tried: continue
            tried.add(key); offset=0; candidates=[]
            for _ in range(50):
                try: rows,payload=self._history_page(entity_id,service,start_date,end_date,offset,use_dates)
                except Exception as err:
                    diagnostics.append({'service':service,'dates':use_dates,'offset':offset,'error':str(err)}); break
                diagnostics.append({'service':service,'dates':use_dates,'offset':offset,'rows':len(rows),'top_keys':list(payload.keys())[:20] if isinstance(payload,dict) else None})
                for x in rows:
                    name=str(x.get('file_name') or x.get('fileName') or '').strip()
                    if name==target:
                        d=self._to_document(entity_id,x,service)
                        if d.folder_id and d.file_manager_id:return d
                    score=self._filename_score(target,name)
                    if score>=.78:candidates.append((score,name,self._to_document(entity_id,x,service)))
                if len(rows)<self.page_size: break
                offset+=len(rows)
            unique={ (d.folder_id,d.file_manager_id):(score,name,d) for score,name,d in candidates if d.folder_id and d.file_manager_id }
            ranked=sorted(unique.values(),key=lambda z:z[0],reverse=True)
            if ranked:
                top=ranked[0]; second=ranked[1][0] if len(ranked)>1 else 0
                if top[0]>=.90 and top[0]-second>=.06:return top[2]
                diagnostics.append({'normalized_target':self._normalize_filename(target),'top_candidates':[(round(s,3),n) for s,n,_ in ranked[:5]]})
        raise LookupError(f'FCC history did not uniquely resolve filename for entity {entity_id}: {target}; diagnostics={diagnostics[-10:]}')
    def download(self,doc,destination):
        if not doc.file_manager_id: raise ValueError('FCC document lacks file manager id')
        self._wait(); url=f'https://files.fcc.gov/download/{doc.file_manager_id}.pdf'
        r=self.session.get(url,timeout=self.timeout,stream=True,allow_redirects=True,headers={'User-Agent':self.session.headers.get('User-Agent','Mozilla/5.0'),'Accept':'application/pdf,*/*;q=0.8'}); self._last=time.monotonic(); r.raise_for_status()
        dest=Path(destination); dest.parent.mkdir(parents=True,exist_ok=True); head=b''
        with dest.open('wb') as f:
            for chunk in r.iter_content(1024*256):
                if chunk:
                    if not head: head=chunk[:8]
                    f.write(chunk)
        if not head.startswith(b'%PDF'):
            dest.unlink(missing_ok=True); raise ValueError(f'FCC CDN response was not a PDF: {r.url} content-type={r.headers.get("content-type")}')
        return str(dest),r.url
