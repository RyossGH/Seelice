#!/usr/bin/env bash
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || echo "[!] ffmpeg introuvable : sudo apt install ffmpeg"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
python app.py
