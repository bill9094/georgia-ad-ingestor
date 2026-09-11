# Georgia Political Ad Ingestor

Primary-source-first reconstruction of Georgia political television advertising.

## Architecture

The service deliberately separates **research/discovery** from **document processing**:

1. A research agent scans FCC OPIF indexes and other primary filing indexes for documents that meet the Georgia political-ad criteria.
2. The agent writes exact document references to `queue/inbox.jsonl`.
3. GitHub Actions imports those references into SQLite and downloads **only those specific documents**.
4. The deterministic processor extracts contract/order/invoice data, reconciles revisions/cancellations, and updates primary-dollar accounting.
5. The research agent checks FEC, Georgia filings, Meta/Google transparency, announcements, and reputable reporting as an adversarial completeness layer.
6. Secondary claims are written to `audit/inbox.jsonl`; they never overwrite or supplement primary totals.
7. Unresolved discrepancies in `public/latest.json` drive the next targeted primary-source scan. Repeat.

The runtime no longer depends on broad FCC facility discovery.

## Primary document queue

`queue/inbox.jsonl` is append-oriented. Each line is one JSON object. A record must provide either:

- `folder_id` **and** `file_manager_id` for an FCC OPIF document; or
- an exact `source_url` for the document PDF.

Recommended fields:

```json
{"source_kind":"fcc","entity_id":"12345","service":"tv","callsign":"WXYZ","dma":"Atlanta","folder_id":"abc","file_manager_id":"def","file_name":"Order Contract.pdf","discovered_at":"2026-09-11T14:00:00-04:00","source_index_url":"https://...","discovery_note":"Political file / 2026 / federal / Senate"}
```

Queue states are persisted in SQLite: `queued`, `downloading`, `downloaded`, `reconciled`, `needs_visual_review`, `retry`, `failed`.

Re-importing the same queue item is idempotent and does not reset a processed item back to `queued`.

## Secondary audit inbox

`audit/inbox.jsonl` stores public claims and secondary signals separately from primary accounting.

Example:

```json
{"source_type":"reporting","source_name":"Reuters","source_url":"https://...","observed_at":"2026-09-11","advertiser":"No Going Back PAC","geography":"six states including Georgia","medium":"TV","claimed_amount":24900000,"amount_scope":"multi-state announced bookings","summary":"Reported $24.9m across six states; Georgia allocation unresolved","status":"unresolved"}
```

Secondary amounts are exposed in the discrepancy ledger but **never imported into primary spending totals**.

## Processor triggers

The GitHub Actions workflow runs four times daily as a safety net, can be dispatched manually, and also runs automatically whenever `queue/**` or `audit/**` changes on `main`. The bot's later `public/**` snapshot commit does **not** retrigger the workflow, preventing a publish loop.

Each processor run performs:

```text
init-db
import-queue
import-audit
process-queue
weekly
publish
cleanup
```

It does not enumerate facilities or broadly search OPIF.

## Accounting safeguards

- Never infer spend from PDF file size.
- Prefer explicitly labeled contract/order/net/gross/invoice totals.
- Preserve original reservation, current revised reservation, and aired/invoiced amount separately.
- A cancellation sets current reservation to zero through reconciliation logic.
- Revisions are reconciled to an order key rather than double-counted.
- Low-confidence or image-only documents are excluded from chart totals and surfaced for review.
- Secondary sources are completeness tests, not substitutes for primary contracts.

## Output

`public/latest.json` is the stable handoff. Schema version 2 contains:

- queue status
- weekly primary order events
- chart-safe primary amounts
- unpriced/visual-review records
- active reservations
- unresolved secondary audit signals
- exceptions

The intended loop is therefore:

**agent scans → queue exact documents → processor extracts/reconciles → agent audits secondary sources → agent searches discrepancies → repeat.**
