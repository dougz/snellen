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
  parser.add_argument("--base_dir", help="Directory with inputs to process.")
  parser.add_argument("--overlay_dir", help="Directory to receive output.")
  parser.add_argument("input_json")
  parser.add_argument("output_json")
  parser.add_argument("output_png")
  options = parser.parse_args()

  hunt2020_base = os.getenv("HUNT2020_BASE")
  assert hunt2020_base

  if not options.base_dir:
    options.base_dir = os.path.join(hunt2020_base, "twemoji/assets/72x72")
  if not options.overlay_dir:
    options.overlay_dir = os.path.join(hunt2020_base, "snellen/static/overlay")

  all_files = set(os.listdir(options.base_dir))
  overlay_files = set(os.listdir(options.overlay_dir))

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

    for title, text, _ in emojis:
      if title.endswith(" suit"): continue

      fn = "-".join(f"{ord(k):x}" for k in text) + ".png"
      print(text, fn)

      if fn in overlay_files:
        src_fn = os.path.join(options.overlay_dir, fn)
      elif fn in all_files:
        src_fn = os.path.join(options.base_dir, fn)
      else:
        print(f"No input {fn}.")
        continue

      if os.stat(src_fn).st_size == 0: continue

      icon = Image.open(src_fn)

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
    json.dump(out_json, f, separators=",:")



if __name__ == "__main__":
  main()

