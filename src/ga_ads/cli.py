import argparse, json
from .config import load_config, resolve
from .db import init_db
from .pipeline import discover_tv, ingest
from .report import weekly, publish_snapshot
from .cleanup import cleanup
from .entities import import_entities

def main():
    p=argparse.ArgumentParser(prog='ga-ads'); p.add_argument('--config',default='config/georgia.yaml'); sp=p.add_subparsers(dest='cmd',required=True)
    sp.add_parser('init-db'); sp.add_parser('discover-tv'); ie=sp.add_parser('import-entities'); ie.add_argument('--csv'); x=sp.add_parser('ingest'); x.add_argument('--since',required=True); x.add_argument('--until',required=True); x.add_argument('--entity-id',action='append'); w=sp.add_parser('weekly'); w.add_argument('--since',required=True); w.add_argument('--until',required=True); pub=sp.add_parser('publish'); pub.add_argument('--since',required=True); pub.add_argument('--until',required=True); c=sp.add_parser('cleanup'); c.add_argument('--hours',type=float)
    a=p.parse_args(); cfg=load_config(a.config)
    if a.cmd=='init-db': init_db(resolve(cfg,'storage.sqlite_path')); result={'status':'ok'}
    elif a.cmd=='discover-tv': result={'entities_discovered':discover_tv(cfg)}
    elif a.cmd=='import-entities': result=import_entities(cfg,a.csv)
    elif a.cmd=='ingest': result=ingest(cfg,a.since,a.until,a.entity_id)
    elif a.cmd=='weekly': result=weekly(cfg,a.since,a.until)
    elif a.cmd=='publish': result=publish_snapshot(cfg,a.since,a.until)
    else: result={'removed':cleanup(cfg,a.hours)}
    print(json.dumps(result,indent=2,default=str))
if __name__=='__main__': main()
