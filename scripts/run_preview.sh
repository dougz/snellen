#!/bin/bash


exec python3.7 "${SNELLEN_BASE}/tools/preview.py" \
     --credentials "${SNELLEN_BASE}/misc/hunt2020-20386e110718.json" \
     --public_host snellen-preview.storage.googleapis.com \
     --template_path "${SNELLEN_BASE}/html" \
     --event_dir test_event \
     "$@"

