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

root="${t}/${version}"
base="${t}/${version}${INSTALL_DIR}"
debdir="${t}/${version}/DEBIAN"

PUZZLE_SERVERS=(badart tugofwar tunnel_of_love hat_venn_dor masked_images)

##
## base server
##

(
    cd snellen
    base="${base}/snellen"
    install -m 0755 -d "${base}"

    for d in src tools html misc; do
	install -m 0755 -d "${base}/${d}"
    done
    for i in src/*.py tools/*.py html/*.html misc/upload-credentials.json; do
	install -m 0644 $i "${base}/${i}"
    done
    for i in src/main.py tools/preview.py; do
	chmod 0755 "${base}/${i}"
    done
    install -m 0644 misc/preview-htpasswd "${base}/misc/preview-htpasswd"
)

##
## bts
##

(
    cd bts
    base="${base}/bts"
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
## preview_event
##

(
    cd preview_event
    base="${base}/preview_event"
    install -m 0755 -d "${base}"

    for i in map_config.json; do
	install -m 0644 $i "${base}/${i}"
    done
)

##
## puzzles w/servers
##

for i in "${PUZZLE_SERVERS[@]}"; do
    install -m 0755 -d "${base}/${i}"
    install -m 0755 "${i}/${i}.py" "${base}/${i}/${i}.py"
done

##
## systemd configs
##

install -m 0755 -d "${root}/lib/systemd/system"
for i in snellen "${PUZZLE_SERVERS[@]}"; do
    install -m 0644 "snellen/sys/${i}.service" "${root}/lib/systemd/system/${i}.service"
done
install -m 0644 "snellen/sys/hunt2020.target" "${root}/lib/systemd/system/hunt2020.target"

##
## haproxy config
##

install -m 0755 -d "${root}/etc/haproxy"
install -m 0755 "snellen/sys/haproxy.cfg" "${root}/etc/haproxy/haproxy-hunt2020.cfg"

##
## nginx config
##

install -m 0755 -d "${root}/etc/nginx/sites-available"
install -m 0755 -d "${root}/etc/nginx/sites-enabled"
install -m 0644 "snellen/sys/hunt2020" "${root}/etc/nginx/sites-available/hunt2020"

##
## misc system tuning
##

install -m 0755 -d "${root}/etc/sysctl.d"
install -m 0644 "snellen/sys/50-hunt2020.conf" "${root}/etc/sysctl.d/50-hunt2020.conf"
install -m 0755 -d "${root}/lib/udev/rules.d"
install -m 0644 "snellen/sys/99-hunt2020.rules" "${root}/lib/udev/rules.d/99-hunt2020.rules"

##
## .deb control files
##

install -d -m 0755 "$debdir"
cat >"$debdir"/control <<EOF
Package: hunt2020
Version: ${version}
Section: misc
Priority: optional
Architecture: all
Depends: python3 (>= 3.7), python3-bs4, python3-bcrypt, python3-pycurl,
  python3-tornado (>= 5.1), python3-html5lib, python3-dateutil, nginx
Maintainer: Doug Zongker <dougz@isotropic.org>
Description: MIT Mystery Hunt 2020 server
EOF

cat >"$debdir"/postinst <<EOF
#!/bin/bash

if [[ -e /etc/nginx/sites-enabled/hunt2020 ]]; then
  echo "Leaving hunt2020 site enabled"
else
  ln -s ../sites-available/hunt2020 /etc/nginx/sites-enabled/hunt2020
  echo "Enabling hunt2020 site"
fi

systemctl reload haproxy

systemctl daemon-reload
EOF
for i in snellen "${PUZZLE_SERVERS[@]}"; do
    echo "systemctl enable ${i}.service" >> "$debdir"/postinst
done

cat >"$debdir"/prerm <<EOF
#!/bin/bash
EOF
for i in snellen "${PUZZLE_SERVERS[@]}"; do
    echo "systemctl stop ${i}.service" >> "$debdir"/prerm
done
echo "systemctl stop hunt2020.target" >> "$debdir"/prerm
for i in snellen "${PUZZLE_SERVERS[@]}"; do
    echo "systemctl disable ${i}.service" >> "$debdir"/prerm
done

chmod 0755 "$debdir"/postinst "$debdir"/prerm

dpkg-deb --root-owner-group --build "$t/$version" /tmp

