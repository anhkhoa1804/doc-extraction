#!/usr/bin/env bash
# Polls nvidia-smi at a fixed interval and appends CSV rows until killed.
# Usage: gpu_monitor.sh <output_csv> [interval_seconds]
set -euo pipefail
OUT="$1"
INTERVAL="${2:-2}"
echo "timestamp,memory_used_mib,memory_free_mib,utilization_pct" > "$OUT"
while true; do
  ts=$(date +%s.%N)
  row=$(nvidia-smi --query-gpu=memory.used,memory.free,utilization.gpu --format=csv,noheader,nounits)
  echo "${ts},${row}" >> "$OUT"
  sleep "$INTERVAL"
done
