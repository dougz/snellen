#!/usr/bin/python3.7

import argparse
import base64
import hashlib
import json
import os
import yaml
from PIL import Image

import common
import oauth2


SECRET_KEY_LENGTH = 16

DEFAULT_BASE_IMG = "map_base.png"


def upload_file(path, options):
  ext = os.path.splitext(path)[1].lower()
  if ext not in common.CONTENT_TYPES:
    raise ValueError(f"Don't know Content-Type for '{n}'.")

  with open(path, "rb") as f:
    data = f.read()

  h = hashlib.sha256()
  h.update(data)
  name = base64.urlsafe_b64encode(h.digest()).decode("ascii")[:SECRET_KEY_LENGTH]

  target_path = f"assets/{name}{ext}"
  url = f"https://{options.public_host}/{target_path}"

  common.upload_object(options.bucket, target_path, common.CONTENT_TYPES[ext],
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

  icons = d.get("icons", None)
  if icons:
    out_icons = []
    out["icons"] = out_icons
    for ic in icons:
      oic = {"name": ic["name"],
             "pos": ic["pos"]}

      if "puzzle" in ic: oic["puzzle"] = ic["puzzle"]

      for variant in ("locked", "unlocked", "solved",
                      "unlocked_thumb", "solved_thumb"):
        icon_image = os.path.join(options.input_assets, shortname,
                                  ic["name"] + "_" + variant + ".png")
        if not os.path.exists(icon_image): continue

        if "size" not in oic:
          oic["size"] = get_image_size(icon_image)
        if variant.endswith("_thumb") and "thumb_size" not in oic:
          oic["thumb_size"] = get_image_size(icon_image)

        oic[variant] = upload_file(icon_image, options)

      # If poly isn't specified, make a rectangle covering the whole icon.
      if "poly" in ic:
        oic["poly"] = ic["poly"]
      else:
        x, y = oic["pos"]
        w, h = oic["size"]
        oic["poly"] = f"{x},{y},{x+w},{y},{x+w},{y+h},{x},{y+h}"

      out_icons.append(oic)

  return out


def convert_static_files(out, options):
  for fn in ("bin/admin-compiled.js",
             "bin/client-compiled.js",
             "static/admin.css",
             "static/event.css",
             ):
    base = os.path.basename(fn)
    out[base] = upload_file(fn, options)


def main():
  parser = argparse.ArgumentParser(
    description="Process an event yaml file and upload assets to GCS.")

  parser.add_argument("--output_file", help="Output json file.")
  parser.add_argument("--credentials", help="Private key for google cloud service account.")
  parser.add_argument("--bucket", help="Google cloud bucket to use.")
  parser.add_argument("--public_host", help="Hostname for assets in urls.")
  parser.add_argument("--skip_upload", action="store_true",
                      help="Don't actually upload to GCS.")
  parser.add_argument("--input_file", help="The input .yaml to process")
  parser.add_argument("--input_assets", help="The directory of input assets")
  options = parser.parse_args()

  options.credentials = oauth2.Oauth2Token(options.credentials)

  with open(options.input_file) as f:
    y = yaml.load(f)

  output = {"maps": {}, "static": {}}
  for shortname, d in y.items():
    output["maps"][shortname] = convert_map(shortname, d, options)

  convert_static_files(output["static"], options)


  with open(options.output_file, "w") as f:
    json.dump(output, f)





if __name__ == "__main__":
  main()

