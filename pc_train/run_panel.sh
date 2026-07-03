#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python pc_train/panel.py
