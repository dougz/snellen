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
  names = set()
  actual_count = 0

  for groupname, emojis in in_json:
    print(groupname)

    outemojis = []
    out_json.append((groupname, outemojis))

    for title, text, url in emojis:
      if title.endswith(" suit"): continue

      if not url:
        print(f"missing url for: {title}")
        continue
      fn = os.path.basename(url)
      cache_path = os.path.join(options.cache_dir, fn)
      if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
          data = f.read()
      else:
        print(f"  fetching {url}")
        r = requests.get(url)
        data = r.content
        if r.status_code == 404:
          print(f"skipping {title}")
          data = b""
        else:
          r.raise_for_status()
        with open(cache_path, "wb") as f:
          f.write(data)
      if not data: continue
      icon = Image.open(io.BytesIO(data))

      icon = icon.convert("RGBA")
      icon = icon.resize((OUTSIZE, OUTSIZE), Image.LANCZOS)

      out.paste(icon, (x_pos*OUTSIZE, y_pos*OUTSIZE))

      if title in names:
        print(f"duplicate: {title}")
      names.add(title)
      outemojis.append((title, text, x_pos, y_pos))
      actual_count += 1

      x_pos += 1
      if x_pos >= WIDTH:
        x_pos = 0
        y_pos += 1

  rows = y_pos+1 if x_pos else y_pos
  out = out.crop((0, 0, OUTSIZE*WIDTH, OUTSIZE*rows))
  print(f"trimmed to {out.size}")
  print(f"outputting {actual_count} emojis")

  out.save(options.output_png)
  with open(options.output_json, "w") as f:
    json.dump(out_json, f)



if __name__ == "__main__":
  main()

