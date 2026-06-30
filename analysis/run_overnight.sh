#!/usr/bin/env bash
# Overnight batch: download remaining ERA5 years + run pipeline.
# Run via:  nohup bash analysis/run_overnight.sh > analysis/overnight.log 2>&1 &
set -euo pipefail

cd "$(dirname "$0")/.."

LOG="analysis/overnight_$(date +%F).log"
echo "[$(date)] Starting overnight CDS batch …" | tee -a "$LOG"

python analysis/multi_year_analysis.py --years 2016 2024 \
    2>&1 | tee -a "$LOG"

echo "[$(date)] Batch finished." | tee -a "$LOG"
