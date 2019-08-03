#!/bin/bash


exec python3.7 tools/preview.py \
     --credentials misc/hunt2020-20386e110718.json \
     --public_host snellen-preview.storage.googleapis.com \
     --template_path html \
     --event_dir test_event \
     "$@"

