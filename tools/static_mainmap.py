#!/usr/bin/python3

import argparse
import os
import sys
import yaml
from collections import namedtuple
import string
import tornado.template
import zipfile

from PIL import Image

def make_sortkey(s):
  s = [k for k in s.lower() if k in string.ascii_lowercase + " "]
  s = "".join(s).split()
  while len(s) > 1 and s[0] in ("the", "a", "an"):
    s.pop(0)
  return "".join(s)

Area = namedtuple("Area", ["poly", "target"])
Text = namedtuple("Text", ["title", "xywh", "target", "sortkey"])

parser = argparse.ArgumentParser(description="Make a static mainmap.")
parser.add_argument("--config")
parser.add_argument("--base_image", default=None)
parser.add_argument("--yaml_file", default=None)

options = parser.parse_args()

land = "mainmap"
basedir = f"static"
if options.base_image is None:
  options.base_image = f"bts_src/assets/{land}/map_base4.png"
input_base = os.path.dirname(options.base_image)
if options.yaml_file is None:
  options.yaml_file = f"bts_src/assets/{land}/land.yaml"
css_file = f"bts_src/assets/{land}/land.css"

with open(options.config) as f:
  allcfg = yaml.safe_load(f.read())
  cfg = allcfg[land]

with open(options.yaml_file) as f:
  y = yaml.safe_load(f.read())

im = Image.open(options.base_image).convert("RGBA")

loader = tornado.template.Loader(os.path.join(os.getenv("HUNT2020_BASE"),
                                              "snellen/tools/templates"))
map_template = loader.load("map.html")
td = {"base": im,
      "css": ["/static.css", f"/land/{land}/land.css"],
      "config": cfg,
      "script": None,
      "json_data": None,
      }

for n, d in y["icons"].items():
  i = d.get("under")
  if not i: continue
  icon = Image.open(os.path.join(input_base, f"under_{n}.png")).convert("RGBA")
  im.paste(icon, tuple(i["pos"]), mask=icon)

areas = []
texts = []
td["areas"] = areas
td["texts"] = texts
for n, d in y["icons"].items():
  if n in ("warning", "statue"): continue
  i = d.get("image")
  if not i: continue

  if n == "statue_open":
    url = "/heart_of_the_park"
  elif n == "workshop":
    url = "/workshop"
  elif n == "events":
    url = "/events"
  else:
    url = f"/land/{n}"

  icon = Image.open(os.path.join(input_base, f"image_{n}.png")).convert("RGBA")
  im.paste(icon, tuple(i["pos"]), mask=icon)

  areas.append(Area(i["poly"], url))

  if n == "events":
    t = "Events"
    sortkey = (3,)
  elif n == "workshop":
    t = "Workshop"
    sortkey = (1,)
  elif n == "statue_open":
    t = "Heart of the Park"
    sortkey = (0,)
  else:
    t = allcfg[n]["title"]
    sortkey = (2, make_sortkey(t))
  offsets = cfg.get("offsets", {}).get(n, (0,0,0))
  if len(offsets) == 2:
    offsets.append(0)

  x, y = i["pos"]
  w, h = i["size"]

  texts.append(Text(t, (x+offsets[0], y+offsets[1], w+offsets[2], h),
                    url, sortkey))

texts.sort(key=lambda t: t.sortkey)

logo = Image.open(f"bts_src/assets/mainmap/cloud5.png").convert("RGBA")
im.paste(logo, (0,0), mask=logo)

im.save(os.path.join(basedir, "map.png"))

with open(os.path.join(basedir, "index.html"), "wb") as f:
  f.write(map_template.generate(**td))



