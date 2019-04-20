#!/bin/bash

"$SNELLEN_BASE/tools/closure/bin/calcdeps.py" \
    -i "$SNELLEN_BASE/src/client.js" \
    -p "$SNELLEN_BASE/tools/closure/" \
    --output_file "$SNELLEN_BASE/bin/client-compiled.js" \
    -o compiled \
    -c "$SNELLEN_BASE/tools/closure-compiler.jar" \
    -f '--compilation_level' -f 'ADVANCED_OPTIMIZATIONS' \
    -f '--externs' -f "$SNELLEN_BASE/src/externs.js"




