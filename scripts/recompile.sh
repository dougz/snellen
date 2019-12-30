#!/bin/bash

if [[ -z "$1" ]]; then
    echo "Must specify event."
    exit 1
fi

mkdir -p "$HUNT2020_BASE/snellen/bin"

if true; then
    "$HUNT2020_BASE/snellen/external/closure/bin/calcdeps.py" \
        -i "$HUNT2020_BASE/snellen/src/client.js" \
        -i "$HUNT2020_BASE/snellen/src/twemoji.js" \
        -i "$HUNT2020_BASE/snellen/src/common.js" \
        -p "$HUNT2020_BASE/snellen/external/closure/" \
        --output_file "$HUNT2020_BASE/snellen/bin/client-compiled.js" \
        -o compiled \
        -c "$HUNT2020_BASE/snellen/external/closure-compiler.jar" \
        -f '--compilation_level' -f 'ADVANCED_OPTIMIZATIONS' \
        -f '--externs' -f "$HUNT2020_BASE/snellen/src/common-externs.js" \
        -f '--externs' -f "$HUNT2020_BASE/snellen/src/externs.js" \
        -f '--define' -f 'goog.DEBUG=false' \
        -f '--rename_variable_prefix' -f 'H'

    "$HUNT2020_BASE/snellen/external/closure/bin/calcdeps.py" \
        -i "$HUNT2020_BASE/snellen/src/admin.js" \
        -i "$HUNT2020_BASE/snellen/src/twemoji.js" \
        -i "$HUNT2020_BASE/snellen/src/common.js" \
        -p "$HUNT2020_BASE/snellen/external/closure/" \
        --output_file "$HUNT2020_BASE/snellen/bin/admin-compiled.js" \
        -o compiled \
        -c "$HUNT2020_BASE/snellen/external/closure-compiler.jar" \
        -f '--compilation_level' -f 'ADVANCED_OPTIMIZATIONS' \
        -f '--externs' -f "$HUNT2020_BASE/snellen/src/common-externs.js" \
        -f '--externs' -f "$HUNT2020_BASE/snellen/src/admin-externs.js"

    "$HUNT2020_BASE/snellen/external/closure/bin/calcdeps.py" \
        -i "$HUNT2020_BASE/snellen/src/visit.js" \
        -p "$HUNT2020_BASE/snellen/external/closure/" \
        --output_file "$HUNT2020_BASE/snellen/bin/visit-compiled.js" \
        -o compiled \
        -c "$HUNT2020_BASE/snellen/external/closure-compiler.jar" \
        -f '--compilation_level' -f 'ADVANCED_OPTIMIZATIONS' \
        -f '--externs' -f "$HUNT2020_BASE/snellen/src/visit-externs.js"
fi

for i in event login default notopen; do
    echo "Compiling ${i}.css"
    yui-compressor --type css \
                   -o "${HUNT2020_BASE}/snellen/bin/${i}-compiled.css" \
                   "${HUNT2020_BASE}/snellen/static/${i}.css"
done

p="${HUNT2020_BASE}/${1}"
for i in $(find "$p" -name \*.css); do
    if [[ $i == *-compiled.css ]]; then continue; fi
    j=${i:${#p}:${#i}}
    echo "Compiling ${j#/}"
    d=$(dirname $i)
    b=$(basename $i)
    b=${b%.*}
    yui-compressor --type css -o "${d}/${b}-compiled.css" "$i"
done
