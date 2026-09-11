import hashlib,re,subprocess,tempfile
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
    try: texts.append('\n'.join((p.extract_text() or '') for p in PdfReader(path).pages))
    except Exception: pass
    try:
        with pdfplumber.open(path) as pdf: texts.append('\n'.join((p.extract_text() or '') for p in pdf.pages))
    except Exception: pass
    return max(texts,key=len,default='')
def _ocr(path):
    try:
        from pdf2image import convert_from_path
        import pytesseract
        return '\n'.join(pytesseract.image_to_string(im,lang='eng') for im in convert_from_path(path,dpi=220,first_page=1,last_page=8))
    except Exception: return ''
def _money(s):
    if not s:return None
    try:return float(s.replace('$','').replace(',','').strip())
    except:return None
def _one(text,patterns):
    for p in patterns:
        m=re.search(p,text,re.I|re.M)
        if m:return m.group(1).strip()
def classify(name,text):
    s=(name+' '+text[:3000]).lower()
    if 'invoice' in s:return 'invoice'
    if any(x in s for x in ('order contract','contract total','order total')):return 'contract'
    if 'nab' in s:return 'nab'
    if any(x in s for x in ('traffic instruction','traffic order')):return 'traffic'
    if any(x in s for x in ('make-good','make good','rebate','credit memo')):return 'adjustment'
    return 'unknown'
def extract_pdf(path,file_name=''):
    path=Path(path); text=_text(path); used_ocr=False
    if len(text.strip())<80:
        o=_ocr(path)
        if len(o)>len(text): text=o; used_ocr=True
    doc_type=classify(file_name,text)
    rec={
      'advertiser':_one(text,[r'(?:Advertiser|Client|Sponsor)\s*[:#-]\s*([^\n\r]+)']),
      'agency':_one(text,[r'Agency\s*[:#-]\s*([^\n\r]+)']),
      'order_number':_one(text,[r'Order\s*(?:#|No\.?|Number)?\s*[:#-]\s*([A-Za-z0-9._-]+)']),
      'contract_number':_one(text,[r'Contract\s*(?:#|No\.?|Number)?\s*[:#-]\s*([A-Za-z0-9._-]+)']),
      'revision_number':_one(text,[r'Revision\s*(?:#|No\.?|Number)?\s*[:#-]\s*([A-Za-z0-9._-]+)']),
      'candidate':_one(text,[r'Candidate\s*[:#-]\s*([^\n\r]+)']),
      'office':_one(text,[r'Office\s*[:#-]\s*([^\n\r]+)']),
      'election':_one(text,[r'Election\s*[:#-]\s*([^\n\r]+)']),
      'flight_start':_one(text,[r'(?:Flight Start|Start Date)\s*[:#-]\s*([0-9/.-]+)']),
      'flight_end':_one(text,[r'(?:Flight End|End Date)\s*[:#-]\s*([0-9/.-]+)']),
      'gross_amount':_money(_one(text,[r'Gross(?: Amount| Total)?\s*[:#-]\s*(\$?[0-9,]+(?:\.\d{2})?)'])),
      'net_amount':_money(_one(text,[r'Net(?: Amount| Total)?\s*[:#-]\s*(\$?[0-9,]+(?:\.\d{2})?)'])),
      'contract_total':_money(_one(text,[r'(?:Contract Total|Order Total|Total Contract)\s*[:#-]\s*(\$?[0-9,]+(?:\.\d{2})?)'])),
      'invoice_total':_money(_one(text,[r'Invoice Total\s*[:#-]\s*(\$?[0-9,]+(?:\.\d{2})?)'])),
      'spot_count':None,'cancellation':1 if re.search(r'\b(cancelled|canceled|cancellation)\b',text,re.I) else 0}
    sc=_one(text,[r'(?:Total Spots|Spot Count)\s*[:#-]\s*(\d+)']); rec['spot_count']=int(sc) if sc else None
    amount=rec['invoice_total'] if doc_type=='invoice' else (rec['contract_total'] or rec['net_amount'] or rec['gross_amount'])
    conf=.35 + (.2 if rec['advertiser'] else 0)+(.2 if rec['order_number'] or rec['contract_number'] else 0)+(.25 if amount is not None else 0)
    if used_ocr: conf-=.1
    rec['extraction_confidence']=max(0,min(1,conf)); rec['amount_source']='labeled_pdf_field' if amount is not None else None
    return {'sha256':sha256(path),'doc_type':doc_type,'text':text,'text_chars':len(text),'needs_visual_review':1 if len(text.strip())<80 else 0,'record':rec}
