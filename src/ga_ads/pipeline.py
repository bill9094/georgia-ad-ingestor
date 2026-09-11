import json,re
from pathlib import Path
from .config import resolve
from .db import init_db
from .fcc import FCCClient
from .extract import extract_pdf
from .reconcile import upsert_order

def _v(x,*keys):
    for k in keys:
        if x.get(k) not in (None,''): return x.get(k)
def discover_tv(cfg):
    con=init_db(resolve(cfg,'storage.sqlite_path')); client=FCCClient(cfg['fcc']); rows=client.search_tv_facilities(cfg['fcc'].get('target_state','GA')); n=0
    for x in rows:
        eid=str(_v(x,'entity_id','entityId','facility_id','facilityId','id') or '')
        if not eid: continue
        callsign=_v(x,'callsign','callSign'); dma=_v(x,'dma','market','dmaName'); state=_v(x,'state','stateCode') or 'GA'
        con.execute('''INSERT INTO entities(entity_id,service,callsign,name,state,dma,active,profile_url,rss_url) VALUES(?,?,?,?,?,?,1,?,?) ON CONFLICT(entity_id) DO UPDATE SET callsign=excluded.callsign,name=excluded.name,state=excluded.state,dma=excluded.dma''',(eid,'tv',callsign,_v(x,'name','facilityName'),state,dma,f"{client.base}/tv-profile/{callsign}" if callsign else None,f"{client.base}/tv-profile/{callsign}/rss/" if callsign else None)); n+=1
    con.commit(); return n
def _alignment(cfg,rec):
    s=' '.join(str(rec.get(k) or '') for k in ('advertiser','candidate')).lower()
    if any(k in s for k in cfg.get('classification',{}).get('democratic_keywords',[])): return 'Democratic-aligned'
    if any(k in s for k in cfg.get('classification',{}).get('republican_keywords',[])): return 'Republican-aligned'
    return cfg.get('classification',{}).get('neutral_label','unclear/issue-only')
def ingest(cfg,since,until,entity_ids=None):
    con=init_db(resolve(cfg,'storage.sqlite_path')); client=FCCClient(cfg['fcc']); tmp=Path(resolve(cfg,'storage.temp_pdf_dir')); tmp.mkdir(parents=True,exist_ok=True)
    if entity_ids: entities=con.execute('SELECT * FROM entities WHERE entity_id IN (%s)'%','.join('?'*len(entity_ids)),entity_ids).fetchall()
    else: entities=con.execute('SELECT * FROM entities WHERE active=1').fetchall()
    stats={'entities':len(entities),'documents':0,'priced':0,'exceptions':0}
    for e in entities:
        try:
            docs=client.file_history(e['entity_id'],e['service'],since,until)
            for d in docs:
                old=con.execute('SELECT id,last_update_ts FROM documents WHERE folder_id=? AND file_manager_id=?',d.key).fetchone()
                if old and (not d.last_update_ts or old['last_update_ts']==d.last_update_ts): continue
                safe=re.sub(r'[^A-Za-z0-9._-]+','_',d.file_name or d.file_manager_id)+'.pdf'; dest=tmp/safe
                try: local,url=client.download(d,dest); ex=extract_pdf(local,d.file_name or '')
                except Exception as err:
                    con.execute('INSERT INTO exceptions(severity,code,message) VALUES(?,?,?)',('error','download_or_parse',f'{e["entity_id"]}: {err}')); stats['exceptions']+=1; continue
                con.execute('''INSERT INTO documents(entity_id,folder_id,file_manager_id,file_name,file_folder_path,create_ts,last_update_ts,history_status,file_status,source_service_code,source_url,sha256,local_path,doc_type,text_chars,needs_visual_review) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(folder_id,file_manager_id) DO UPDATE SET last_update_ts=excluded.last_update_ts,source_url=excluded.source_url,sha256=excluded.sha256,local_path=excluded.local_path,doc_type=excluded.doc_type,text_chars=excluded.text_chars,needs_visual_review=excluded.needs_visual_review''',(e['entity_id'],d.folder_id,d.file_manager_id,d.file_name,d.file_folder_path,d.create_ts,d.last_update_ts,d.history_status,d.file_status,d.source_service_code,url,ex['sha256'],local,ex['doc_type'],ex['text_chars'],ex['needs_visual_review']))
                did=con.execute('SELECT id FROM documents WHERE folder_id=? AND file_manager_id=?',d.key).fetchone()['id']; rec=ex['record']; rec['partisan_alignment']=_alignment(cfg,rec)
                cols=['advertiser','agency','order_number','contract_number','revision_number','candidate','office','election','flight_start','flight_end','gross_amount','net_amount','contract_total','invoice_total','spot_count','cancellation','partisan_alignment','extraction_confidence','amount_source','raw_json']; vals=[rec.get(c) for c in cols[:-1]]+[json.dumps(rec)]
                con.execute('INSERT OR REPLACE INTO extracted_records(document_id,%s) VALUES(%s)'%(','.join(cols),','.join('?'*(len(cols)+1))),[did]+vals)
                if ex['doc_type'] in ('contract','invoice'): upsert_order(con,did,e['entity_id'],d.file_name or '',ex['doc_type'],rec,d.create_ts or d.last_update_ts); stats['priced']+=1 if any(rec.get(k) is not None for k in ('contract_total','net_amount','gross_amount','invoice_total')) else 0
                if ex['needs_visual_review'] or (ex['doc_type']=='contract' and not any(rec.get(k) is not None for k in ('contract_total','net_amount','gross_amount'))): con.execute('INSERT INTO exceptions(document_id,severity,code,message) VALUES(?,?,?,?)',(did,'warning','amount_missing' if not ex['needs_visual_review'] else 'needs_visual_review','Primary FCC document requires review')); stats['exceptions']+=1
                stats['documents']+=1; con.commit()
        except Exception as err:
            con.execute('INSERT INTO exceptions(severity,code,message) VALUES(?,?,?)',('error','history_error',f'{e["entity_id"]}: {err}')); con.commit(); stats['exceptions']+=1
    return stats
