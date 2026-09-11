import hashlib, json, re
from pathlib import Path
import requests
from .config import resolve
from .db import init_db
from .fcc import FCCClient, FCCDocument
from .extract import extract_pdf
from .reconcile import upsert_order


def _alignment(cfg, rec):
    s = ' '.join(str(rec.get(k) or '') for k in ('advertiser','candidate')).lower()
    if any(k in s for k in cfg.get('classification',{}).get('democratic_keywords',[])):
        return 'Democratic-aligned'
    if any(k in s for k in cfg.get('classification',{}).get('republican_keywords',[])):
        return 'Republican-aligned'
    return cfg.get('classification',{}).get('neutral_label','unclear/issue-only')


def _download_exact(client, q, dest):
    folder_id = q['folder_id']; file_manager_id = q['file_manager_id']
    if folder_id and file_manager_id:
        doc = FCCDocument(
            str(q['entity_id'] or ''), str(folder_id), str(file_manager_id), q['file_name'],
            None, q['discovered_at'], q['discovered_at'], None, None, q['service']
        )
        return client.download(doc, dest)
    url = q['source_url']
    if not url:
        raise ValueError('Queued document needs folder_id + file_manager_id or an exact source_url')
    r = requests.get(url, timeout=client.timeout, headers={'User-Agent': client.session.headers.get('User-Agent','GeorgiaPoliticalAdResearch/1.0')})
    r.raise_for_status()
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_bytes(r.content)
    return str(dest), r.url


def process_queue(cfg, limit=100):
    con = init_db(resolve(cfg,'storage.sqlite_path'))
    client = FCCClient(cfg['fcc'])
    tmp = Path(resolve(cfg,'storage.temp_pdf_dir')); tmp.mkdir(parents=True, exist_ok=True)
    rows = con.execute('''SELECT * FROM document_queue
                          WHERE status IN ('queued','retry')
                          ORDER BY COALESCE(discovered_at,queued_at), queued_at
                          LIMIT ?''', (int(limit),)).fetchall()
    stats = {'selected': len(rows), 'downloaded': 0, 'parsed': 0, 'reconciled': 0, 'priced': 0, 'visual_review': 0, 'failed': 0}
    for q in rows:
        con.execute("UPDATE document_queue SET status='downloading',attempts=attempts+1,last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE queue_key=?", (q['queue_key'],)); con.commit()
        safe = re.sub(r'[^A-Za-z0-9._-]+','_', q['file_name'] or q['file_manager_id'] or q['queue_key']) + '.pdf'
        dest = tmp / safe
        try:
            local, final_url = _download_exact(client, q, dest); stats['downloaded'] += 1
            con.execute("UPDATE document_queue SET status='downloaded',source_url=COALESCE(source_url,?),updated_at=CURRENT_TIMESTAMP WHERE queue_key=?", (final_url,q['queue_key'])); con.commit()
            ex = extract_pdf(local, q['file_name'] or '')
            folder_id = str(q['folder_id'] or ('url-' + hashlib.sha256(final_url.encode()).hexdigest()[:16]))
            file_manager_id = str(q['file_manager_id'] or hashlib.sha256(final_url.encode()).hexdigest()[:24])
            con.execute('''INSERT INTO documents(entity_id,folder_id,file_manager_id,file_name,create_ts,last_update_ts,
                           source_service_code,source_url,sha256,local_path,doc_type,text_chars,needs_visual_review)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(folder_id,file_manager_id) DO UPDATE SET
                             source_url=excluded.source_url,sha256=excluded.sha256,local_path=excluded.local_path,
                             doc_type=excluded.doc_type,text_chars=excluded.text_chars,needs_visual_review=excluded.needs_visual_review,
                             last_update_ts=COALESCE(excluded.last_update_ts,documents.last_update_ts)''',
                        (q['entity_id'],folder_id,file_manager_id,q['file_name'],q['discovered_at'],q['discovered_at'],q['service'],final_url,
                         ex['sha256'],local,ex['doc_type'],ex['text_chars'],ex['needs_visual_review']))
            did = con.execute('SELECT id FROM documents WHERE folder_id=? AND file_manager_id=?',(folder_id,file_manager_id)).fetchone()['id']
            rec = ex['record']; rec['partisan_alignment'] = _alignment(cfg,rec)
            cols=['advertiser','agency','order_number','contract_number','revision_number','candidate','office','election','flight_start','flight_end','gross_amount','net_amount','contract_total','invoice_total','spot_count','cancellation','partisan_alignment','extraction_confidence','amount_source','raw_json']
            vals=[rec.get(c) for c in cols[:-1]]+[json.dumps(rec)]
            con.execute('INSERT OR REPLACE INTO extracted_records(document_id,%s) VALUES(%s)'%(','.join(cols),','.join('?'*(len(cols)+1))),[did]+vals)
            stats['parsed'] += 1
            if ex['doc_type'] in ('contract','invoice'):
                upsert_order(con,did,q['entity_id'] or '',q['file_name'] or '',ex['doc_type'],rec,q['discovered_at'])
                stats['reconciled'] += 1
                if any(rec.get(k) is not None for k in ('contract_total','net_amount','gross_amount','invoice_total')):
                    stats['priced'] += 1
            needs_review = bool(ex['needs_visual_review']) or (ex['doc_type']=='contract' and not any(rec.get(k) is not None for k in ('contract_total','net_amount','gross_amount')))
            status = 'needs_visual_review' if needs_review else 'reconciled'
            if needs_review:
                code = 'needs_visual_review' if ex['needs_visual_review'] else 'amount_missing'
                con.execute('INSERT INTO exceptions(document_id,severity,code,message) VALUES(?,?,?,?)',(did,'warning',code,'Primary queued document requires review'))
                stats['visual_review'] += 1
            con.execute('''UPDATE document_queue SET status=?,processed_document_id=?,last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE queue_key=?''',(status,did,q['queue_key']))
            con.commit()
        except Exception as err:
            stats['failed'] += 1
            con.execute('''UPDATE document_queue SET status=CASE WHEN attempts < 3 THEN 'retry' ELSE 'failed' END,
                           last_error=?,updated_at=CURRENT_TIMESTAMP WHERE queue_key=?''',(str(err),q['queue_key']))
            con.execute('INSERT INTO exceptions(severity,code,message) VALUES(?,?,?)',('error','queue_process_error',f"{q['queue_key']}: {err}"))
            con.commit()
    return stats
