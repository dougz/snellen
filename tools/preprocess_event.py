#!/usr/bin/python3.7

import argparse
import base64
import hashlib
import json
import re
import os
import yaml
from PIL import Image

import common
import oauth2


SECRET_KEY_LENGTH = 16

BASE_IMG = "map_base{}.png"


def upload_file(path, options, processor=None):
  ext = os.path.splitext(path)[1].lower()
  if ext not in common.CONTENT_TYPES:
    raise ValueError(f"Don't know Content-Type for '{path}'.")

  with open(path, "rb") as f:
    data = f.read()

  if processor: data = processor(data)

  h = hashlib.sha256()
  h.update(data)
  name = base64.urlsafe_b64encode(h.digest()).decode("ascii")[:SECRET_KEY_LENGTH]

  target_path = f"{name}{ext}"
  url = f"https://{options.public_host}/{target_path}"

  common.upload_object(path, options.bucket, target_path, common.CONTENT_TYPES[ext],
                       data, options.credentials)
  return url


def get_image_size(path):
  im = Image.open(path)
  return im.size


def convert_map(shortname, d, options):
  out = {"title": d["title"]}
  def copyif(k):
    if k in d: out[k] = d[k]
  copyif("symbol")
  copyif("land_order")
  copyif("color")
  copyif("guess_interval")
  copyif("guess_max")
  copyif("open_at")
  copyif("initial_puzzles")
  copyif("order")
  copyif("additional_order")
  copyif("base_min_puzzles")
  print(f"Parsing {shortname} \"{d['title']}\"...")

  base_img = os.path.join(options.input_assets, shortname,
                          BASE_IMG.format(""))
  if os.path.exists(base_img):
    out["base_size"] = get_image_size(base_img)
    out["base_img"] = upload_file(base_img, options)
  else:
    i = 0
    out["base_size"] = []
    out["base_img"] = []
    while True:
      base_img = os.path.join(options.input_assets, shortname,
                              BASE_IMG.format(i))
      if not os.path.exists(base_img): break
      out["base_size"].append(get_image_size(base_img))
      out["base_img"].append(upload_file(base_img, options))
      i += 1

  assert out["base_img"]

  if "logo" in d:
    src_image = os.path.join(options.input_assets, shortname,
                             d["logo"])
    url = upload_file(src_image, options)
    out["logo"] = url

  assignments = d.get("assignments", {})
  if assignments:
    out["assignments"] = assignments

  icons = d.get("icons", None)
  if icons:
    out_icons = {}
    out["icons"] = out_icons
    for name, ic in icons.items():
      oic = {}
      out_icons[name] = oic

      if name in assignments and "headerimage" in assignments[name]:
        src = os.path.join(options.input_assets, shortname,
                           assignments[name]["headerimage"])
        oic["headerimage"] = upload_file(src, options)

      for variant in ("locked", "solved", "solved_mask", "under"):
        icon_image = os.path.join(options.input_assets, shortname,
                                  name + "_" + variant + ".png")
        if not os.path.exists(icon_image): continue

        voic = dict(ic[variant])
        oic[variant] = voic
        voic["url"] = upload_file(icon_image, options)

        # If poly isn't specified, make a rectangle covering the whole icon.
        if "poly" not in voic and "pos" in voic:
          x, y = voic["pos"]
          w, h = voic["size"]
          voic["poly"] = f"{x},{y},{x+w},{y},{x+w},{y+h},{x},{y+h}"

  return out


def convert_static_files(out, options, lands):
  print("Processing static assets...")

  def css_processor(data):
    text = data.decode("utf-8")
    def replacer(m):
      return out.get(m.group(1), m.group(1))[0]
    text = re.sub(r"@@STATIC:([^@]+)@@", replacer, text)
    return text.encode("utf-8")

  base = os.getenv("HUNT2020_BASE")
  absbase = os.path.abspath(base) + "/"

  to_convert = []

  for land in lands:
    land_dir = os.path.join(options.input_assets, land)
    for fn in os.listdir(land_dir):
      if fn.startswith("land_") and fn.endswith(".png"):
        to_convert.append((os.path.join(land, fn), os.path.join(land_dir, fn)))

    for xfn in ("land.css", "solve.mp3", "fastpass.png"):
      fn = os.path.join(options.input_assets, land, xfn)
      if os.path.exists(fn):
        to_convert.append((os.path.join(land, xfn), fn))

  to_convert.extend([("mute.png", f"{base}/snellen/static/mute.png"),
                     ("emojisprite.png", f"{base}/snellen/static/emojisprite.png"),
                     ("pennypass.png", f"{base}/snellen/static/pennypass.png"),
                     ("ppicon1.png", f"{base}/snellen/static/ppicon1.png"),
                     ("ppicon2.png", f"{base}/snellen/static/ppicon2.png"),
                     ("ppicon3.png", f"{base}/snellen/static/ppicon3.png"),
                     ("admin-compiled.js", f"{base}/snellen/bin/admin-compiled.js"),
                     ("client-compiled.js", f"{base}/snellen/bin/client-compiled.js"),
                     ("admin.css", f"{base}/snellen/static/admin.css"),
                     ("event.css", f"{base}/snellen/static/event.css"),
                     ("default.css", f"{base}/snellen/static/default.css"),
                     ("login.css", f"{base}/snellen/static/login.css"),
                     ("notopen.css", f"{base}/snellen/static/notopen.css"),
                     ("logo.png", f"{base}/snellen/static/logo.png"),
                     ("logo-nav.png", f"{base}/snellen/static/logo-nav.png"),
                     ("emoji.json", f"{base}/snellen/static/emoji.json"),
                     ("video1.mp4", f"{base}/media/video1.mp4"),
                     ("video2.mp4", f"{base}/media/video2.mp4"),
                     ("video3.mp4", f"{base}/media/video3.mp4"),
                     ("video4.mp4", f"{base}/media/video4.mp4"),
                     ("video5.mp4", f"{base}/media/video5.mp4"),
                     ("thumb1.png", f"{base}/media/thumb1.png"),
                     ("thumb2.png", f"{base}/media/thumb2.png"),
                     ("thumb3.png", f"{base}/media/thumb3.png"),
                     ("thumb4.png", f"{base}/media/thumb4.png"),
                     ("thumb5.png", f"{base}/media/thumb5.png"),
                     ("admin_fav_green/favicon-32x32.png",
                      f"{base}/snellen/static/admin_fav_green/favicon-32x32.png"),
                     ("admin_fav_green/favicon-16x16.png",
                      f"{base}/snellen/static/admin_fav_green/favicon-16x16.png"),
                     ("admin_fav_amber/favicon-32x32.png",
                      f"{base}/snellen/static/admin_fav_amber/favicon-32x32.png"),
                     ("admin_fav_amber/favicon-16x16.png",
                      f"{base}/snellen/static/admin_fav_amber/favicon-16x16.png"),
                     ("admin_fav_red/favicon-32x32.png",
                      f"{base}/snellen/static/admin_fav_red/favicon-32x32.png"),
                     ("admin_fav_red/favicon-16x16.png",
                      f"{base}/snellen/static/admin_fav_red/favicon-16x16.png"),
                     ])

  for fn in os.listdir(os.path.join(options.input_assets, "achievements")):
    if not fn.endswith(".png"): continue
    base = os.path.basename(fn)
    to_convert.append((os.path.join("achievements", base),
                       os.path.join(options.input_assets, "achievements", fn)))

  # Process .css files last.
  to_convert.sort(key=lambda x: (1 if x[0].endswith(".css") else 0, x[0]))

  for key, fn in to_convert:
    processor = css_processor if fn.endswith(".css") else None

    outfn = os.path.abspath(fn)
    assert outfn.startswith(absbase)
    outfn = outfn[len(absbase):]

    out[key] = (upload_file(fn, options, processor=processor), outfn)


def main():
  parser = argparse.ArgumentParser(
    description="Process an event yaml file and upload assets to GCS.")

  parser.add_argument("--input_dir", help="Directory with inputs to process.")
  parser.add_argument("--output_dir", help="Directory to receive output.")
  parser.add_argument("--credentials", help="Private key for google cloud service account.")
  parser.add_argument("--bucket", help="Google cloud bucket to use.")
  parser.add_argument("--public_host", help="Hostname for assets in urls.")
  parser.add_argument("--skip_upload", action="store_true",
                      help="Don't actually upload to GCS.")
  options = parser.parse_args()

  assert os.getenv("HUNT2020_BASE")

  options.input_assets = os.path.join(options.input_dir, "assets")
  if not options.public_host:
    options.public_host = options.bucket + ".storage.googleapis.com"

  options.credentials = oauth2.Oauth2Token(options.credentials)

  common.load_object_cache(options.bucket, options.credentials)

  print("Loading map_config.yaml...")
  with open(os.path.join(options.input_dir, "map_config.yaml")) as f:
    y = yaml.safe_load(f)

  for land in y.keys():
    if land in ("events", "workshop", "runaround"): continue
    print(f"Loading assets/{land}/land.yaml...")
    with open(os.path.join(options.input_dir, "assets", land, "land.yaml")) as f:
      y[land].update(yaml.safe_load(f))

  output_file = os.path.join(options.output_dir, "map_config.json")

  output = {}

  output["maps"] = {}
  for shortname, d in y.items():
    if shortname in ("events", "workshop", "runaround"): continue
    output["maps"][shortname] = convert_map(shortname, d, options)

  output["static"] = {}
  convert_static_files(output["static"], options, output["maps"].keys())

  output["static"]["emoji"] = f"https://{options.public_host}/emoji/"

  output["events"] = y.get("events", {})
  output["workshop"] = y.get("workshop", {})
  output["runaround"] = y.get("runaround", {})

  with open(output_file, "w") as f:
    json.dump(output, f, sort_keys=True, indent=2)


if __name__ == "__main__":
  main()

