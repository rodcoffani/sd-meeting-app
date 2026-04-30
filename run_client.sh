#!/bin/bash
# Uso: ./run_client.sh [--username nome] [--room A] [--no-av]
source venv/bin/activate
pulseaudio --start 2>/dev/null || true
python3 client.py "$@"
