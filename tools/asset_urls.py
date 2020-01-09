#!/usr/bin/python3

import sys
import json
import re
import os

def find_asset(m):
  shortname = m.group(1)
  fn = os.path.join(puzzle_dir, shortname + ".assets.json")
  with open(fn) as f:
    j = json.load(f)
  return j[m.group(2)]


puzzle_dir = sys.argv[1]
input_file = sys.argv[2]
output_file = sys.argv[3]

with open(input_file, "r") as f_in:
  with open(output_file, "w") as f_out:
    for line in f_in:
      line = re.sub(r"@@ASSET:([^:]+):([^@]+)@@", find_asset, line)
      f_out.write(line)
