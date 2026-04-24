#!/bin/bash
source venv/bin/activate
pulseaudio --start
python3 client.py
