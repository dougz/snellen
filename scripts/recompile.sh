#!/bin/bash

mkdir -p "$HUNT2020_BASE/snellen/bin"

"$HUNT2020_BASE/snellen/external/closure/bin/calcdeps.py" \
    -i "$HUNT2020_BASE/snellen/src/client.js" \
    -p "$HUNT2020_BASE/snellen/external/closure/" \
    --output_file "$HUNT2020_BASE/snellen/bin/client-compiled.js" \
    -o compiled \
    -c "$HUNT2020_BASE/snellen/external/closure-compiler.jar" \
    -f '--compilation_level' -f 'ADVANCED_OPTIMIZATIONS' \
    -f '--externs' -f "$HUNT2020_BASE/snellen/src/externs.js" \
    -f '--rename_variable_prefix' -f 'H'


"$HUNT2020_BASE/snellen/external/closure/bin/calcdeps.py" \
    -i "$HUNT2020_BASE/snellen/src/admin.js" \
    -p "$HUNT2020_BASE/snellen/external/closure/" \
    --output_file "$HUNT2020_BASE/snellen/bin/admin-compiled.js" \
    -o compiled \
    -c "$HUNT2020_BASE/snellen/external/closure-compiler.jar" \
    -f '--compilation_level' -f 'ADVANCED_OPTIMIZATIONS' \
    -f '--externs' -f "$HUNT2020_BASE/snellen/src/admin-externs.js"




