#!/usr/bin/python3

import json
import re

group = None

out = []
curr = None

with open("emoji-test-12-1.txt") as f:
  for line in f:
    if line.startswith("# group:"):
      _, group = line.strip().split(":", 1)
      group = group.strip()
      print("-" * 60, group)
      curr = []
      out.append([group, curr])
      continue

    if line.startswith("#"): continue

    line = line.strip()
    if not line: continue

    codes, rest = line.split(";", 1)
    _, comment = rest.split("#", 1)
    comment = comment.strip()
    e, comment = comment.split(" ", 1)
    comment = comment.strip()

    codes = codes.lower().split()
    e2 = "".join(chr(int(c, 16)) for c in codes)
    assert e2 == e

    if re.search(r"^E\d", comment):
      comment = " ".join(comment.split()[1:])

    comment = comment.lower()
    if "skin tone" in comment: continue

    hexlist = "-".join(codes)
    curr.append([comment, e, f"https://twemoji.maxcdn.com/v/12.1.3/72x72/{hexlist}.png"])

    print(codes, e, comment)

with open("emoji.json", "w") as f:
  json.dump(out, f, indent=True)



