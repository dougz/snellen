#!/usr/bin/python3.7

import argparse
import base64
import bs4
import hashlib
import io
import json
import os
import yaml
import zipfile

import common
import oauth2

SECRET_KEY_LENGTH = 16


class PuzzleErrors(ValueError):
  def __init__(self, errors):
    self.errors = errors


class Puzzle:
  METADATA_FILE = "metadata.yaml"
  PUZZLE_HTML = "puzzle.html"
  STATIC_PUZZLE_HTML = "static_puzzle.html"
  SOLUTION_HTML = "solution.html"

  SPECIAL_FILES = {METADATA_FILE, PUZZLE_HTML, SOLUTION_HTML, STATIC_PUZZLE_HTML}

  def __init__(self, zip_data, options, include_solutions=False):
    h = hashlib.sha256()
    h.update(zip_data)
    self.prefix = base64.urlsafe_b64encode(h.digest()).decode("ascii")[:SECRET_KEY_LENGTH]

    z = zipfile.ZipFile(io.BytesIO(zip_data))

    errors = []

    metadata = []
    for n in z.namelist():
      if os.path.basename(n) == self.METADATA_FILE:
        metadata.append(n)
    if len(metadata) == 0:
      errors.append(f"No {self.METADATA_FILE} file found.")
    elif len(metadata) > 1:
      errors.append(f"Multiple {self.METADATA_FILE} files found:\n  " + "\n  ".join(metadata))

    if errors: raise PuzzleErrors(errors)
    metadata = metadata[0]

    try:
      y = yaml.load(z.read(metadata).decode("utf-8"))
    except yaml.YAMLError as e:
      raise PuzzleErrors([f"Error parsing {self.METADATA_FILE}:\n{e}"])

    shortname = y.get("shortname")
    if not shortname:
      errors.append("Missing or empty shortname.")

    if metadata == self.METADATA_FILE:
      strip_shortname = None
    elif metadata == os.path.join(shortname, self.METADATA_FILE):
      for n in z.namelist():
        if not n.startswith(shortname+"/"):
          errors.append(f"If shortname directory is used, everything must be in it.")
          break
      strip_shortname = shortname + "/"
    else:
      errors.append(f"Metadata path {metadata} doesn't match shortname.")

    if errors: raise PuzzleErrors(errors)

    self.shortname = shortname

    self.title = y.get("title")
    if not self.title:
      errors.append("Missing or empty title.")
    elif not isinstance(self.title, str):
      errors.append("title is not a string.")

    self.oncall = y.get("oncall")
    if not self.oncall:
      errors.append("Missing or empty oncall.")
    elif not isinstance(self.oncall, str):
      errors.append("oncall is not a string.")

    self.puzzletron_id = y.get("puzzletron_id")
    if not self.puzzletron_id:
      errors.append("Missing or empty puzzletron_id.")
    elif not isinstance(self.puzzletron_id, int):
      errors.append("puzzletron_id is not an integer.")

    self.max_queued = y.get("max_queued")
    if self.max_queued is not None and not isinstance(self.max_queued, int):
      errors.append("max_queued is not an integer.")

    print(f"Puzzle {self.shortname} \"{self.title}\" (prefix {self.prefix})")

    # Answer(s) must be a nonempty list of nonempty strings.
    answers = self.get_plural(y, "answer", errors)
    if answers is not None:
      if isinstance(answers, str):
        self.answers = [answers]
      elif isinstance(answers, list):
        self.answers = answers

      if not self.answers:
        errors.append("No answers given.")
      else:
        for a in self.answers:
          if not isinstance(a, str):
            errors.append(f"Answer '{a}' not a string.")
          elif not a:
            errors.append(f"Answer can't be an empty string.")
          if a != a.upper():
            errors.append(f"Answers must be uppercase.")

    # Author(s) must be a nonempty list of nonempty strings.
    authors = self.get_plural(y, "author", errors)
    if authors is not None:
      if isinstance(authors, str):
        self.authors = [authors]
      elif isinstance(authors, list):
        self.authors = authors

      if not self.authors:
        errors.append("No authors given.")
      else:
        for a in self.authors:
          if not isinstance(a, str):
            errors.append(f"Author '{a}' not a string.")
          elif not a:
            errors.append(f"Author can't be an empty string.")

    self.incorrect_responses = {}
    if "response" in y or "responses" in y:
      responses = self.get_plural(y, "response", errors)
      if responses is not None:
        if len(responses) == 0:
          errors.append("Response(s) is present but empty.")
        else:
          for k, v in responses.items():
            if not isinstance(k, str):
              errors.append("Response trigger '{k}' not a string.")
            elif not k:
              errors.append("Response trigger is empty string.")
            if v is None:
              pass
            elif not isinstance(v, str):
              errors.append("Response '{v}' not a string.")
            elif not v:
              errors.append("Response to '{k}' is empty string.")
          self.incorrect_responses = responses

    if errors: raise PuzzleErrors(errors)

    self.upload_assets(z, options, include_solutions, strip_shortname)
    self.parse_puzzle_html(z, strip_shortname)
    if include_solutions:
      self.parse_solution_html(z, strip_shortname)

  @staticmethod
  def get_plural(y, name, errors):
    plural = name + "s"
    if name in y and plural in y:
      errors.append(f"Can't specify both '{name}' and '{plural}'.")
      return
    value = y.get(name)
    if value is None:
      value = y.get(plural)
    if value is None:
      errors.append(f"Must specify {name}(s).")
      return
    return value


  def upload_assets(self, z, options, include_solutions, strip_shortname):
    self.asset_map = {}
    bucket = options.bucket

    for n in z.namelist():
      if strip_shortname:
        assert n.startswith(strip_shortname)
        nn = n[len(strip_shortname):]
        if not nn: continue
      else:
        nn = n

      if nn in self.SPECIAL_FILES: continue
      if nn.endswith("/"): continue
      if not include_solutions and nn.startswith("solution/"): continue

      ext = os.path.splitext(nn)[1].lower()
      if ext not in common.CONTENT_TYPES:
        raise ValueError(f"Don't know Content-Type for '{nn}'.")

      path = f"puzzle/{self.prefix}/{self.shortname}/{nn}"

      if not options.skip_upload:
        common.upload_object(nn, bucket, path, common.CONTENT_TYPES[ext], z.read(n), options.credentials)

      self.asset_map[nn] = f"https://{options.public_host}/{path}"

  def rewrite_html(self, soup):
    for i in soup.find_all():
      for attr in ("src", "href"):
        if attr in i.attrs:
          v = i[attr]
          vv = self.asset_map.get(v)
          if vv:
            print(f"  Rewriting <{i.name} {attr}=\"{v}\"> to {vv}")
            i[attr] = vv

  def parse_puzzle_html(self, z, strip_shortname):
    fn = Puzzle.PUZZLE_HTML
    if strip_shortname:
      fn = strip_shortname + fn
    soup = bs4.BeautifulSoup(z.read(fn).decode("utf-8"), features="html5lib")
    self.rewrite_html(soup)
    if soup.head:
      self.html_head = "".join(str(i) for i in soup.head.contents)
    else:
      self.html_head = None
    self.html_body = "".join(str(i) for i in soup.body.contents)

  def parse_solution_html(self, z, strip_shortname):
    fn = Puzzle.SOLUTION_HTML
    if strip_shortname:
      fn = strip_shortname + fn
    soup = bs4.BeautifulSoup(z.open(fn), features="html5lib")
    self.rewrite_html(soup)
    if soup.head:
      self.solution_head = "".join(str(i) for i in soup.head.contents)
    else:
      self.solution_head = None
    self.solution_body = "".join(str(i) for i in soup.body.contents)

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
      json.dump(self.json_dict(), f, sort_keys=True, indent=2)
    with open(os.path.join(output_dir, self.shortname + ".assets.json"), "w") as f:
      json.dump(self.asset_map, f, sort_keys=True, indent=2)



def main():
  parser = argparse.ArgumentParser(
    description="Prepare a puzzle zip file for use with the hunt server.")
  parser.add_argument("--output_dir", help="Directory for output json files.")
  parser.add_argument("--credentials", help="Private key for google cloud service account.")
  parser.add_argument("--bucket", help="Google cloud bucket to use.")
  parser.add_argument("--public_host", help="Hostname for assets in urls.")
  parser.add_argument("--skip_upload", action="store_true",
                      help="Don't actually upload to GCS.")
  parser.add_argument("input_files", nargs="*",
                      help="The input .zip to process")
  options = parser.parse_args()

  options.credentials = oauth2.Oauth2Token(options.credentials)
  if not options.public_host:
    options.public_host = options.bucket + ".storage.googleapis.com"

  puzzle_dir = os.path.join(options.output_dir, "puzzles")
  os.makedirs(puzzle_dir, exist_ok=True)

  for zipfn in options.input_files:
    with open(zipfn, "rb") as f:
      zip_data = f.read()
      try:
        p = Puzzle(zip_data, options)
        p.save(puzzle_dir)
      except PuzzleErrors as e:
        print(f"{zipfn} had {len(e.errors)} error(s):")
        for i, err in enumerate(e.errors):
          print(f"{i+1}: {err}")


if __name__ == "__main__":
  main()

