#!/bin/bash

INSTALL_DIR=/sites/hunt2020

if [[ -z "$HUNT2020_BASE" ]]; then
    echo "HUNT2020_BASE is unset."
    exit 1
fi

cd "$HUNT2020_BASE"
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

(
    cd snellen
    base="${base}/snellen"
    install -m 0755 -d "${base}"

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
)

##
## test_event
##

(
    cd test_event
    base="${base}/test_event"
    install -m 0755 -d "${base}"

    for i in map_config.json teams.json admins.json; do
	install -m 0644 $i "${base}/${i}"
    done

    install -m 0755 -d "${base}/puzzles"
    for i in puzzles/*.json; do
	install -m 0644 $i "${base}/${i}"
    done
)

##
## puzzles w/servers
##

for i in badart tugofwar tunnel_of_love; do
    install -m 0755 -d "${base}/${i}"
    install -m 0755 "${i}/${i}.py" "${base}/${i}/${i}.py"
done

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
  python3-tornado (>= 5.1), python3-html5lib, python3-dateutil
Maintainer: Doug Zongker <dougz@isotropic.org>
Description: MIT Mystery Hunt 2020 server
EOF

dpkg-deb --root-owner-group --build "$t/$version" /tmp

