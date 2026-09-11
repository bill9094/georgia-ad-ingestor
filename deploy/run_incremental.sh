#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="${PYTHONPATH:-$PWD/src}"
CONFIG="${GA_ADS_CONFIG:-config/georgia.yaml}"
TZ_NAME="${GA_ADS_TZ:-America/New_York}"
TODAY="$(TZ="$TZ_NAME" date +%F)"
SINCE="${GA_ADS_SINCE:-$(TZ="$TZ_NAME" date -d '10 days ago' +%F)}"
UNTIL="${GA_ADS_UNTIL:-$(TZ="$TZ_NAME" date -d 'tomorrow' +%F)}"
WEEK_SINCE="${GA_ADS_WEEK_SINCE:-$(TZ="$TZ_NAME" date -d '7 days ago' +%F)}"

python -m ga_ads.cli --config "$CONFIG" init-db
python -m ga_ads.cli --config "$CONFIG" discover-tv || true
python -m ga_ads.cli --config "$CONFIG" import-entities || true
python -m ga_ads.cli --config "$CONFIG" ingest --since "$SINCE" --until "$UNTIL"
python -m ga_ads.cli --config "$CONFIG" weekly --since "$WEEK_SINCE" --until "$UNTIL"
python -m ga_ads.cli --config "$CONFIG" publish --since "$WEEK_SINCE" --until "$UNTIL"
python -m ga_ads.cli --config "$CONFIG" cleanup --hours 24
