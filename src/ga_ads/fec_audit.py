import hashlib,os
import requests
from .config import resolve
from .db import init_db

BASE='https://api.open.fec.gov/v1/schedules/schedule_e/'

def _signal_key(x):
    ident=str(x.get('sched_e_sk') or x.get('link_id') or x.get('sub_id') or x.get('image_number') or '')
    raw='fec_schedule_e|'+ident+'|'+str(x.get('tran_id') or '')+'|'+str(x.get('expenditure_amount') or '')
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def _spender(x):
    c=x.get('committee') or {}
    return x.get('committee_name') or c.get('name') or x.get('filer_name') or 'FEC independent expenditure filer'

def ingest_fec_notices(cfg,since,until,state='GA',cycle=2026):
    con=init_db(resolve(cfg,'storage.sqlite_path')); key=os.getenv('FEC_API_KEY') or 'DEMO_KEY'; page=1; seen=inserted=0
    while True:
        params={'api_key':key,'candidate_office_state':state,'cycle':cycle,'is_notice':'true','min_filing_date':since,'max_filing_date':until,'per_page':100,'page':page,'sort':'-filing_date'}
        r=requests.get(BASE,params=params,timeout=45); r.raise_for_status(); payload=r.json(); rows=payload.get('results') or []
        for x in rows:
            seen+=1; candidate=x.get('candidate_name') or ' '.join(filter(None,[x.get('candidate_first_name'),x.get('candidate_last_name')])).strip() or None
            spender=_spender(x); amount=x.get('expenditure_amount'); purpose=x.get('expenditure_description'); report=x.get('report_type') or x.get('filing_form')
            direction={'S':'support','O':'oppose'}.get(x.get('support_oppose_indicator'),x.get('support_oppose_indicator'))
            summary=f"FEC {report or '24/48-hour'} Schedule E notice: {spender} {direction or 'reported an IE regarding'} {candidate or 'a Georgia federal candidate'}"
            if purpose: summary+=f"; purpose: {purpose}"
            vals=(_signal_key(x),'PRIMARY — FEC IE / disclosed expenditure',spender,x.get('pdf_url') or r.url,x.get('filing_date') or x.get('receipt_date') or x.get('dissemination_date'),spender,candidate,f"{x.get('candidate_office') or ''} {state}".strip(),state,purpose,float(amount) if amount is not None else None,'individual Schedule E 24/48-hour notice expenditure',summary,'unresolved')
            old=con.execute('SELECT 1 FROM audit_signals WHERE signal_key=?',(vals[0],)).fetchone()
            con.execute('''INSERT INTO audit_signals(signal_key,source_type,source_name,source_url,observed_at,advertiser,candidate,race,geography,medium,claimed_amount,amount_scope,summary,status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(signal_key) DO UPDATE SET source_url=excluded.source_url,observed_at=excluded.observed_at,claimed_amount=excluded.claimed_amount,summary=excluded.summary,updated_at=CURRENT_TIMESTAMP''',vals)
            inserted+=0 if old else 1
        con.commit(); pages=(payload.get('pagination') or {}).get('pages') or page
        if page>=pages or not rows: break
        page+=1
    return {'state':state,'cycle':cycle,'since':since,'until':until,'seen':seen,'inserted':inserted}
