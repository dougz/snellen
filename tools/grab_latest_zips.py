#!/usr/bin/python3

import argparse
import json
import os
import re
import requests

import oauth2

def main():
  parser = argparse.ArgumentParser(
    description="Grab latest zips from preview bucket.")

  parser.add_argument("--input_bucket",
                      default="snellen-prod-zip",
                      help="Bucket where zips are saved.")
  parser.add_argument("--output_dir",
                      help="Where to wriet latest zips.")
  parser.add_argument("--credentials", help="Private key for google cloud service account.")
  parser.add_argument("puzzle_shortnames", nargs="*",
                      help="The input .zip to process")

  options = parser.parse_args()
  assert options.output_dir

  options.credentials = oauth2.Oauth2Token(options.credentials)
  options.puzzle_shortnames = set(options.puzzle_shortnames)

  latest = {}

  page_token = None
  while True:
    url = f"https://www.googleapis.com/storage/v1/b/{options.input_bucket}/o"
    if page_token:
      url += f"?pageToken={page_token}"

    r = requests.get(url, headers={"Authorization": options.credentials.get()})
    if r.status_code == 401:
      options.credentials.invalidate()
      continue
    if r.status_code != 200:
      r.raise_for_status()

    d = json.loads(r.content)
    for i in d["items"]:
      name = i["name"]
      if not name.endswith(".zip"): continue
      m = re.match(r"(?:.*/)?([a-z0-9_]+)/(\d{8}_\d{6})[.][^.]+[.][^.]+[.]zip$", name)
      if not m: continue
      shortname, timestamp = m.groups()

      if options.puzzle_shortnames and shortname not in options.puzzle_shortnames:
        continue

      if shortname not in latest or timestamp > latest[shortname][0]:
        latest[shortname] = (timestamp, name)

    page_token = d.get("nextPageToken")
    if not page_token: break

  for shortname, (_, fn) in latest.items():
    print(f"Downloading {shortname}...")
    url = f"https://storage.googleapis.com/{options.input_bucket}/{fn}"
    r = requests.get(url, headers={"Authorization": options.credentials.get()})
    r.raise_for_status()

    with open(os.path.join(options.output_dir, shortname + ".zip"), "wb") as f:
      f.write(r.content)


if __name__ == "__main__":
  main()

