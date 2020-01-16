#!/bin/bash

if [[ $# != 1 ]]; then
  cat <<EOF
Usage: $0 <puzzle_shortname>
EOF
  exit 1
fi

gsutil ls -l "gs://snellen-prod-zip/saved/${1}"
