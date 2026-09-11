import hashlib, json
from pathlib import Path
from .config import resolve
from .db import init_db


def _queue_key(x):
    explicit = x.get('queue_key')
    if explicit:
        return str(explicit)
    parts = [
        str(x.get('source_kind') or 'fcc'),
        str(x.get('entity_id') or ''),
        str(x.get('folder_id') or ''),
        str(x.get('file_manager_id') or ''),
        str(x.get('source_url') or ''),
    ]
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:32]


def import_document_queue(cfg, path='queue/inbox.jsonl'):
    p = Path(path)
    if not p.exists():
        return {'path': str(p), 'seen': 0, 'inserted': 0, 'updated': 0}
    con = init_db(resolve(cfg, 'storage.sqlite_path'))
    seen = inserted = updated = 0
    for raw in p.read_text(encoding='utf-8').splitlines():
        raw = raw.strip()
        if not raw or raw.startswith('#'):
            continue
        x = json.loads(raw); seen += 1
        key = _queue_key(x)
        eid = str(x.get('entity_id') or '').strip() or None
        if eid:
            con.execute('''INSERT INTO entities(entity_id,service,callsign,name,state,dma,active)
                           VALUES(?,?,?,?,?,?,1)
                           ON CONFLICT(entity_id) DO UPDATE SET
                             service=COALESCE(excluded.service,entities.service),
                             callsign=COALESCE(excluded.callsign,entities.callsign),
                             dma=COALESCE(excluded.dma,entities.dma)''',
                        (eid, x.get('service') or 'tv', x.get('callsign'), x.get('entity_name'), x.get('state') or 'GA', x.get('dma')))
        old = con.execute('SELECT queue_key,status FROM document_queue WHERE queue_key=?', (key,)).fetchone()
        values = (
            key, x.get('source_kind') or 'fcc', eid, x.get('service'), x.get('callsign'), x.get('dma'),
            str(x.get('folder_id') or '') or None, str(x.get('file_manager_id') or '') or None,
            x.get('file_name'), x.get('source_url'), x.get('discovered_at'), x.get('source_index_url'),
            x.get('discovery_note')
        )
        con.execute('''INSERT INTO document_queue(
                         queue_key,source_kind,entity_id,service,callsign,dma,folder_id,file_manager_id,
                         file_name,source_url,discovered_at,source_index_url,discovery_note)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(queue_key) DO UPDATE SET
                         entity_id=COALESCE(excluded.entity_id,document_queue.entity_id),
                         service=COALESCE(excluded.service,document_queue.service),
                         callsign=COALESCE(excluded.callsign,document_queue.callsign),
                         dma=COALESCE(excluded.dma,document_queue.dma),
                         folder_id=COALESCE(excluded.folder_id,document_queue.folder_id),
                         file_manager_id=COALESCE(excluded.file_manager_id,document_queue.file_manager_id),
                         file_name=COALESCE(excluded.file_name,document_queue.file_name),
                         source_url=COALESCE(excluded.source_url,document_queue.source_url),
                         discovered_at=COALESCE(excluded.discovered_at,document_queue.discovered_at),
                         source_index_url=COALESCE(excluded.source_index_url,document_queue.source_index_url),
                         discovery_note=COALESCE(excluded.discovery_note,document_queue.discovery_note),
                         updated_at=CURRENT_TIMESTAMP''', values)
        inserted += 0 if old else 1
        updated += 1 if old else 0
    con.commit()
    return {'path': str(p), 'seen': seen, 'inserted': inserted, 'updated': updated}


def queue_status(cfg):
    con = init_db(resolve(cfg, 'storage.sqlite_path'))
    rows = con.execute('SELECT status,COUNT(*) n FROM document_queue GROUP BY status ORDER BY status').fetchall()
    return {r['status']: r['n'] for r in rows}
