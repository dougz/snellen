#!/usr/bin/python3.7

import argparse
import base64
import bs4
import configparser
import hashlib
import io
import json
import os
import zipfile

import common
import oauth2

SECRET_KEY_LENGTH = 16


class Puzzle:
  METADATA_FILE = "metadata.cfg"
  PUZZLE_HTML = "puzzle.html"
  SOLUTION_HTML = "solution.html"

  SPECIAL_FILES = {METADATA_FILE, PUZZLE_HTML, SOLUTION_HTML}

  def __init__(self, zip_data, args):
    h = hashlib.sha256()
    h.update(zip_data)
    self.prefix = base64.urlsafe_b64encode(h.digest()).decode("ascii")[:SECRET_KEY_LENGTH]

    z = zipfile.ZipFile(io.BytesIO(zip_data))
    c = configparser.ConfigParser()
    c.read_file(io.TextIOWrapper(z.open(Puzzle.METADATA_FILE)))

    cp = c["PUZZLE"]
    self.shortname = cp["shortname"]
    self.title = cp["title"]
    self.oncall = cp["oncall"]
    self.puzzletron_id = int(cp["puzzletron_id"])
    self.max_queued = cp.get("max_queued", None)

    print(f"Puzzle {self.shortname} \"{self.title}\" (prefix {self.prefix})")

    ca = c["ANSWER"]
    self.answers = list(ca.values())

    self.incorrect_responses = {}
    if "INCORRECT_RESPONSES" in c:
      for k, v in c["INCORRECT_RESPONSES"].items():
        self.incorrect_responses[k] = None if not v else v

    self.upload_assets(z, args)
    self.parse_puzzle_html(z)


  def upload_assets(self, z, args):
    self.asset_map = {}
    bucket = args.bucket

    for n in z.namelist():
      if n in self.SPECIAL_FILES: continue
      if n.endswith("/"): continue

      ext = os.path.splitext(n)[1].lower()
      if ext not in common.CONTENT_TYPES:
        raise ValueError(f"Don't know Content-Type for '{n}'.")

      path = f"puzzle/{self.prefix}/{self.shortname}/{n}"

      if not args.skip_upload:
        print(f"  Uploading {n}...")
        common.upload_object(bucket, path, common.CONTENT_TYPES[ext], z.read(n), args.credentials)

      self.asset_map[n] = f"https://{bucket}.storage.googleapis.com/{path}"

  def parse_puzzle_html(self, z):
    soup = bs4.BeautifulSoup(z.open(Puzzle.PUZZLE_HTML), features="html5lib")

    for i in soup.find_all():
      for attr in ("src", "href"):
        if attr in i.attrs:
          v = i[attr]
          vv = self.asset_map.get(v)
          if vv:
            print(f"  Rewriting <{i.name} {attr}=\"{v}\"> to {vv}")
            i[attr] = vv

    if soup.head:
      self.html_head = "".join(str(i) for i in soup.head.contents)
    else:
      self.html_head = None
    self.html_body = "".join(str(i) for i in soup.body.contents)

    if False:
      print("---- HEAD ----")
      print(self.html_head)
      print("---- BODY ----")
      print(self.html_body)

  def json_dict(self):
    d = {}
    for n in ("shortname title oncall puzzletron_id max_queued "
              "answers incorrect_responses "
              "html_head html_body ").split():
      v = getattr(self, n)
      if v is not None: d[n] = v
    return d

  def save(self, output_dir):
    with open(os.path.join(output_dir, self.shortname + ".json"), "w") as f:
      json.dump(self.json_dict(), f)


def main():
  parser = argparse.ArgumentParser(
    description="Prepare a puzzle zip file for use with the hunt server.")
  parser.add_argument("--output_dir", help="Directory for output json files.")
  parser.add_argument("--credentials", help="Private key for google cloud service account.")
  parser.add_argument("--bucket", help="Google cloud bucket to use.")
  parser.add_argument("--skip_upload", action="store_true",
                      help="Don't actually upload to GCS.")
  parser.add_argument("input_files", nargs="*",
                      help="The input .zip to process")
  args = parser.parse_args()

  args.credentials = oauth2.Oauth2Token(args.credentials)

  for zipfn in args.input_files:
    with open(zipfn, "rb") as f:
      zip_data = f.read()
      p = Puzzle(zip_data, args)
    p.save(args.output_dir)


if __name__ == "__main__":
  main()

