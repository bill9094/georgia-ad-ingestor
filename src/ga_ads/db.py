import sqlite3
from pathlib import Path

SCHEMA = r'''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS entities (
  entity_id TEXT PRIMARY KEY, service TEXT NOT NULL, callsign TEXT, name TEXT, state TEXT, dma TEXT, network_affiliation TEXT, active INTEGER DEFAULT 1, profile_url TEXT, rss_url TEXT, discovered_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS document_queue (
  queue_key TEXT PRIMARY KEY,
  source_kind TEXT NOT NULL DEFAULT 'fcc',
  entity_id TEXT,
  service TEXT,
  callsign TEXT,
  dma TEXT,
  folder_id TEXT,
  file_manager_id TEXT,
  file_name TEXT,
  source_url TEXT,
  discovered_at TEXT,
  source_index_url TEXT,
  discovery_note TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  processed_document_id INTEGER,
  queued_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_document_queue_status ON document_queue(status);
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id TEXT, folder_id TEXT NOT NULL, file_manager_id TEXT NOT NULL, file_name TEXT, file_folder_path TEXT, create_ts TEXT, last_update_ts TEXT, history_status TEXT, file_status TEXT, source_service_code TEXT, source_url TEXT, sha256 TEXT, local_path TEXT, doc_type TEXT, text_chars INTEGER DEFAULT 0, needs_visual_review INTEGER DEFAULT 0, ingested_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(folder_id, file_manager_id), FOREIGN KEY(entity_id) REFERENCES entities(entity_id)
);
CREATE TABLE IF NOT EXISTS extracted_records (
  document_id INTEGER PRIMARY KEY, advertiser TEXT, agency TEXT, order_number TEXT, contract_number TEXT, revision_number TEXT, candidate TEXT, office TEXT, election TEXT, flight_start TEXT, flight_end TEXT, gross_amount REAL, net_amount REAL, contract_total REAL, invoice_total REAL, spot_count INTEGER, cancellation INTEGER DEFAULT 0, partisan_alignment TEXT, extraction_confidence REAL DEFAULT 0, amount_source TEXT, raw_json TEXT, FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS orders (
  order_key TEXT PRIMARY KEY, entity_id TEXT, advertiser TEXT, order_number TEXT, first_document_id INTEGER, latest_document_id INTEGER, original_reserved_amount REAL, current_reserved_amount REAL, aired_invoiced_amount REAL, flight_start TEXT, flight_end TEXT, partisan_alignment TEXT, status TEXT DEFAULT 'active', confidence REAL DEFAULT 0, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(first_document_id) REFERENCES documents(id), FOREIGN KEY(latest_document_id) REFERENCES documents(id)
);
CREATE TABLE IF NOT EXISTS order_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, order_key TEXT NOT NULL, document_id INTEGER NOT NULL, event_type TEXT NOT NULL, event_ts TEXT, amount REAL, notes TEXT, UNIQUE(order_key, document_id, event_type), FOREIGN KEY(order_key) REFERENCES orders(order_key), FOREIGN KEY(document_id) REFERENCES documents(id)
);
CREATE TABLE IF NOT EXISTS audit_signals (
  signal_key TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_name TEXT,
  source_url TEXT,
  observed_at TEXT,
  advertiser TEXT,
  candidate TEXT,
  race TEXT,
  geography TEXT,
  medium TEXT,
  claimed_amount REAL,
  amount_scope TEXT,
  summary TEXT,
  status TEXT NOT NULL DEFAULT 'unresolved',
  matched_order_key TEXT,
  resolution_note TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_signals_status ON audit_signals(status);
CREATE TABLE IF NOT EXISTS exceptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER, severity TEXT, code TEXT, message TEXT, resolved INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(document_id) REFERENCES documents(id)
);
'''

def connect(path: str):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p); con.row_factory = sqlite3.Row; con.execute('PRAGMA foreign_keys=ON'); return con

def init_db(path: str):
    con = connect(path); con.executescript(SCHEMA); con.commit(); return con
