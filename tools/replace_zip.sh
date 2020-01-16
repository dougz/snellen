#!/bin/bash

if [[ $# != 1 ]]; then
  cat <<EOF
Usage: $0 <puzzle_zip_file>
EOF
  exit 1
fi

LIVEDIR=/sites/hunt2020/event/puzzles

sudo /bin/true || {
    echo "Need sudo access."
    exit 1
}

fn=$(basename "$1")
shortname=${fn%%.*}

t=$(mktemp -d)

trap "rm -rf ${t}" EXIT

HUNT2020_BASE=/home/dougz/fix /home/dougz/fix/preprocess_puzzle.py \
             --output_dir "$t" \
             --credentials /home/dougz/fix/upload-credentials.json \
             --bucket hunt2020 \
             --public_host assets.pennypark.fun \
             "$1" || {
    echo "Upload puzzle assets failed."
    exit 1
}

current_version=$(jq .zip_version "${LIVEDIR}/${shortname}.json")
current_version=${current_version%.*}
current_version=${current_version#*.}
new_version=$(jq .zip_version "${t}/puzzles/${shortname}.json")
new_version=${new_version%.*}
new_version=${new_version#*.}

B="$(tput bold)"
N="$(tput sgr0)"
R="$(tput setaf 1)"
G="$(tput setaf 2)"

echo "Replacing ${B}${shortname}${N} version ${B}${R}${current_version}${N} with ${B}${G}${new_version}${N}."
read -p "Proceed? [y/N]> " answer

case $answer in
    y|Y) ;;
    *) echo "Cancelled."
       exit 1
       ;;
esac

save_dir="${LIVEDIR}/old/${shortname}-${current_version}"
sudo mkdir -p "$save_dir"
sudo mv "${LIVEDIR}/${shortname}".*json "$save_dir"
sudo mv "${t}/puzzles/${shortname}".*json "$LIVEDIR"
sudo chmod -R go+rX "${LIVEDIR}/old"

echo "Files replaced. Former versions are in ${save_dir}."
echo "You can reload the puzzle at: https://pennypark.fun/admin/fix/${shortname}"







