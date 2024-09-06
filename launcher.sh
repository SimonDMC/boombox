#!/bin/sh
# launcher.sh
# start web server on boot

source ~simonrpi/boombox_venv/bin/activate
cd ~simonrpi/boombox
python src/app.py