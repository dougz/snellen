#!/bin/bash


exec python3.7 tools/preview.py \
     --credentials misc/hunt2020-20386e110718.json \
     --template_path html \
     "$@"

