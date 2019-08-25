#!/bin/bash

mkdir -p "$SNELLEN_BASE/bin"

"$SNELLEN_BASE/external/closure/bin/calcdeps.py" \
    -i "$SNELLEN_BASE/src/client.js" \
    -p "$SNELLEN_BASE/external/closure/" \
    --output_file "$SNELLEN_BASE/bin/client-compiled.js" \
    -o compiled \
    -c "$SNELLEN_BASE/external/closure-compiler.jar" \
    -f '--compilation_level' -f 'ADVANCED_OPTIMIZATIONS' \
    -f '--externs' -f "$SNELLEN_BASE/src/externs.js" \
    -f '--rename_variable_prefix' -f 'H'


"$SNELLEN_BASE/external/closure/bin/calcdeps.py" \
    -i "$SNELLEN_BASE/src/admin.js" \
    -p "$SNELLEN_BASE/external/closure/" \
    --output_file "$SNELLEN_BASE/bin/admin-compiled.js" \
    -o compiled \
    -c "$SNELLEN_BASE/external/closure-compiler.jar" \
    -f '--compilation_level' -f 'ADVANCED_OPTIMIZATIONS' \
    -f '--externs' -f "$SNELLEN_BASE/src/admin-externs.js"




