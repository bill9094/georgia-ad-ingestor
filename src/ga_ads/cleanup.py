import time
from pathlib import Path
from .config import resolve
from .db import connect

def cleanup(cfg,hours=None):
    hours=float(hours if hours is not None else cfg['project'].get('temp_retention_hours',24)); root=Path(resolve(cfg,'storage.temp_pdf_dir')); cutoff=time.time()-hours*3600; removed=0
    if root.exists():
        for p in root.glob('*.pdf'):
            try:
                if p.stat().st_mtime < cutoff: p.unlink(); removed+=1
            except FileNotFoundError: pass
    con=connect(resolve(cfg,'storage.sqlite_path'))
    for r in con.execute('SELECT id,local_path FROM documents WHERE local_path IS NOT NULL').fetchall():
        if not Path(r['local_path']).exists(): con.execute('UPDATE documents SET local_path=NULL WHERE id=?',(r['id'],))
    con.commit(); return removed
