import hashlib,re
from pathlib import Path
from pypdf import PdfReader
import pdfplumber

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def _text(path):
    texts=[]
    try:texts.append('\n'.join((p.extract_text() or '') for p in PdfReader(path).pages))
    except Exception:pass
    try:
        with pdfplumber.open(path) as pdf:texts.append('\n'.join((p.extract_text() or '') for p in pdf.pages))
    except Exception:pass
    return max(texts,key=len,default='')

def _ocr(path):
    try:
        from pdf2image import convert_from_path
        import pytesseract
        return '\n'.join(pytesseract.image_to_string(im,lang='eng') for im in convert_from_path(path,dpi=220,first_page=1,last_page=8))
    except Exception:return ''

def _money(s):
    if not s:return None
    try:return float(s.replace('$','').replace(',','').replace(' ','').strip())
    except:return None

def _one(text,patterns):
    for p in patterns:
        m=re.search(p,text,re.I|re.M)
        if m:return m.group(1).strip()

def _last_money(text,patterns):
    candidates=[]
    for priority,p in enumerate(patterns):
        for m in re.finditer(p,text,re.I|re.M):
            v=_money(m.group(1))
            if v is not None:candidates.append((priority,m.start(),v,m.group(0)[:100]))
    if not candidates:return None,None
    # Prefer the most explicit label class, then the last occurrence on the invoice.
    best_priority=min(x[0] for x in candidates); pool=[x for x in candidates if x[0]==best_priority]; chosen=max(pool,key=lambda x:x[1])
    return chosen[2],chosen[3]

def _clean_party(v):
    if not v:return None
    s=' '.join(v.split()).strip(' :-#'); low=s.lower()
    if any(x in low for x in ('http://','https://','www.','terms-and-conditions','terms and conditions')):return None
    if '/' in s and len(s.split())<=3:return None
    if len(s)>160:return None
    return s

def classify(name,text):
    n=(name or '').lower().replace('-','_').replace(' ','_')
    if 'order_contract' in n or 'contract_order' in n:return 'contract'
    if 'invoice' in n:return 'invoice'
    if 'nab' in n:return 'nab'
    if 'traffic' in n:return 'traffic'
    if any(x in n for x in ('make_good','makegood','rebate','credit')):return 'adjustment'
    head=(text[:2500] or '').lower()
    if re.search(r'\border\s*(?:/|and)?\s*contract\b',head) or any(x in head for x in ('contract total','order total','order gross','order net')):return 'contract'
    if re.search(r'\binvoice\s*(?:number|no\.?|#|date|total)\b',head):return 'invoice'
    if 'nab' in head:return 'nab'
    if any(x in head for x in ('traffic instruction','traffic order')):return 'traffic'
    if any(x in head for x in ('make-good','make good','rebate','credit memo')):return 'adjustment'
    return 'unknown'

def extract_pdf(path,file_name=''):
    path=Path(path); text=_text(path); used_ocr=False
    if len(text.strip())<80:
        o=_ocr(path)
        if len(o)>len(text):text=o;used_ocr=True
    doc_type=classify(file_name,text)
    advertiser=_clean_party(_one(text,[r'(?:Advertiser\s*Name|Client\s*Name|Sponsor\s*Name|Advertiser|Client|Sponsor|Customer)\s*[:#-]\s*([^\n\r]+)',r'(?:Agency\s*/\s*Advertiser|Advertiser\s*/\s*Agency)\s*[:#-]\s*([^\n\r]+)']))
    invoice_total,invoice_evidence=_last_money(text,[
        r'(?:Invoice\s+Total|Total\s+Invoice|Grand\s+Total|Total\s+Due|Balance\s+Due|Amount\s+Due)\s*[:#-]?\s*\$?\s*([0-9][0-9,]*(?:\.\d{2})?)',
        r'(?:Net\s+Invoice\s+Total|Gross\s+Invoice\s+Total)\s*[:#-]?\s*\$?\s*([0-9][0-9,]*(?:\.\d{2})?)']) if doc_type=='invoice' else (None,None)
    rec={
      'advertiser':advertiser,
      'agency':_clean_party(_one(text,[r'(?:Agency\s*Name|Agency)\s*[:#-]\s*([^\n\r]+)'])),
      'order_number':_one(text,[r'Order\s*(?:#|No\.?|Number)?\s*[:#-]\s*([A-Za-z0-9._-]+)',r'Order\s+(?:#|No\.?|Number)\s+([A-Za-z0-9._-]+)']),
      'contract_number':_one(text,[r'Contract\s*(?:#|No\.?|Number)?\s*[:#-]\s*([A-Za-z0-9._-]+)',r'Contract\s+(?:#|No\.?|Number)\s+([A-Za-z0-9._-]+)']),
      'revision_number':_one(text,[r'Revision\s*(?:#|No\.?|Number)?\s*[:#-]\s*([A-Za-z0-9._-]+)',r'Revision\s+(?:#|No\.?|Number)\s+([A-Za-z0-9._-]+)']),
      'candidate':_clean_party(_one(text,[r'Candidate(?:\s*Name)?\s*[:#-]\s*([^\n\r]+)'])),
      'office':_clean_party(_one(text,[r'Office\s*[:#-]\s*([^\n\r]+)'])),
      'election':_clean_party(_one(text,[r'Election(?:\s*Type)?\s*[:#-]\s*([^\n\r]+)'])),
      'flight_start':_one(text,[r'(?:Flight\s*Start|Start\s*Date|Contract\s*Start)\s*[:#-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})']),
      'flight_end':_one(text,[r'(?:Flight\s*End|End\s*Date|Contract\s*End)\s*[:#-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})']),
      'gross_amount':_money(_one(text,[r'(?:Gross(?:\s+Amount|\s+Total)?|Order\s+Gross|Gross\s+Order)\s*[:#-]?\s*\$?\s*([0-9][0-9,]*(?:\.\d{2})?)'])) if doc_type!='invoice' else None,
      'net_amount':_money(_one(text,[r'(?:Net(?:\s+Amount|\s+Total)?|Order\s+Net|Net\s+Order)\s*[:#-]?\s*\$?\s*([0-9][0-9,]*(?:\.\d{2})?)'])) if doc_type!='invoice' else None,
      'contract_total':_money(_one(text,[r'(?:Contract\s+Total|Order\s+Total|Total\s+Contract|Contract\s+Amount|Order\s+Amount|Total\s+Order|Grand\s+Total|Total\s+Cost)\s*[:#-]?\s*\$?\s*([0-9][0-9,]*(?:\.\d{2})?)'])) if doc_type=='contract' else None,
      'invoice_total':invoice_total,'invoice_total_evidence':invoice_evidence,'spot_count':None,
      'cancellation':1 if re.search(r'\b(cancelled|canceled|cancellation)\b',text,re.I) else 0}
    sc=_one(text,[r'(?:Total\s+Spots|Spot\s+Count|Number\s+of\s+Spots)\s*[:#-]?\s*(\d+)']);rec['spot_count']=int(sc) if sc else None
    amount=rec['invoice_total'] if doc_type=='invoice' else (rec['contract_total'] or rec['net_amount'] or rec['gross_amount'])
    conf=.35+(.2 if rec['advertiser'] else 0)+(.2 if rec['order_number'] or rec['contract_number'] else 0)+(.25 if amount is not None else 0)
    if used_ocr:conf-=.1
    rec['extraction_confidence']=max(0,min(1,conf));rec['amount_source']='explicit_invoice_total' if doc_type=='invoice' and amount is not None else ('labeled_pdf_field' if amount is not None else None)
    return {'sha256':sha256(path),'doc_type':doc_type,'text':text,'text_chars':len(text),'needs_visual_review':1 if len(text.strip())<80 else 0,'record':rec}
