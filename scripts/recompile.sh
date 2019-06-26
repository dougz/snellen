#!/bin/bash

mkdir -p "$SNELLEN_BASE/bin"

"$SNELLEN_BASE/tools/closure/bin/calcdeps.py" \
    -i "$SNELLEN_BASE/src/client.js" \
    -p "$SNELLEN_BASE/tools/closure/" \
    --output_file "$SNELLEN_BASE/bin/client-compiled.js" \
    -o compiled \
    -c "$SNELLEN_BASE/tools/closure-compiler.jar" \
    -f '--compilation_level' -f 'ADVANCED_OPTIMIZATIONS' \
    -f '--externs' -f "$SNELLEN_BASE/src/externs.js"


"$SNELLEN_BASE/tools/closure/bin/calcdeps.py" \
    -i "$SNELLEN_BASE/src/admin.js" \
    -p "$SNELLEN_BASE/tools/closure/" \
    --output_file "$SNELLEN_BASE/bin/admin-compiled.js" \
    -o compiled \
    -c "$SNELLEN_BASE/tools/closure-compiler.jar" \
    -f '--compilation_level' -f 'ADVANCED_OPTIMIZATIONS' \
    -f '--externs' -f "$SNELLEN_BASE/src/admin-externs.js"




