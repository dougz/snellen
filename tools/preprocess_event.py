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
    raise ValueError(f"Don't know Content-Type for '{n}'.")

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

  icons = d.get("icons", None)
  if icons:
    out_icons = []
    out["icons"] = out_icons
    for ic in icons:
      oic = {"name": ic["name"]}

      if "puzzle" in ic: oic["puzzle"] = ic["puzzle"]

      if "headerimage" in ic:
        src = os.path.join(options.input_assets, shortname,
                           ic["headerimage"])
        oic["headerimage"] = upload_file(src, options)

      for variant in ("locked", "unlocked", "solved",
                      "unlocked_thumb", "solved_thumb"):
        icon_image = os.path.join(options.input_assets, shortname,
                                  ic["name"] + "_" + variant + ".png")
        if not os.path.exists(icon_image): continue

        voic = dict(ic[variant])
        oic[variant] = voic
        voic["url"] = upload_file(icon_image, options)

        # If poly isn't specified, make a rectangle covering the whole icon.
        if "poly" not in voic and "pos" in voic:
          x, y = voic["pos"]
          w, h = voic["size"]
          voic["poly"] = f"{x},{y},{x+w},{y},{x+w},{y+h},{x},{y+h}"

      out_icons.append(oic)

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
    fn = os.path.join(options.input_assets, land, "land.css")
    if os.path.exists(fn):
      to_convert.append((os.path.join(land, "land.css"), fn))

  to_convert.extend([("mute.png", f"{base}/static/mute.png"),
                     ("admin-compiled.js", f"{base}/bin/admin-compiled.js"),
                     ("client-compiled.js", f"{base}/bin/client-compiled.js"),
                     ("admin.css", f"{base}/static/admin.css"),
                     ("event.css", f"{base}/static/event.css"),
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

  with open(os.path.join(options.input_dir, "map_config.yaml")) as f:
    y = yaml.load(f)

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

