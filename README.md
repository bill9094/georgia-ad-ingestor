# Georgia Political Ad Ingestor

Primary-source-first reconstruction of Georgia political television advertising.

## Architecture

The service separates research/discovery from deterministic document processing:

1. The research agent reads `config/broadcast_targets.json` and scans every listed station in Atlanta, Albany, Augusta, Savannah, Columbus, Macon, and Chattanooga/Northwest Georgia spillover, plus known cable/DBS systems.
2. Exact document references are written to `queue/inbox.jsonl`.
3. GitHub Actions imports those references and downloads only those documents.
4. FCC history filename differences are resolved conservatively using normalized stable tokens/numeric identifiers; ambiguous matches remain retry/failed rather than being guessed.
5. The processor extracts order/contract data, reconciles revisions/cancellations, and updates primary-dollar accounting.
6. Raw FEC Schedule E `is_notice=true` records for Georgia are ingested directly so 24- and 48-hour IE notices are captured even when candidate aggregates omit or lag them.
7. Secondary reporting/platform sources remain completeness checks and are written to `audit/inbox.jsonl`.
8. Unresolved sponsors are surfaced in `public/latest.json`. The research agent searches ad creative, sponsor primary sources, NAB forms, FEC notices and credible reporting, then writes attributable evidence to `classification/inbox.jsonl`.
9. Classification evidence is applied deterministically to matching orders. Inconclusive entities stay unresolved.
10. Remaining discrepancies drive another targeted primary scan. Repeat.

## Primary document queue

`queue/inbox.jsonl` is append-oriented. An FCC item may provide `folder_id + file_manager_id`, an exact PDF `source_url`, or `entity_id + exact indexed file_name` for conservative FCC-history resolution.

Queue states: `queued`, `downloading`, `downloaded`, `reconciled`, `needs_visual_review`, `retry`, `failed`.

## Broadcast universe

`config/broadcast_targets.json` is the minimum station-by-station universe. The research agent must scan each listed station every reporting cycle regardless of known advertiser activity. No market should be called inactive until its station list plus relevant cable/DBS systems have been checked.

## Invoice safeguards

Reservation accounting and invoice accounting are separate. Contract/order values may come from explicit contract total, order total, net or gross order fields. Invoice accounting accepts only explicit invoice-level labels such as `Invoice Total`, `Total Due`, `Balance Due`, `Amount Due` or `Grand Total`. Per-spot/rate values are never promoted to aired/invoiced totals.

## FEC 24/48-hour audit

`src/ga_ads/fec_audit.py` queries OpenFEC Schedule E for Georgia with `is_notice=true`. The processor stores individual IE notice amounts, filer, candidate, support/oppose context, purpose, dates and source PDF as primary audit signals. A repository/Actions secret `FEC_API_KEY` is used when available; otherwise the public `DEMO_KEY` is used.

## Evidence-based classification

`classification/inbox.jsonl` stores attributable evidence for unresolved sponsors/buys. Required fields are `sponsor`, `alignment`, and `source_url`; recommended fields include support/oppose target, candidate/party, communication title/summary, source type/name, date and confidence.

The parser never infers alignment from the sponsor name alone. `public/latest.json` exposes `unresolved_classification_entities` so the research agent knows what requires targeted searching.

## Output

`public/latest.json` schema version 3 contains queue status, weekly primary events, chart-safe amounts, unpriced items, active reservations, unresolved FCC/FEC/secondary audit signals, unresolved sponsor classifications, and exceptions.

The intended loop is:

**systematic station scan → exact-document queue → deterministic extraction/reconciliation → FEC + secondary audit → evidence-based classification → discrepancy search → repeat.**
