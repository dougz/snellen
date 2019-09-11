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
  MARGIN = 5

  def __init__(self, image, coords):
    d = ImageDraw.Draw(Image.new("L", image.size, 0))
    d.polygon(coords, 255)

    min_x = min(p[0] for p in coords) - self.MARGIN
    max_x = max(p[0] for p in coords) + self.MARGIN
    min_y = min(p[1] for p in coords) - self.MARGIN
    max_y = max(p[1] for p in coords) + self.MARGIN
    if min_x < 0: min_x = 0
    if min_y < 0: min_y = 0
    if max_x > image.size[0]: max_x = image.size[0]
    if max_y > image.size[1]: max_y = image.size[1]

    self.origin = [min_x, min_y]
    self.size = [max_x - min_x, max_y - min_y]
    self.image = image.crop((min_x, min_y, max_x, max_y))

    t = []
    for x, y in coords:
      t.append(str(x))
      t.append(str(y))
    self.coords_str = ",".join(t)

    self.mask = Image.new("RGBA", self.image.size, (255,255,255,0))
    self.mask.paste((255,255,255,255), self.image)



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
  parser.add_argument("--background_color",
                      default="#f8f8f8",
                      help="Background color for map")

  parser.add_argument("bg_image",
                      help="Background without any attractions")
  parser.add_argument("bad_image",
                      help="Broken attractions")
  parser.add_argument("bad_html",
                      help="Image map HTML")
  parser.add_argument("good_image",
                      help="Fixed attractions")
  parser.add_argument("good_html",
                      help="Image map HTML")
  options = parser.parse_args()

  assert options.background_color[0] == "#" and len(options.background_color) == 7
  options.background_color = tuple(int(options.background_color[i*2+1:i*2+3], 16) for i in range(3))

  bg_image = Image.open(options.bg_image)
  bad_map = get_polys(options.bad_html)
  bad_image = Image.open(options.bad_image)
  good_map = get_polys(options.good_html)
  good_image = Image.open(options.good_image)

  assert bg_image.size == bad_image.size
  assert bg_image.size == good_image.size
  assert set(bad_map.keys()) == set(good_map.keys())
  size = bg_image.size

  temp = Image.new("RGB", size, options.background_color)
  temp.paste(bg_image, (0,0), bg_image)
  bg_image = temp

  icons = {}

  for name, coords in bad_map.items():
    out = {}
    icons[name] = out

    bad_coords = coords
    bad_patch = Patch(bad_image, bad_coords)

    od = {}
    out["unlocked"] = od
    od["pos"] = bad_patch.origin
    od["poly"] = bad_patch.coords_str
    od["size"] = bad_patch.size
    bad_patch.image.save(os.path.join(options.output_dir, f"{name}_unlocked.png"))

    od = {}
    out["unlocked_mask"] = od
    od["pos"] = bad_patch.origin[:]
    od["size"] = bad_patch.size[:]
    bad_patch.mask.save(os.path.join(options.output_dir, f"{name}_unlocked_mask.png"))

    good_coords = good_map[name]
    good_patch = Patch(good_image, good_coords)

    od = {}
    out["solved"] = od
    od["pos"] = good_patch.origin
    od["poly"] = good_patch.coords_str
    od["size"] = good_patch.size
    good_patch.image.save(os.path.join(options.output_dir, f"{name}_solved.png"))

    od = {}
    out["solved_mask"] = od
    od["pos"] = good_patch.origin[:]
    od["size"] = good_patch.size[:]
    good_patch.mask.save(os.path.join(options.output_dir, f"{name}_solved_mask.png"))


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





