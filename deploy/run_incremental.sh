#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="${PYTHONPATH:-$PWD/src}"
CONFIG="${GA_ADS_CONFIG:-config/georgia.yaml}"
TZ_NAME="${GA_ADS_TZ:-America/New_York}"
UNTIL="${GA_ADS_UNTIL:-$(TZ="$TZ_NAME" date -d 'tomorrow' +%F)}"
WEEK_SINCE="${GA_ADS_WEEK_SINCE:-$(TZ="$TZ_NAME" date -d '7 days ago' +%F)}"
QUEUE_PATH="${GA_ADS_QUEUE_PATH:-queue/inbox.jsonl}"
AUDIT_PATH="${GA_ADS_AUDIT_PATH:-audit/inbox.jsonl}"
CLASSIFICATION_PATH="${GA_ADS_CLASSIFICATION_PATH:-classification/inbox.jsonl}"
QUEUE_LIMIT="${GA_ADS_QUEUE_LIMIT:-100}"
REPROCESS_ARG=""
if [ "${GA_ADS_REPROCESS:-0}" = "1" ]; then REPROCESS_ARG="--reprocess"; fi

python -m ga_ads.cli --config "$CONFIG" init-db
python -m ga_ads.cli --config "$CONFIG" import-queue --path "$QUEUE_PATH"
python -m ga_ads.cli --config "$CONFIG" import-audit --path "$AUDIT_PATH"
python -m ga_ads.cli --config "$CONFIG" import-classification --path "$CLASSIFICATION_PATH"
python -m ga_ads.cli --config "$CONFIG" fec-audit --since "$WEEK_SINCE" --until "$UNTIL" --state GA --cycle 2026 || true
python -m ga_ads.cli --config "$CONFIG" process-queue --limit "$QUEUE_LIMIT" $REPROCESS_ARG
python -m ga_ads.cli --config "$CONFIG" apply-classification
python -m ga_ads.cli --config "$CONFIG" classification-status
python -m ga_ads.cli --config "$CONFIG" weekly --since "$WEEK_SINCE" --until "$UNTIL"
python -m ga_ads.cli --config "$CONFIG" publish --since "$WEEK_SINCE" --until "$UNTIL"
python -m ga_ads.cli --config "$CONFIG" cleanup --hours 24
