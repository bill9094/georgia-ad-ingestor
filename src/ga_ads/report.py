import csv,json
from datetime import datetime,timezone
from pathlib import Path
from .config import resolve
from .db import connect


def _rows(con,since,until):
    q='''SELECT oe.event_ts,oe.event_type,oe.amount,o.order_key,o.advertiser,o.order_number,o.current_reserved_amount,o.original_reserved_amount,o.aired_invoiced_amount,o.flight_start,o.flight_end,o.partisan_alignment,o.status,o.confidence,e.callsign,e.dma,d.source_url,d.doc_type,d.file_name,d.needs_visual_review FROM order_events oe JOIN orders o ON o.order_key=oe.order_key JOIN documents d ON d.id=oe.document_id LEFT JOIN entities e ON e.entity_id=o.entity_id WHERE date(COALESCE(oe.event_ts,d.create_ts,d.ingested_at))>=date(?) AND date(COALESCE(oe.event_ts,d.create_ts,d.ingested_at))<date(?) ORDER BY COALESCE(oe.event_ts,d.create_ts,d.ingested_at)'''
    return [dict(r) for r in con.execute(q,(since,until)).fetchall()]


def _chart(rows,threshold):
    latest={r['order_key']:r for r in rows}; chart=[]; unpriced=[]
    for r in latest.values():
        if r['current_reserved_amount'] is not None and (r['confidence'] or 0)>=threshold and not r['needs_visual_review']:
            chart.append({'advertiser':r['advertiser'] or '(unresolved advertiser)','amount':r['current_reserved_amount'],'alignment':r['partisan_alignment'],'market':r['dma'],'callsign':r['callsign'],'order_key':r['order_key'],'source_url':r['source_url']})
        elif r['event_type'] in ('new_order','revision','cancellation'):
            unpriced.append({'advertiser':r['advertiser'],'market':r['dma'],'callsign':r['callsign'],'order_number':r['order_number'],'confidence':r['confidence'],'source_url':r['source_url'],'reason':'visual_review' if r['needs_visual_review'] else 'amount_missing_or_low_confidence'})
    return chart,unpriced


def _queue_summary(con):
    return {r['status']:r['n'] for r in con.execute('SELECT status,COUNT(*) n FROM document_queue GROUP BY status').fetchall()}


def _audit(con):
    return [dict(r) for r in con.execute("SELECT * FROM audit_signals WHERE status='unresolved' ORDER BY observed_at DESC,created_at DESC").fetchall()]


def weekly(cfg,since,until):
    con=connect(resolve(cfg,'storage.sqlite_path')); out=Path(resolve(cfg,'storage.export_dir')); out.mkdir(parents=True,exist_ok=True)
    rows=_rows(con,since,until); threshold=float(cfg.get('validation',{}).get('min_confidence_for_chart',.8)); chart,unpriced=_chart(rows,threshold)
    exceptions=[dict(r) for r in con.execute('SELECT * FROM exceptions WHERE resolved=0 ORDER BY created_at').fetchall()]
    audit=_audit(con); queue=_queue_summary(con); base=f'weekly_{since}_to_{until}'
    lp=out/f'{base}_ledger.csv'
    with lp.open('w',newline='') as f:
        if rows:
            w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    for suffix,obj in [('chart',chart),('unpriced',unpriced),('exceptions',exceptions),('audit_unresolved',audit),('queue',queue)]:
        (out/f'{base}_{suffix}.json').write_text(json.dumps(obj,indent=2,default=str))
    return {'ledger_rows':len(rows),'chart_rows':len(chart),'unpriced_rows':len(unpriced),'exceptions':len(exceptions),'unresolved_audit':len(audit),'queue':queue}


def publish_snapshot(cfg,since,until):
    con=connect(resolve(cfg,'storage.sqlite_path')); rows=_rows(con,since,until)
    threshold=float(cfg.get('validation',{}).get('min_confidence_for_chart',.8)); chart,unpriced=_chart(rows,threshold)
    active=[dict(r) for r in con.execute('''SELECT o.*,e.callsign,e.dma,d.source_url,d.file_name FROM orders o LEFT JOIN entities e ON e.entity_id=o.entity_id LEFT JOIN documents d ON d.id=o.latest_document_id WHERE o.status='active' AND o.current_reserved_amount IS NOT NULL ORDER BY o.current_reserved_amount DESC''').fetchall()]
    exceptions=[dict(r) for r in con.execute('SELECT * FROM exceptions WHERE resolved=0 ORDER BY created_at').fetchall()]
    audit=_audit(con); queue=_queue_summary(con)
    snap={
      'schema_version':2,
      'generated_at_utc':datetime.now(timezone.utc).isoformat(),
      'window':{'since':since,'until_exclusive':until},
      'pipeline':{
        'model':'agent discovery -> exact-document queue -> deterministic download/extract/reconcile -> secondary audit -> repeat',
        'queue_status':queue,
        'unresolved_secondary_signals':len(audit)
      },
      'accounting':{
        'chart_metric':'current_reserved_amount for new/materially revised primary-supported orders in window',
        'original_reserved_amount':'first reliable accepted contract value',
        'current_reserved_amount':'latest reliable non-cancelled contract value',
        'aired_invoiced_amount':'latest reliable invoice/reconciliation amount',
        'secondary_amounts_imported_into_primary_totals':False,
        'confidence_threshold':threshold
      },
      'weekly_events':rows,
      'chart':chart,
      'unpriced':unpriced,
      'active_future_inventory':active,
      'unresolved_audit_signals':audit,
      'exceptions':exceptions
    }
    public=Path(resolve(cfg,'storage.public_dir')); public.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(snap,indent=2,default=str); latest=public/'latest.json'; dated=public/f'weekly_{since}_to_{until}.json'
    latest.write_text(payload); dated.write_text(payload)
    return {'latest':str(latest),'dated':str(dated),'chart_rows':len(chart),'unpriced_rows':len(unpriced),'unresolved_audit':len(audit),'queue':queue}
