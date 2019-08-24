#!/bin/bash

INSTALL_DIR=/sites/snellen

if [[ -z "$SNELLEN_BASE" ]]; then
    echo "SNELLEN_BASE is unset."
    exit 1
fi

cd "$SNELLEN_BASE"
version="$(date +"%Y%m%d-%H%M%S")-1"

t=$(mktemp -d /run/shm/deploy.XXXXXX)
cleanup() {
    rm -rf "$t"
}
trap cleanup EXIT

base="${t}/${version}${INSTALL_DIR}"
debdir="${t}/${version}/DEBIAN"

##
## base server
##

for d in src tools html misc scripts; do
    install -m 0755 -d "${base}/${d}"
done
for i in src/*.py tools/*.py html/*.html misc/hunt2020-*.json; do
    install -m 0644 $i "${base}/${i}"
done
for i in scripts/run*.sh; do
    install -m 0755 $i "${base}/${i}"
done
install -m 0644 misc/preview-htpasswd "${base}/misc/preview-htpasswd"

# ##
# ## test_event
# ##

# install -m 0755 -d "$base"/test_event
# install -m 0644 test_event/map_config.json "$base"/test_event/map_config.json
# install -m 0755 -d "$base"/test_event/puzzles
# for i in test_event/puzzles/*.json; do
#     install -m 0655 $i "${base}/${i}"
# done

##
## .deb control files
##

install -d -m 0755 "$debdir"
cat >"$debdir"/control <<EOF
Package: snellen
Version: ${version}
Section: misc
Priority: optional
Architecture: all
Depends: python3 (>= 3.7), python3-bs4, python3-bcrypt, python3-pycurl,
  python3-tornado (>= 5.1), python3-html5lib
Maintainer: Doug Zongker <dougz@isotropic.org>
Description: MIT Mystery Hunt 2020 server
EOF

dpkg-deb --root-owner-group --build "$t/$version" /tmp

