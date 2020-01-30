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

parser = argparse.ArgumentParser(description="Make a static map.")
parser.add_argument("--land")
parser.add_argument("--config")
parser.add_argument("--base_image", default=None)
parser.add_argument("--yaml_file", default=None)
parser.add_argument("--puzzle_dir", default=None)
parser.add_argument("--all_puzzles", default=None)

options = parser.parse_args()

land = options.land
basedir = f"static/land/{land}"
if options.base_image is None:
  base = "map_base.png"
  if land == "safari":
    base = "map_base3.png"
  elif land == "cascade":
    base = "map_base2.png"
  options.base_image = f"bts_src/assets/{land}/{base}"
input_base = os.path.dirname(options.base_image)
if options.yaml_file is None:
  options.yaml_file = f"bts_src/assets/{land}/land.yaml"
css_file = f"bts_src/assets/{land}/land.css"

if options.puzzle_dir is None:
  options.puzzle_dir = os.path.join(os.getenv("HUNT2020_BASE"), "bts_src/puzzles")
if options.all_puzzles is None:
  options.all_puzzles = os.path.join(os.getenv("HUNT2020_BASE"), "bts/all_puzzles.yaml")

with open(options.config) as f:
  cfg = yaml.safe_load(f.read())[land]

with open(options.yaml_file) as f:
  y = yaml.safe_load(f.read())

try:
  with open(options.all_puzzles) as f:
    all_puzzles = yaml.safe_load(f.read())
except FileNotFoundError:
  all_puzzles = {}

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

PUZZLE_ZIPS = dict((fn.split(".",1)[0], fn) for fn in os.listdir(options.puzzle_dir)
                   if fn.endswith(".zip"))

def get_puzzle_title(shortname):
  fn = PUZZLE_ZIPS[shortname]
  with zipfile.ZipFile(os.path.join(options.puzzle_dir, fn)) as z:
    p = "metadata.yaml"
    if p not in z.namelist():
      p = f"{shortname}/metadata.yaml"
    y = yaml.safe_load(z.read(p))
    t = y["title"]
    if y.get("scrum"):
      t = "TEAMWORK TIME: " + t
    return t

if land == "cascade":
  for n, d in y["icons"].items():
    i = d.get("emptypipe2")
    if not i: continue
    icon = Image.open(os.path.join(input_base, f"emptypipe2_{n}.png")).convert("RGBA")
    im.paste(icon, tuple(i["pos"]), mask=icon)

if land == "balloons":
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
  i = d.get("image")
  if not i: continue
  if n in ("sign", "sign_overlay"): continue

  icon = Image.open(os.path.join(input_base, f"image_{n}.png")).convert("RGBA")
  im.paste(icon, tuple(i["pos"]), mask=icon)

  shortname = cfg["assignments"][n]["puzzle"]
  meta = cfg["assignments"][n].get("meta")

  areas.append(Area(i["poly"], f"/puzzle/{shortname}"))

  t = get_puzzle_title(shortname)
  offsets = cfg.get("offsets", {}).get(n, (0,0,0))
  if len(offsets) == 2:
    offsets.append(0)

  if meta:
    sortkey = (0, make_sortkey(t))
  elif n in cfg.get("additional_order", ()) or cfg["assignments"][n].get("submeta"):
    sortkey = (1, make_sortkey(t))
  else:
    sortkey = (10, make_sortkey(t))

  x, y = i["pos"]
  w, h = i["size"]
  texts.append(Text(t, (x+offsets[0], y+offsets[1], w+offsets[2], h),
                    f"/puzzle/{shortname}", sortkey))

texts.sort(key=lambda t: t.sortkey)

ap = []
all_puzzles[land] = ap
for t in texts:
  ap.append([t.title, t.target, t.sortkey[0]])

im.save(os.path.join(basedir, "map.png"))

with open(os.path.join(basedir, "index.html"), "wb") as f:
  f.write(map_template.generate(**td))

with open(options.all_puzzles, "w") as f:
  f.write(yaml.dump(all_puzzles))



