#!/usr/bin/python3

import argparse
import io
import json
import os
import requests

from PIL import Image

def main():
  # emoji are scaled to this many pixels square.
  OUTSIZE = 40

  # The output image has this many columns of emoji.
  WIDTH = 40

  parser = argparse.ArgumentParser(
    description="Join emoji image into sprite.")
  parser.add_argument("--cache_dir",
                      default=os.path.join(os.getenv("HUNT2020_BASE"),
                                           "snellen/assets/emoji_cache"),
                      help="Directory for caching downloaded source emoji.")
  parser.add_argument("input_json")
  parser.add_argument("output_json")
  parser.add_argument("output_png")
  options = parser.parse_args()

  with open(options.input_json) as f:
    in_json = json.load(f)

  count = 0
  for groupname, emojis in in_json:
    for _, _, url in emojis:
      if url:
        count += 1
  print(f"Combining {count} emojis.")

  rows = (count-1) // WIDTH + 1
  out = Image.new("RGBA", (WIDTH * OUTSIZE, rows * OUTSIZE))
  print(f"Output image will be {out.size[0]} x {out.size[1]}.")

  x_pos = 0
  y_pos = 0

  out_json = []

  for groupname, emojis in in_json:
    print(groupname)

    outemojis = []
    out_json.append((groupname, outemojis))

    for title, text, url in emojis:
      if not url:
        outemojis.append((title, text))
        continue
      fn = os.path.basename(url)
      cache_path = os.path.join(options.cache_dir, fn)
      if os.path.exists(cache_path):
        icon = Image.open(cache_path)
      else:
        print(f"  fetching {url}")
        r = requests.get(url)
        r.raise_for_status()
        with open(cache_path, "wb") as f:
          f.write(r.content)
        icon = Image.open(io.BytesIO(r.content))

      icon = icon.convert("RGBA")
      icon = icon.resize((OUTSIZE, OUTSIZE), Image.LANCZOS)

      out.paste(icon, (x_pos*OUTSIZE, y_pos*OUTSIZE))
      outemojis.append((title, text, x_pos, y_pos))

      x_pos += 1
      if x_pos >= WIDTH:
        x_pos = 0
        y_pos += 1


  out.save(options.output_png)
  with open(options.output_json, "w") as f:
    json.dump(out_json, f)



if __name__ == "__main__":
  main()

