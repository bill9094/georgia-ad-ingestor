import hashlib, json
from pathlib import Path
from .config import resolve
from .db import init_db


def _signal_key(x):
    if x.get('signal_key'):
        return str(x['signal_key'])
    parts = [
        str(x.get('source_type') or ''), str(x.get('source_name') or ''), str(x.get('source_url') or ''),
        str(x.get('advertiser') or ''), str(x.get('candidate') or ''), str(x.get('claimed_amount') or ''),
        str(x.get('observed_at') or '')
    ]
    return hashlib.sha256('|'.join(parts).encode()).hexdigest()[:32]


def import_audit_signals(cfg, path='audit/inbox.jsonl'):
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
        key = _signal_key(x)
        old = con.execute('SELECT signal_key FROM audit_signals WHERE signal_key=?', (key,)).fetchone()
        con.execute('''INSERT INTO audit_signals(
                         signal_key,source_type,source_name,source_url,observed_at,advertiser,candidate,race,
                         geography,medium,claimed_amount,amount_scope,summary,status,matched_order_key,resolution_note)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(signal_key) DO UPDATE SET
                         source_url=COALESCE(excluded.source_url,audit_signals.source_url),
                         observed_at=COALESCE(excluded.observed_at,audit_signals.observed_at),
                         advertiser=COALESCE(excluded.advertiser,audit_signals.advertiser),
                         candidate=COALESCE(excluded.candidate,audit_signals.candidate),
                         race=COALESCE(excluded.race,audit_signals.race),
                         geography=COALESCE(excluded.geography,audit_signals.geography),
                         medium=COALESCE(excluded.medium,audit_signals.medium),
                         claimed_amount=COALESCE(excluded.claimed_amount,audit_signals.claimed_amount),
                         amount_scope=COALESCE(excluded.amount_scope,audit_signals.amount_scope),
                         summary=COALESCE(excluded.summary,audit_signals.summary),
                         status=COALESCE(excluded.status,audit_signals.status),
                         matched_order_key=COALESCE(excluded.matched_order_key,audit_signals.matched_order_key),
                         resolution_note=COALESCE(excluded.resolution_note,audit_signals.resolution_note),
                         updated_at=CURRENT_TIMESTAMP''',
                    (key, x.get('source_type') or 'secondary', x.get('source_name'), x.get('source_url'), x.get('observed_at'),
                     x.get('advertiser'), x.get('candidate'), x.get('race'), x.get('geography'), x.get('medium'),
                     x.get('claimed_amount'), x.get('amount_scope'), x.get('summary'), x.get('status') or 'unresolved',
                     x.get('matched_order_key'), x.get('resolution_note')))
        inserted += 0 if old else 1
        updated += 1 if old else 0
    con.commit()
    return {'path': str(p), 'seen': seen, 'inserted': inserted, 'updated': updated}


def unresolved_audit(cfg):
    con = init_db(resolve(cfg, 'storage.sqlite_path'))
    return [dict(r) for r in con.execute('''SELECT * FROM audit_signals WHERE status='unresolved' ORDER BY observed_at DESC, created_at DESC''').fetchall()]
