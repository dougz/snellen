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

DEFAULT_BASE_IMG = "map_base.png"


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
  if "symbol" in d:
    out["symbol"] = d["symbol"]
  if "land_order" in d:
    out["land_order"] = d["land_order"]
  print(f"Parsing {shortname} \"{d['title']}\"...")

  base_img = os.path.join(options.input_assets, shortname,
                          d.get("base_img", DEFAULT_BASE_IMG))
  out["base_size"] = get_image_size(base_img)
  out["base_img"] = upload_file(base_img, options)

  if "logo" in d:
    src_image = os.path.join(options.input_assets, shortname,
                             d["logo"])
    url = upload_file(src_image, options)
    out["logo"] = url

  if "order" in d:
    out["order"] = d["order"]
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

      for variant in ("locked", "unlocked", "solved",
                      "unlocked_thumb", "solved_thumb",
                      "unlocked_mask", "solved_mask"):
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
      return out.get(m.group(1), m.group(1))
    text = re.sub(r"@@STATIC:([^@]+)@@", replacer, text)
    return text.encode("utf-8")

  base = os.path.join(os.getenv("HUNT2020_BASE"), "snellen")

  to_convert = []

  for land in lands:
    land_dir = os.path.join(options.input_assets, land)
    for fn in os.listdir(land_dir):
      if fn.startswith("land_") and fn.endswith(".png"):
        to_convert.append((os.path.join(land, fn), os.path.join(land_dir, fn)))

    for xfn in ("land.css", "solve.mp3"):
      fn = os.path.join(options.input_assets, land, xfn)
      if os.path.exists(fn):
        to_convert.append((os.path.join(land, xfn), fn))

  to_convert.extend([("mute.png", f"{base}/static/mute.png"),
                     ("emojisprite.png", f"{base}/static/emojisprite.png"),
                     ("admin-compiled.js", f"{base}/bin/admin-compiled.js"),
                     ("client-compiled.js", f"{base}/bin/client-compiled.js"),
                     ("admin.css", f"{base}/static/admin.css"),
                     ("event.css", f"{base}/static/event.css"),
                     ("login.css", f"{base}/static/login.css"),
                     ("notopen.css", f"{base}/static/notopen.css"),
                     ("logo.png", f"{base}/static/logo.png"),
                     ("emoji.json", f"{base}/static/emoji.json"),
                     ])

  for fn in os.listdir(os.path.join(options.input_assets, "achievements")):
    if not fn.endswith(".png"): continue
    base = os.path.basename(fn)
    to_convert.append((os.path.join("achievements", base),
                       os.path.join(options.input_assets, "achievements", fn)))

  for key, fn in to_convert:
    processor = css_processor if fn.endswith(".css") else None
    out[key] = upload_file(fn, options, processor=processor)


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
  parser.add_argument("--static_only", action="store_true",
                      help="Don't process map; just upload static assets.")
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
    print(f"Loading assets/{land}/land.yaml...")
    with open(os.path.join(options.input_dir, "assets", land, "land.yaml")) as f:
      y[land].update(yaml.safe_load(f))

  output_file = os.path.join(options.output_dir, "map_config.json")

  if options.static_only:
    with open(output_file) as f:
      output = json.load(f)
  else:
    output = {}

  if not options.static_only:
    output["maps"] = {}
    for shortname, d in y.items():
      output["maps"][shortname] = convert_map(shortname, d, options)

  output["static"] = {}
  convert_static_files(output["static"], options, output["maps"].keys())

  with open(output_file, "w") as f:
    json.dump(output, f, sort_keys=True, indent=2)


if __name__ == "__main__":
  main()

