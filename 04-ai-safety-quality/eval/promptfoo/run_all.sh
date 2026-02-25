#!/usr/bin/env bash
set -euo pipefail

echo "== promptfoo: accuracy =="
npx -y promptfoo@latest eval -c promptfoo_accuracy.yaml --no-cache

echo
echo "== promptfoo: hallucination proxy =="
npx -y promptfoo@latest eval -c promptfoo_hallucination.yaml --no-cache

echo
echo "Done."
