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



def main():
  parser = argparse.ArgumentParser(description="Uploads twemoji images to bucket")

  parser.add_argument("--base_dir", help="Directory with inputs to process.")
  parser.add_argument("--overlay_dir", help="Directory to receive output.")
  parser.add_argument("--credentials", help="Private key for google cloud service account.")
  parser.add_argument("--bucket", help="Google cloud bucket to use.")
  options = parser.parse_args()

  hunt2020_base = os.getenv("HUNT2020_BASE")
  assert hunt2020_base

  if not options.base_dir:
    options.base_dir = os.path.join(hunt2020_base, "twemoji/assets/72x72")
  if not options.overlay_dir:
    options.overlay_dir = os.path.join(hunt2020_base, "snellen/static/overlay")

  options.credentials = oauth2.Oauth2Token(options.credentials)

  already = common.load_object_cache(options.bucket, options.credentials)

  base_files = set(os.listdir(options.base_dir))
  overlay_files = set(os.listdir(options.overlay_dir))

  all_files = base_files | overlay_files

  skipped = 0
  for fn in all_files:
    if fn in overlay_files:
      src_path = os.path.join(options.overlay_dir, fn)
      if os.stat(src_path).st_size == 0:
        src_path = os.path.join(options.base_dir, fn)
    else:
      src_path = os.path.join(options.base_dir, fn)
    tgt_path = os.path.join("emoji", fn)

    with open(src_path, "rb") as f:
      data = f.read()

    h = base64.b64encode(hashlib.md5(data).digest()).decode("ascii")
    if already.get(tgt_path, None) == h:
      skipped += 1
      continue

    common.upload_object(src_path, options.bucket, tgt_path, "image/png",
                         data, options.credentials, update=True)

  print(f"Already had {skipped} emoji.")


if __name__ == "__main__":
  main()

