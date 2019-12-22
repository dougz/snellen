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
    mask = Image.new("L", image.size, 0)
    d = ImageDraw.Draw(mask)
    d.polygon(coords, 255)

    masked = Image.new("RGBA", image.size, (0,0,0,0))
    masked.paste(image, (0,0), mask)

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
    self.image = masked.crop((min_x, min_y, max_x, max_y))

    t = []
    for x, y in coords:
      t.append(str(x))
      t.append(str(y))
    self.coords_str = ",".join(t)

    self.highlight = Image.new("RGBA", self.image.size, (255,255,255,0))
    for ox in range(-2, 3):
      for oy in range(-2, 3):
        if ox in (-2,2) and oy in (-2,2): continue
        self.highlight.paste((255,255,255,255), (ox,oy), self.image)

    pixels = set()
    for j in range(self.size[1]):
      for i in range(self.size[0]):
        if self.image.getpixel((i,j))[3]:
          pixels.add((i,j))
        elif self.highlight.getpixel((i,j))[3]:
          pixels.add((i,j))
    if not pixels:
      self.image = None
      self.highlight = None
      return

    min_x = min(p[0] for p in pixels)
    max_x = max(p[0] for p in pixels)
    min_y = min(p[1] for p in pixels)
    max_y = max(p[1] for p in pixels)

    w = max_x + 1 - min_x
    h = max_y + 1 - min_y

    self.image = self.image.crop((min_x, min_y, max_x, max_y))
    self.highlight = self.highlight.crop((min_x, min_y, max_x, max_y))

    self.origin = [self.origin[0] + min_x, self.origin[1] + min_y]
    self.size = [w, h]


def main():
  parser = argparse.ArgumentParser(
    description="Extract icons from images and a map.")

  parser.add_argument("--output_dir",
                      default=".",
                      help="Directory for output icons")
  parser.add_argument("--max_thumb_height",
                      type=int, default=260,
                      help="Max height of thumb images")
  parser.add_argument("--background_color",
                      default="#f8f8f8",
                      help="Background color for map")

  parser.add_argument("html",
                      help="Image map HTML")
  parser.add_argument("source_image")
  parser.add_argument("--under_image", default=None)
  parser.add_argument("--under_html", default=None)

  options = parser.parse_args()

  assert options.background_color[0] == "#" and len(options.background_color) == 7
  options.background_color = tuple(int(options.background_color[i*2+1:i*2+3], 16) for i in range(3))

  html_map = get_polys(options.html)
  if options.under_html:
    under_map = get_polys(options.under_html)
  else:
    under_map = html_map
  
  source_image = Image.open(options.source_image).convert("RGBA")
  if options.under_image:
    under_image = Image.open(options.under_image).convert("RGBA")
    assert under_image.size == source_image.size
  else:
    under_image = None

  size = source_image.size

  icons = {}

  for name, coords in html_map.items():
    out = {}
    icons[name] = out

    patch = Patch(source_image, coords)

    if patch.image:
      od = {}
      out["image"] = od
      od["pos"] = patch.origin
      od["poly"] = patch.coords_str
      od["size"] = patch.size
      patch.image.save(os.path.join(options.output_dir, f"image_{name}.png"))

    if patch.highlight:
      od = {}
      out["mask"] = od
      od["pos"] = patch.origin[:]
      od["size"] = patch.size[:]
      patch.highlight.save(os.path.join(options.output_dir, f"mask_{name}.png"))

    if under_image:
      under_coords = under_map.get(name)
      if under_coords:
        under_patch = Patch(under_image, under_coords)

        if under_patch.image:
          od = {}
          out["under"] = od
          od["pos"] = under_patch.origin
          od["poly"] = under_patch.coords_str
          od["size"] = under_patch.size
          under_patch.image.save(os.path.join(options.output_dir, f"under_{name}.png"))

  y = { "icons": icons }
  with open(os.path.join(options.output_dir, "land.yaml"), "w") as f:
    f.write(yaml.dump(y))





if __name__ == "__main__":
  main()





