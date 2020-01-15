#!/usr/bin/python3.7

import argparse
import base64
import bs4
import hashlib
import io
import json
import os
import unicodedata
import yaml
import zipfile
import tornado.template
from collections import namedtuple

import common
import oauth2


class PuzzleErrors(ValueError):
  def __init__(self, errors):
    self.errors = errors

Land = namedtuple("Land", ("title", "url"))

LANDS = {
  "castle": Land("The Grand Castle", "/land/castle"),
  "forest": Land("Storybook Forest", "/land/forest"),
  "space": Land("Spaceopolis", "/land/space"),
  "hollow": Land("Wizard's Hollow", "/land/hollow"),
  "balloons": Land("Balloon Vendor", "/land/balloons"),
  "bigtop": Land("Big Top Circus", "/land/bigtop"),
  "yesterday": Land("YesterdayLand", "/land/yesterday"),
  "studios": Land("Creative Pictures Studios", "/land/studios"),
  "safari": Land("Safari Adventure", "/land/safari"),
  "cascade": Land("Cascade Bay", "/land/safari"),
  "canyon": Land("Cactus Canyon", "/land/canyon"),
  }



class Puzzle:
  METADATA_FILE = "metadata.yaml"
  PUZZLE_HTML = "puzzle.html"
  STATIC_PUZZLE_HTML = "static_puzzle.html"
  SOLUTION_HTML = "solution.html"
  FOR_OPS_HTML = "for_ops.html"

  SPECIAL_FILES = {METADATA_FILE, PUZZLE_HTML, SOLUTION_HTML, STATIC_PUZZLE_HTML, FOR_OPS_HTML}

  @classmethod
  def init_templates(cls, template_dir):
    cls.loader = tornado.template.Loader(template_dir)
    cls.T_puzzle = cls.loader.load("puzzle.html")
    cls.T_solution = cls.loader.load("solution.html")

  def __init__(self, zip_data, land, options, puzzle_dir, authors_dict, filename=None):
    self.prefix = common.hash_name(zip_data)
    z = zipfile.ZipFile(io.BytesIO(zip_data))
    self.zip_version = filename

    errors = []

    has_static = False
    metadata = []
    for n in z.namelist():
      if os.path.basename(n) == self.METADATA_FILE:
        metadata.append(n)
      if os.path.basename(n) == self.STATIC_PUZZLE_HTML:
        has_static = True
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

    self.scrum = y.get("scrum", False)

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

    emojify = False
    for a in self.answers:
      cat = unicodedata.category(a[0])
      if cat[0] != "L":
        emojify = True
        break
    self.emojify = emojify

    authors_text = authors_dict[shortname]

    # # Author(s) must be a nonempty list of nonempty strings.
    # authors = self.get_plural(y, "author", errors)
    # if authors is not None:
    #   if isinstance(authors, str):
    #     self.authors = [authors]
    #   elif isinstance(authors, list):
    #     self.authors = authors

    #   if not self.authors:
    #     errors.append("No authors given.")
    #   else:
    #     for a in self.authors:
    #       if not isinstance(a, str):
    #         errors.append(f"Author '{a}' not a string.")
    #       elif not a:
    #         errors.append(f"Author can't be an empty string.")

    self.responses = {}
    if "response" in y or "responses" in y:
      responses = self.get_plural(y, "response", errors)
      if responses is not None:
        if len(responses) == 0:
          errors.append("Response(s) is present but empty.")
        else:
          for k, v in responses.items():
            if not isinstance(k, str):
              errors.append(f"Response trigger '{k}' not a string.")
            elif not k:
              errors.append("Response trigger is empty string.")

            if v is None:
              # incorrect but "honest guess"
              self.responses[k] = None
            elif v is True:
              # also counts as correct, if there is a single answer
              if len(self.answers) != 1:
                errors.append(
                  "Alternate correct response works only with single-answer puzzles.")
              else:
                self.responses[k] = True
            elif isinstance(v, str):
              # partial progress
              self.responses[k] = v
            elif isinstance(v, dict):
              self.responses[k] = v
            else:
              errors.append(f"Bad response to '{k}'.")

    if errors: raise PuzzleErrors(errors)

    out_dir = os.path.join(puzzle_dir, shortname)
    out_url = f"/puzzle/{shortname}"
    os.makedirs(os.path.join(out_dir, "solution"), exist_ok=True)
    self.copy_assets(z, out_dir, out_url, strip_shortname)

    if "for_ops_url" in y:
      self.for_ops_url = y["for_ops_url"]
    else:
      soup = self.make_soup(z, strip_shortname, Puzzle.FOR_OPS_HTML)
      ok = True
      for t in soup.find_all():
        if t.name not in {"html", "head", "body", "a"}:
          ok = False
          break
      if ok:
        ok = (len(soup.find_all("a")) == 1)
      if not ok:
        errors.append("Replace for_ops.html with a for_ops_url.")
      else:
        a = soup.find_all("a")[0]
        self.for_ops_url = a["href"]

    self.extra = y.get("extra")

    if has_static:
      self.static_puzzle_head, self.static_puzzle_body = self.parse_html(
        z, strip_shortname, errors, Puzzle.STATIC_PUZZLE_HTML, self.asset_map)
    else:
      self.static_puzzle_head, self.static_puzzle_body = None, None

    self.html_head, self.html_body = self.parse_html(
      z, strip_shortname, errors, Puzzle.PUZZLE_HTML, self.asset_map)

    self.solution_head, self.solution_body = self.parse_html(
      z, strip_shortname, errors, Puzzle.SOLUTION_HTML, self.asset_map)

    if errors: raise PuzzleErrors(errors)

    self.land = LANDS[land]

    with open(f"{out_dir}/solution/index.html", "wb") as f:
      html = self.T_solution.generate(puzzle=self,
                                      css=["/static.css",
                                           f"/land/{land}/land.css"],
                                      script="", json_data="",
                                      solution_url="",
                                      supertitle="",
                                      authors=authors_text)
      f.write(html)

    with open(f"{out_dir}/index.html", "wb") as f:
      html = self.T_puzzle.generate(puzzle=self,
                                    css=["/static.css",
                                         f"/land/{land}/land.css"],
                                    script="", json_data="",
                                    solution_url="",
                                    supertitle="",
                                    authors="")
      f.write(html)



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


  def copy_assets(self, z, out_dir, out_url, strip_shortname):
    self.asset_map = {}

    for n in z.namelist():
      if strip_shortname:
        assert n.startswith(strip_shortname)
        nn = n[len(strip_shortname):]
        if not nn: continue
      else:
        nn = n

      if nn in self.SPECIAL_FILES: continue
      if nn.endswith("/"): continue
      #if not include_solutions and nn.startswith("solution/"): continue

      data = z.read(n)
      path = f"{out_dir}/{nn}"
      os.makedirs(os.path.dirname(path), exist_ok=True)

      with open(path, "wb") as f:
        f.write(z.read(n))

      self.asset_map[nn] = f"{out_url}/{nn}"

  def rewrite_html(self, soup, asset_map, fn, errors):
    for i in soup.find_all():
      for attr in ("src", "href", "xlink:href"):
        if attr in i.attrs:
          v = i[attr]
          if v in asset_map:
            vv = asset_map[v]
            if vv:
              #print(f"  Rewriting <{i.name} {attr}=\"{v}\"> to {vv}")
              i[attr] = vv
            else:
              errors.append(f"{fn} can't refer to {v}")

  def make_soup(self, z, strip_shortname, fn):
    if strip_shortname:
      zfn = strip_shortname + fn
    else:
      zfn = fn
    try:
      return bs4.BeautifulSoup(z.read(zfn).decode("utf-8"), features="html5lib")
    except KeyError:
      return None

  def parse_html(self, z, strip_shortname, errors, fn, asset_map):
    soup = self.make_soup(z, strip_shortname, fn)
    if not soup:
      errors.append(f"Required file {fn} is missing.")
      return None, None
    self.rewrite_html(soup, asset_map, fn, errors)
    if soup.head:
      head = "".join(str(i) for i in soup.head.contents)
    else:
      head = None
    body = "".join(str(i) for i in soup.body.contents)
    return head, body


def main():
  parser = argparse.ArgumentParser(
    description="Turn a puzzle zip into files for the post-hunt site.")
  parser.add_argument("--output_dir", help="Directory for output puzzles.")
  parser.add_argument("--authors", help="Author override file.")
  parser.add_argument("--config", help="Event config as source of puzzles.")
  parser.add_argument("input_files", nargs="*",
                      help="The input .zip files to process")
  options = parser.parse_args()

  assert os.getenv("HUNT2020_BASE")

  puzzle_dir = os.path.join(options.output_dir, "puzzle")
  os.makedirs(puzzle_dir, exist_ok=True)

  with open(options.authors) as f:
    authors = yaml.safe_load(f.read())

  Puzzle.init_templates(os.path.join(os.getenv("HUNT2020_BASE"), "snellen/tools/templates"))

  missing_authors = []
  if options.config:
    assert not options.input_files
    options.input_files = []

    pd = os.path.join(os.getenv("HUNT2020_BASE"), "bts_src/puzzles")
    fns = os.listdir(pd)
    all_puzzles = {}
    for fn in fns:
      if not fn.endswith(".zip"): continue
      all_puzzles[fn.split(".", 1)[0]] = os.path.join(pd, fn)

    with open(options.config) as f:
      cfg = yaml.safe_load(f.read())
      for n, d in cfg.items():
        if n not in LANDS: continue
        a = d.get("assignments")
        if not a: continue
        for dd in a.values():
          p = dd.get("puzzle")
          if not p: continue
          if p not in authors:
            missing_authors.append(p)
            continue
          options.input_files.append(f"{n}:{all_puzzles[p]}")

  for zipfn in options.input_files:
    land, zipfn = zipfn.split(":", 1)
    with open(zipfn, "rb") as f:
      zip_data = f.read()
      try:
        p = Puzzle(zip_data, land, options, puzzle_dir, authors, filename=os.path.basename(zipfn))
        #p.save(puzzle_dir)
      except PuzzleErrors as e:
        print(f"{zipfn} had {len(e.errors)} error(s):")
        for i, err in enumerate(e.errors):
          print(f"{i+1}: {err}")

  if missing_authors:
    print(f"missing authors: {', '.join(missing_authors)}")


if __name__ == "__main__":
  main()

