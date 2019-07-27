#!/bin/bash

tarball=$1
if [[ -z "$tarball" ]]; then
    echo "Specify tarball filename."
    exit 1
fi

if [[ -z "$SNELLEN_BASE" ]]; then
    echo "SNELLEN_BASE is unset."
    exit 1
fi

cd "$SNELLEN_BASE"

rm -rf tools/__pycache__

tar czvf "$tarball" html scripts tools


