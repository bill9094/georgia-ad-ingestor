import argparse, json
from .config import load_config, resolve
from .db import init_db
from .report import weekly, publish_snapshot
from .cleanup import cleanup
from .queue import import_document_queue, queue_status
from .audit import import_audit_signals, unresolved_audit
from .processor import process_queue


def main():
    p=argparse.ArgumentParser(prog='ga-ads');p.add_argument('--config',default='config/georgia.yaml');sp=p.add_subparsers(dest='cmd',required=True)
    sp.add_parser('init-db')
    q=sp.add_parser('import-queue');q.add_argument('--path',default='queue/inbox.jsonl')
    a=sp.add_parser('import-audit');a.add_argument('--path',default='audit/inbox.jsonl')
    pq=sp.add_parser('process-queue');pq.add_argument('--limit',type=int,default=100);pq.add_argument('--reprocess',action='store_true')
    sp.add_parser('queue-status');sp.add_parser('audit-status')
    w=sp.add_parser('weekly');w.add_argument('--since',required=True);w.add_argument('--until',required=True)
    pub=sp.add_parser('publish');pub.add_argument('--since',required=True);pub.add_argument('--until',required=True)
    c=sp.add_parser('cleanup');c.add_argument('--hours',type=float)
    args=p.parse_args();cfg=load_config(args.config)
    if args.cmd=='init-db':init_db(resolve(cfg,'storage.sqlite_path'));result={'status':'ok'}
    elif args.cmd=='import-queue':result=import_document_queue(cfg,args.path)
    elif args.cmd=='import-audit':result=import_audit_signals(cfg,args.path)
    elif args.cmd=='process-queue':result=process_queue(cfg,args.limit,args.reprocess)
    elif args.cmd=='queue-status':result=queue_status(cfg)
    elif args.cmd=='audit-status':result={'unresolved':unresolved_audit(cfg)}
    elif args.cmd=='weekly':result=weekly(cfg,args.since,args.until)
    elif args.cmd=='publish':result=publish_snapshot(cfg,args.since,args.until)
    else:result={'removed':cleanup(cfg,args.hours)}
    print(json.dumps(result,indent=2,default=str))

if __name__=='__main__':main()
