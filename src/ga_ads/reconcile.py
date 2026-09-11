import hashlib, re

def canonical(s): return '' if not s else re.sub(r'[^a-z0-9]+','',s.lower())
def order_key(entity_id, rec, file_name=''):
    number=rec.get('order_number') or rec.get('contract_number'); adv=canonical(rec.get('advertiser'))
    raw=f'{entity_id}|{canonical(number)}|{adv}' if number else f'{entity_id}|{adv}|{rec.get("flight_start") or ""}|{canonical(file_name)[:80]}'
    return hashlib.sha1(raw.encode()).hexdigest()
def effective_amount(rec,doc_type):
    return (rec.get('invoice_total') or rec.get('net_amount') or rec.get('gross_amount') or rec.get('contract_total')) if doc_type=='invoice' else (rec.get('contract_total') or rec.get('net_amount') or rec.get('gross_amount'))
def upsert_order(con, document_id, entity_id, file_name, doc_type, rec, event_ts):
    key=order_key(entity_id,rec,file_name); amt=effective_amount(rec,doc_type); row=con.execute('SELECT * FROM orders WHERE order_key=?',(key,)).fetchone()
    if not row:
        orig=amt if doc_type=='contract' and not rec.get('cancellation') else None; current=orig; aired=amt if doc_type=='invoice' else None
        con.execute('''INSERT INTO orders(order_key,entity_id,advertiser,order_number,first_document_id,latest_document_id,original_reserved_amount,current_reserved_amount,aired_invoiced_amount,flight_start,flight_end,partisan_alignment,status,confidence,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)''',(key,entity_id,rec.get('advertiser'),rec.get('order_number') or rec.get('contract_number'),document_id,document_id,orig,current,aired,rec.get('flight_start'),rec.get('flight_end'),rec.get('partisan_alignment'),'cancelled' if rec.get('cancellation') else 'active',rec.get('extraction_confidence',0)))
    else:
        current=row['current_reserved_amount']; aired=row['aired_invoiced_amount']; status=row['status']
        if doc_type=='invoice' and amt is not None: aired=amt
        elif doc_type=='contract':
            if rec.get('cancellation'): current=0.0; status='cancelled'
            elif amt is not None: current=amt; status='active'
        con.execute('''UPDATE orders SET latest_document_id=?, advertiser=COALESCE(?,advertiser), current_reserved_amount=?, aired_invoiced_amount=?, flight_start=COALESCE(?,flight_start),flight_end=COALESCE(?,flight_end),status=?,confidence=MAX(confidence,?),updated_at=CURRENT_TIMESTAMP WHERE order_key=?''',(document_id,rec.get('advertiser'),current,aired,rec.get('flight_start'),rec.get('flight_end'),status,rec.get('extraction_confidence',0),key))
    etype='invoice' if doc_type=='invoice' else ('cancellation' if rec.get('cancellation') else ('revision' if row else 'new_order'))
    con.execute('INSERT OR IGNORE INTO order_events(order_key,document_id,event_type,event_ts,amount,notes) VALUES(?,?,?,?,?,?)',(key,document_id,etype,event_ts,amt,None)); return key
