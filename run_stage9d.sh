#!/bin/zsh
set -euo pipefail
cd "${0:A:h}"
exec .venv/bin/python -B main_stage9d.py "$@"
