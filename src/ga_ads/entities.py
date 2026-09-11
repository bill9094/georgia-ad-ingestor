import csv
from pathlib import Path
from .config import resolve
from .db import init_db

def import_entities(cfg, csv_path=None):
    path = Path(csv_path or resolve(cfg, 'fcc.manual_entities_csv'))
    if not path.exists(): return {'imported': 0, 'path': str(path), 'warning': 'manifest not found'}
    db = init_db(resolve(cfg, 'storage.sqlite_path')); n = 0
    with path.open(newline='') as f:
        for row in csv.DictReader(f):
            eid = (row.get('entity_id') or '').strip()
            if not eid: continue
            db.execute('''INSERT INTO entities(entity_id,service,callsign,name,state,dma,network_affiliation,active,profile_url,rss_url) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(entity_id) DO UPDATE SET service=excluded.service,callsign=excluded.callsign,name=excluded.name,state=excluded.state,dma=excluded.dma,network_affiliation=excluded.network_affiliation,active=excluded.active,profile_url=excluded.profile_url,rss_url=excluded.rss_url''', (eid,row.get('service') or 'tv',row.get('callsign'),row.get('name'),row.get('state'),row.get('dma'),row.get('network_affiliation'),int(row.get('active') or 1),row.get('profile_url'),row.get('rss_url'))); n += 1
    db.commit(); return {'imported': n, 'path': str(path)}
