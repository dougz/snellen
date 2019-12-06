#!/usr/bin/python3

import argparse
import json
import os
import re
import requests
import yaml

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
  parser.add_argument("map_config_yaml")

  options = parser.parse_args()
  assert options.output_dir

  options.credentials = oauth2.Oauth2Token(options.credentials)

  assert options.map_config_yaml
  puzzle_shortnames = []
  with open(options.map_config_yaml) as f:
    y = yaml.safe_load(f)
    for land, d in y.items():
      if "assignments" in d:
        print(f"Processing land {land}...")
        for dd in d["assignments"].values():
          name = dd.get("puzzle", "_")
          if name != "_":
            puzzle_shortnames.append(name)

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
      m = re.match(r"^saved/([a-z0-9_]+)/(\d{8}_\d{6})[.][^.]+[.]zip$", name)
      if not m: continue
      shortname, timestamp = m.groups()

      if shortname not in latest or timestamp > latest[shortname][0]:
        latest[shortname] = (timestamp, name)

    page_token = d.get("nextPageToken")
    if not page_token: break

  current = {}
  for f in os.listdir(options.output_dir):
    x = f.split(".")
    if len(x) == 3 and x[2] == "zip":
      current[x[0]] = x[1]

  for shortname in puzzle_shortnames:
    if shortname not in latest:
      print(f"Missing puzzle {shortname}")
      continue
    timestamp, fn = latest[shortname]

    outfn = f"{shortname}.{timestamp}.zip"
    oldts = current.get(shortname)
    if oldts == timestamp:
      print(f"Already have {shortname}.{timestamp}.zip")
      continue

    if oldts:
      oldfn = f"{shortname}.{oldts}.zip"
      print(f"Removing {oldfn}")
      os.remove(os.path.join(options.output_dir, oldfn))

    print(f"Downloading {fn} as {shortname}...")
    url = f"https://storage.googleapis.com/{options.input_bucket}/{fn}"
    r = requests.get(url, headers={"Authorization": options.credentials.get()})
    r.raise_for_status()

    with open(os.path.join(options.output_dir, outfn), "wb") as f:
      f.write(r.content)


if __name__ == "__main__":
  main()

