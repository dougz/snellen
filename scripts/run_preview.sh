#!/bin/bash


exec python3.7 "${HUNT2020_BASE}/snellen/tools/preview.py" \
     --credentials "${HUNT2020_BASE}/snellen/misc/hunt2020-20386e110718.json" \
     --public_host snellen-preview.storage.googleapis.com \
     --template_path "${HUNT2020_BASE}/snellen/html" \
     --event_dir bts \
     "$@"

