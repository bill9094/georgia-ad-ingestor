import hashlib,json,re
from pathlib import Path
from .config import resolve
from .db import init_db

def normalize_sponsor(s):
    s=(s or '').upper(); s=re.sub(r'\b(?:MHB|MEDIA|AMP)\b',' ',s); s=re.sub(r'[^A-Z0-9]+',' ',s); return ' '.join(s.split())

def _key(x):
    raw='|'.join(str(x.get(k) or '') for k in ('sponsor','alignment','support_oppose','target_candidate','source_url'))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def import_classification_evidence(cfg,path='classification/inbox.jsonl'):
    p=Path(path); con=init_db(resolve(cfg,'storage.sqlite_path')); seen=upserted=0
    if not p.exists(): return {'path':str(p),'seen':0,'upserted':0}
    for raw in p.read_text(encoding='utf-8').splitlines():
        raw=raw.strip()
        if not raw or raw.startswith('#'): continue
        x=json.loads(raw); seen+=1; sponsor=x.get('sponsor')
        if not sponsor or not x.get('source_url') or x.get('alignment') not in ('Democratic-aligned','Republican-aligned','nonpartisan/issue-only','unclear/issue-only'):
            continue
        vals=(_key(x),sponsor,normalize_sponsor(sponsor),x['alignment'],x.get('support_oppose'),x.get('target_candidate'),x.get('target_party'),x.get('communication_title'),x.get('communication_summary'),x.get('source_type'),x.get('source_name'),x['source_url'],x.get('observed_at'),float(x.get('confidence',.8)),x.get('notes'))
        con.execute('''INSERT INTO classification_evidence(evidence_key,sponsor,normalized_sponsor,alignment,support_oppose,target_candidate,target_party,communication_title,communication_summary,source_type,source_name,source_url,observed_at,confidence,notes)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(evidence_key) DO UPDATE SET alignment=excluded.alignment,support_oppose=excluded.support_oppose,target_candidate=excluded.target_candidate,target_party=excluded.target_party,communication_title=excluded.communication_title,communication_summary=excluded.communication_summary,confidence=excluded.confidence,notes=excluded.notes,updated_at=CURRENT_TIMESTAMP''',vals); upserted+=1
    con.commit(); return {'path':str(p),'seen':seen,'upserted':upserted}

def apply_classifications(cfg):
    con=init_db(resolve(cfg,'storage.sqlite_path')); ev=[dict(r) for r in con.execute('SELECT * FROM classification_evidence ORDER BY confidence DESC,updated_at DESC').fetchall()]; changed=0
    for o in con.execute("SELECT order_key,advertiser,partisan_alignment FROM orders WHERE advertiser IS NOT NULL").fetchall():
        n=normalize_sponsor(o['advertiser']); matches=[e for e in ev if e['normalized_sponsor']==n]
        if not matches: continue
        best=matches[0]
        if o['partisan_alignment']!=best['alignment']:
            con.execute('UPDATE orders SET partisan_alignment=?,updated_at=CURRENT_TIMESTAMP WHERE order_key=?',(best['alignment'],o['order_key']))
            con.execute('UPDATE extracted_records SET partisan_alignment=? WHERE document_id IN (SELECT document_id FROM order_events WHERE order_key=?)',(best['alignment'],o['order_key'])); changed+=1
    con.commit(); return {'changed_orders':changed}

def unresolved_sponsors(cfg):
    con=init_db(resolve(cfg,'storage.sqlite_path'))
    rows=con.execute("SELECT advertiser,COUNT(*) orders_count,SUM(COALESCE(current_reserved_amount,0)) amount FROM orders WHERE advertiser IS NOT NULL AND COALESCE(partisan_alignment,'unclear/issue-only') IN ('unclear/issue-only','nonpartisan/issue-only') GROUP BY advertiser ORDER BY amount DESC").fetchall()
    return [dict(r) for r in rows]
