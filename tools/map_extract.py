#!/usr/bin/python3

import argparse
import itertools
import os
import pprint
import sys
import yaml

from PIL import Image, ImageDraw
import bs4

THUMB_MARGIN = 10

def get_polys(html):
  with open(html) as f:
    soup = bs4.BeautifulSoup(f.read(), features="html5lib")

  out = {}
  for a in soup.find_all("area"):
    assert a["shape"] == "poly"
    name = a["href"]
    coords = a["coords"]

    coords = [int(i) for i in coords.split(",")]
    coords = list(zip(coords[::2], coords[1::2]))

    out[name] = coords

  return out


class Patch:
  def __init__(self, bg_image, fg_image, coords):
    mask = Image.new("L", bg_image.size, 0)
    d = ImageDraw.Draw(mask)
    d.polygon(coords, 255)

    min_x = min(p[0] for p in coords) - 1
    max_x = max(p[0] for p in coords) + 1
    min_y = min(p[1] for p in coords) - 1
    max_y = max(p[1] for p in coords) + 1
    if min_x < 0: min_x = 0
    if min_y < 0: min_y = 0
    if max_x > bg_image.size[0]: max_x = bg_image.size[0]
    if max_y > bg_image.size[1]: max_y = bg_image.size[1]

    self.origin = [min_x, min_y]
    self.size = [max_x - min_x, max_y - min_y]

    self.image = Image.new("RGBA", self.size, (0,0,0,0))
    for j in range(min_y, max_y):
      for i in range(min_x, max_x):
        if not mask.getpixel((i, j)): continue
        k = fg_image.getpixel((i,j))
        if k != bg_image.getpixel((i,j)):
          self.image.putpixel((i-min_x, j-min_y), k)

def main():
  parser = argparse.ArgumentParser(
    description="Extract icons from images and a map.")

  parser.add_argument("--land",
                      default="land",
                      help="Land name for output yaml")
  parser.add_argument("--output_dir",
                      default=".",
                      help="Directory for output icons")
  parser.add_argument("--max_thumb_height",
                      type=int, default=260,
                      help="Max height of thumb images")

  parser.add_argument("bg_image",
                      help="Background without any attractions")
  parser.add_argument("bad_image",
                      help="Map with crappy attractions")
  parser.add_argument("bad_html",
                      help="Image map HTML")
  parser.add_argument("good_image",
                      help="Map with fixed attractions")
  parser.add_argument("good_html",
                      help="Image map HTML")
  options = parser.parse_args()

  bg_image = Image.open(options.bg_image)
  bad_map = get_polys(options.bad_html)
  bad_image = Image.open(options.bad_image)
  good_map = get_polys(options.good_html)
  good_image = Image.open(options.good_image)

  assert bg_image.size == bad_image.size
  assert bg_image.size == good_image.size
  assert set(bad_map.keys()) == set(good_map.keys())
  size = bg_image.size

  icons = []

  for name, coords in bad_map.items():
    out = {"name": name, "puzzle": "_"}
    icons.append(out)

    od = {}
    out["unlocked"] = od
    bad_patch = Patch(bg_image, bad_image, coords)
    od["pos"] = bad_patch.origin
    merged = []
    for x, y in coords:
      merged.append(str(x))
      merged.append(str(y))
    od["poly"] = ",".join(merged)
    od["size"] = bad_patch.size
    bad_patch.image.save(os.path.join(options.output_dir, f"{name}_unlocked.png"))

    od = {}
    out["solved"] = od
    coords = good_map[name]
    good_patch = Patch(bg_image, good_image, coords)
    od["pos"] = good_patch.origin
    merged = []
    for x, y in coords:
      merged.append(str(x))
      merged.append(str(y))
    od["poly"] = ",".join(merged)
    od["size"] = good_patch.size
    good_patch.image.save(os.path.join(options.output_dir, f"{name}_solved.png"))

    # find

    tx0 = min(bad_patch.origin[0], good_patch.origin[0]) - THUMB_MARGIN
    ty0 = min(bad_patch.origin[1], good_patch.origin[1]) - THUMB_MARGIN
    tx1 = max(bad_patch.origin[0] + bad_patch.size[0],
              good_patch.origin[0] + good_patch.size[0]) + THUMB_MARGIN
    ty1 = max(bad_patch.origin[1] + bad_patch.size[1],
              good_patch.origin[1] + good_patch.size[1]) + THUMB_MARGIN

    if tx0 < 0: tx0 = 0
    if ty0 < 0: ty0 = 0
    if tx1 > size[0]: tx1 = size[0]
    if ty1 > size[1]: ty1 = size[1]

    temp = bg_image.copy()
    temp.paste(bad_patch.image, tuple(bad_patch.origin), bad_patch.image)
    bad_thumb = temp.crop((tx0, ty0, tx1, ty1))
    if bad_thumb.size[1] > options.max_thumb_height:
      bad_thumb = bad_thumb.resize((bad_thumb.size[0] * options.max_thumb_height // bad_thumb.size[1],
                                    options.max_thumb_height), Image.LANCZOS)

    od = {}
    out["unlocked_thumb"] = od
    od["size"] = list(bad_thumb.size)
    bad_thumb.save(os.path.join(options.output_dir, f"{name}_unlocked_thumb.png"))

    temp = bg_image.copy()
    temp.paste(good_patch.image, tuple(good_patch.origin), good_patch.image)
    good_thumb = temp.crop((tx0, ty0, tx1, ty1))
    if good_thumb.size[1] > options.max_thumb_height:
      good_thumb = good_thumb.resize((good_thumb.size[0] * options.max_thumb_height // good_thumb.size[1],
                                    options.max_thumb_height), Image.LANCZOS)

    od = {}
    out["solved_thumb"] = od
    od["size"] = list(good_thumb.size)
    good_thumb.save(os.path.join(options.output_dir, f"{name}_solved_thumb.png"))


  y = { options.land: {"icons": icons} }
  with open(os.path.join(options.output_dir, "land.yaml"), "w") as f:
    f.write(yaml.dump(y))





if __name__ == "__main__":
  main()





