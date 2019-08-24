#!/usr/bin/python3

import argparse
import base64
import io
import os
import requests
import zipfile

BASIC_AUTH = b"Basic " + base64.b64encode(b"leftout:left13r")

def main():
  parser = argparse.ArgumentParser(
    description=("Turn a directory into a zip and upload it to "
                 "the preview server."))
  parser.add_argument("--preview_server", default="preview.isotropic.org")
  parser.add_argument("--local_zip", default=None)
  parser.add_argument("input_dir")
  options = parser.parse_args()

  temp = io.BytesIO()
  with zipfile.ZipFile(temp, mode="w") as z:
    for dirpath, dirnames, filenames in os.walk(options.input_dir):
      relpath = dirpath[len(options.input_dir):].lstrip("/")
      d = os.path.basename(relpath)
      if d == ".git": continue
      if d.startswith("__OSX"): continue
      for fn in filenames:
        with open(os.path.join(dirpath, fn), "rb") as f:
          z.writestr(os.path.join(relpath, fn), f.read())
  temp = temp.getbuffer()

  if options.local_zip:
    with open(options.local_zip, "wb") as f:
      f.write(temp)

  r = requests.post(f"https://{options.preview_server}/upload",
                    headers={"Authorization": BASIC_AUTH},
                    files={"zip": temp})
  if r.status_code != 200:
    print(f"upload failed: {r}")
    return

  if r.url.endswith("error.txt"):
    print("server reported errors:")
    print(r.content.decode("utf-8"))
    return

  print(f"puzzle metadata page: {r.url}")
  puzzle_page = r.url.replace("meta.html", "puzzle.html")
  print(f"         puzzle page: {puzzle_page}")

if __name__ == "__main__":
  main()
