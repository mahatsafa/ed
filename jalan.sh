#!/bin/sh
# Satu perintah: buka Chromium (mik senyap), tunggu login manual, lalu bot jalan. Log di logs/jalan_real.txt
cd "$(dirname "$0")" || exit 1
mkdir -p logs
PY="$HOME/engdis-bot/.venv/bin/python"
"$PY" -u bot.py --target real --buka "$@" 2>&1 | tee logs/jalan_real.txt
