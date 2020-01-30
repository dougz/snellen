#!/usr/bin/python3

import argparse
import os
import sys
import yaml
from collections import namedtuple
import tornado.template
import zipfile

# gparser = argparse.ArgumentParser(description="Make a static map.")
# parser.add_argument("--land")
# parser.add_argument("--config")
# parser.add_argument("--base_image", default=None)
# parser.add_argument("--yaml_file", default=None)
# parser.add_argument("--puzzle_dir", default=None)

# options = parser.parse_args()

basedir = os.path.join(os.getenv("HUNT2020_BASE"), "static")
with open(os.path.join(os.getenv("HUNT2020_BASE"), "bts/all_puzzles.yaml")) as f:
  all_puzzles = yaml.safe_load(f.read())

static_content = {}
for i in os.listdir(os.path.join(basedir, "assets")):
  static_content[i] = f"/assets/{i}"

landnames = {
  "castle": "The Grand Castle",
  "forest": "Storybook Forest",
  "space": "Spaceopolis",
  "hollow": "Wizard's Hollow",
  "balloons": "Balloon Vendor",
  "yesterday": "YesterdayLand",
  "bigtop": "Big Top Carnival",
  "studios": "Creative Pictures Studios",
  "safari": "Safari Adventure",
  "cascade": "Cascade Bay",
  "canyon": "Cactus Canyon",
  }

loader = tornado.template.Loader(os.path.join(os.getenv("HUNT2020_BASE"),
                                              "snellen/tools/templates"))
for page in ("health_and_safety", "about_the_park", "sponsors",
             "rules", "events", "statistics", "credits",
             "heart_of_the_park", "heart_of_the_park@solution",
             "workshop", "workshop@solution",
             "puzzles"):
  template = loader.load(f"{page}.html")

  d = os.path.join(basedir, page.replace("@", "/"))

  css = ["/static.css"]
  if page in ("heart_of_the_park", "workshop"):
    css.append("land.css")
  elif page in ("workshop@solution", "heart_of_the_park@solution"):
    css.append("../land.css")
  else:
    css.append("/default.css")

  td = {"css": css,
        "script": None,
        "json_data": None,

        "videos": [
          "https://www.youtube.com/embed/jP0G-yZpgzA",
          "https://www.youtube.com/embed/r89wX9EJTnQ",
          "https://www.youtube.com/embed/82RnpI15aM0",
          "https://www.youtube.com/embed/Y3e41hZLdj8",
          "https://www.youtube.com/embed/OSHMcEoJUAk",
          "https://www.youtube.com/embed/XRKtkaS4DUQ",
          ],

        "static_content": static_content,

        "eurl": "/emoji/",
        "all_puzzles": all_puzzles,
        "landnames": landnames,
  }

  os.makedirs(d, exist_ok=True)
  print(d)

  with open(os.path.join(d, "index.html"), "wb") as f:
    f.write(template.generate(**td))



