#!/usr/bin/env bash
set -euo pipefail

API=${API:-http://localhost:8080}

echo "[1/3] Submit"
RESP=$(curl -s -X POST "$API/v1/jobs" -F "file=@${1}" -F "route=auto")
echo "$RESP" | jq
JOB=$(echo "$RESP" | jq -r .job_id)

echo "[2/3] Poll"
for i in $(seq 1 30); do
  OUT=$(curl -s "$API/v1/jobs/$JOB")
  ST=$(echo "$OUT" | jq -r .status)
  echo "  $i status=$ST"
  if [[ "$ST" == "finished" ]]; then
    echo "$OUT" | jq
    break
  fi
  sleep 1
done

echo "[3/3] Done. Artifacts are in ./data/jobs/$JOB/"
