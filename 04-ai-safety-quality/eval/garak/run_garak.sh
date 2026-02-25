#!/usr/bin/env bash
set -euo pipefail

# Run from repo root
# Example:
#   garak -c eval/garak/garak.yaml -g rest.RestGenerator

python -m garak --config eval/garak/garak.yaml
