#!/bin/bash

if [[ $# != 1 ]]; then
  cat <<EOF
Usage: $0 <puzzle_shortname>
EOF
  exit 1
fi

to_grab=$(gsutil ls "gs://snellen-prod-zip/saved/${1}" | tail -1)

if [[ -z "$to_grab" ]]; then
    echo "Didn't find that puzzle."
    exit 1
fi

fn=$(basename "$to_grab")
version=${fn%%.*}
outfn="/tmp/${1}.${version}.zip"

gsutil cp "$to_grab" "$outfn"

echo "Copied to: $(tput bold)${outfn}$(tput sgr0)"


