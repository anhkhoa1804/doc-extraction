#!/usr/bin/env bash
# Launch N parallel prepare.py processes (one per chunk built by
# build_concurrency_chunks.py), each a SEPARATE OS process (never threads --
# see _get_component_backends()'s docstring constraint), monitor GPU
# throughout, wait for all to finish, record wall time.
#
# Usage: run_concurrency_arm.sh <N> <config_yaml> <label>
set -euo pipefail
N="$1"
CONFIG="$2"
LABEL="$3"
HERE="/home/leanhkhoa150204/doc-extraction"
SNAP="$HERE/experiments/034a_omnidocbench_snapshot"
PY="/home/leanhkhoa150204/.venvs/doc-extraction-gpu312/bin/python3"

cd "$HERE"

# GPU monitor in the background
bash "$SNAP/gpu_monitor.sh" "$SNAP/results/gpu_${LABEL}.csv" 2 &
MONITOR_PID=$!

start_ts=$(date +%s.%N)
pids=()
for c in $(seq 0 $((N-1))); do
  out="$SNAP/results/conc_${LABEL}_chunk${c}"
  rm -rf "$out"
  "$PY" "$HERE/experiments/005_omnidocbench/prepare.py" \
    --dataset "$SNAP/dataset/conc_${N}way_chunk${c}" \
    --backend baseline \
    --output "$out" \
    --config "$CONFIG" \
    > "$SNAP/results/conc_${LABEL}_chunk${c}.log" 2>&1 &
  pids+=($!)
done

# wait for all chunk processes, record individual exit codes
fail=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    fail=1
  fi
done
end_ts=$(date +%s.%N)

kill "$MONITOR_PID" 2>/dev/null || true
wait "$MONITOR_PID" 2>/dev/null || true

wall=$(echo "$end_ts - $start_ts" | bc)
echo "CONCURRENCY_ARM_DONE label=$LABEL n=$N wall_seconds=$wall any_failed=$fail"
