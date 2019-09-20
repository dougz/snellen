#!/usr/bin/python3

import argparse
import asyncio
import base64
from collections import namedtuple
import hashlib
import json
import os
import re
import requests
import time
import tornado.ioloop
import tornado.httpserver
import tornado.netutil
import tornado.template
import tornado.web
import traceback

import common
import oauth2

import preprocess_puzzle as ppp


class Team:
  name = "Team Name Here"
  score = 0


class Land:
  url = ""
  title = "Some Land"


SAVED_PUZZLES = {}

SavedPuzzle = namedtuple("SavedPuzzle", ("timestamp", "who", "puzzle_url", "meta_url"))


class Puzzle:
  NEXT_PID = 1
  BY_PID = {}

  def __init__(self):
    self.pid = Puzzle.NEXT_PID
    Puzzle.NEXT_PID += 1
    Puzzle.BY_PID[self.pid] = self

  def process(self, zip_data):
    h = hashlib.md5(zip_data).digest()
    h = base64.urlsafe_b64encode(h).decode("ascii")
    assert h[-2:] == "=="
    self.prefix = h[:-2]
    self.pp = ppp.Puzzle(zip_data, self.options, include_solutions=True)
    self.pp.land = Land


class PreviewPage(tornado.web.RequestHandler):
  def get(self):
    self.render("preview.html")


class SavedPage(tornado.web.RequestHandler):
  def get(self):
    self.render("saved_prod_zip.html", puzzles=SAVED_PUZZLES)

class UploadHandler(tornado.web.RequestHandler):
  LAND_NAMES = {"castle": "The Grand Castle",
                "forest": "Enchanted Forest",
                "space": "Spaceopolis",
                }

  def initialize(self, options):
    self.options = options

  def post(self):
    p = Puzzle()

    save = self.get_body_argument("save", False)

    css = [self.static_content["event.css"]]
    land = self.get_body_argument("land", None)
    if land and land != "none":
      path = f"{land}/land.css"
      if path in self.static_content:
        css.append(self.static_content[path])
    landobj = Land()
    landobj.title = self.LAND_NAMES.get(land, "Some Land")

    d = {"script": None,
         "json_data": None,
         "park_open": True,
         "css": css,
         "supertitle": ""}

    if land == "space":
      d["supertitle"] = ('<img src="https://preview-static.storage.googleapis.com/'
                         '83u3b9EB5Yyruqc9.png">')

    who = self.get_body_argument("who", "")

    who = who.lower()
    who = re.sub(r"[^a-z0-9_]+", "", who)

    if save and not who:
      p.error_msg = "Must enter your name if saving for the hunt server."
      self.redirect(f"/error/{p.pid}")
      return

    if save:
      timestamp = time.strftime("%Y%m%d_%H%M%S")

    try:
      zip_data = self.request.files["zip"][0]["body"]
      p.process(zip_data)

      authors = p.pp.authors
      if len(authors) == 1:
        authors = authors[0]
      elif len(authors) == 2:
        authors = f"{authors[0]} and {authors[1]}"
      else:
        authors = ", ".join(authors[:-1] + ["and " + authors[-1]])

      p.pp.land = landobj
      d.update({"puzzle": p.pp,
                "team": Team})

      path = f"html/{p.prefix}/solution.html"
      puzzle_html = self.render_string("solution_frame.html",
                                       solution_url=None,
                                       authors=authors,
                                       **d)
      common.upload_object("solution.html",
                           self.options.bucket, path,
                           common.CONTENT_TYPES[".html"],
                           puzzle_html, self.options.credentials, update=True)

      p.solution_url = f"https://{self.options.public_host}/{path}"

      path = f"html/{p.prefix}/puzzle.html"
      puzzle_html = self.render_string("solution_frame.html",
                                       solution_url=p.solution_url,
                                       authors=None,
                                       **d)
      common.upload_object("puzzle.html",
                           self.options.bucket, path,
                           common.CONTENT_TYPES[".html"],
                           puzzle_html, self.options.credentials, update=True)

      p.puzzle_url = f"https://{self.options.public_host}/{path}"

      path = f"html/{p.prefix}/for_ops.html"
      puzzle_html = self.render_string("preview_for_ops.html",
                                       **d)
      common.upload_object("for_ops.html",
                           self.options.bucket, path,
                           common.CONTENT_TYPES[".html"],
                           puzzle_html, self.options.credentials, update=True)

      p.for_ops_url = f"https://{self.options.public_host}/{path}"

      path = f"html/{p.prefix}/meta.html"
      meta_html = self.render_string("meta.html",
                                     puzzle_url=p.puzzle_url,
                                     solution_url=p.solution_url,
                                     for_ops_url=p.for_ops_url,
                                     puzzle=p.pp)
      common.upload_object("meta.html",
                           self.options.bucket, path,
                           common.CONTENT_TYPES[".html"],
                           meta_html, self.options.credentials, update=True)

      p.meta_url = f"https://{self.options.public_host}/{path}"

      if save:
        path = f"saved/{p.pp.shortname}/{timestamp}.{who}.zip"
        common.upload_object("puzzle zip",
                             self.options.save_bucket, path,
                             "appliction/zip",
                             zip_data, self.options.credentials)
        global SAVED_PUZZLES
        SAVED_PUZZLES.setdefault(p.pp.shortname, {})[timestamp] = SavedPuzzle(
          timestamp=timestamp,
          who=who,
          puzzle_url=p.puzzle_url,
          meta_url=p.meta_url,
        )

      self.redirect(p.meta_url)
    except ppp.PuzzleErrors as e:
      path = f"html/{p.prefix}/error.txt"
      data = [f"{len(e.errors)} error(s) were encountered:"]
      for i, err in enumerate(e.errors):
        data.append(f"{i+1}: {err}")
      data = "\n".join(data)

      common.upload_object("errors",
                           self.options.bucket, path,
                           common.CONTENT_TYPES[".txt"],
                           data, self.options.credentials)

      error_url = f"https://{self.options.public_host}/{path}"

      self.redirect(error_url)
    except Exception as e:
      p.error_msg = traceback.format_exc()
      self.redirect(f"/error/{p.pid}")


class ErrorPage(tornado.web.RequestHandler):
  def get(self, pid):
    pid = int(pid)
    p = Puzzle.BY_PID[pid]

    self.render("preview_error.html", error=p.error_msg)


def load_saved_puzzles(options):
  global SAVED_PUZZLES
  page_token = None
  while True:
    url = f"https://www.googleapis.com/storage/v1/b/{options.save_bucket}/o?prefix=saved/"
    if page_token:
      url += f"&pageToken={page_token}"

    r = requests.get(url, headers={"Authorization": options.credentials.get()})
    if r.status_code == 401:
      options.credentials.invalidate()
      continue
    if r.status_code != 200:
      r.raise_for_status()

    d = json.loads(r.content)
    if "items" not in d: break
    for i in d["items"]:
      _, shortname, filename = i["name"].split("/")
      h = i["md5Hash"]
      assert h[-2:] == "=="
      h = h[:-2]
      h = h.replace("+", "-").replace("/", "_")
      timestamp, who, _ = filename.split(".")
      assert _ == "zip"
      SAVED_PUZZLES.setdefault(shortname, {})[timestamp] = SavedPuzzle(
        timestamp=timestamp,
        who=who,
        puzzle_url=f"https://{options.public_host}/html/{h}/puzzle.html",
        meta_url=f"https://{options.public_host}/html/{h}/meta.html",
      )

    page_token = d.get("nextPageToken")
    if not page_token: break


def main():
  parser = argparse.ArgumentParser(description="Live puzzle zip previewer")
  parser.add_argument("--credentials", help="Private key for google cloud service account.")
  parser.add_argument("--save_bucket", default="snellen-prod-zip",
                      help="Google cloud bucket to use for saved zips.")
  parser.add_argument("--bucket", default="snellen-preview",
                      help="Google cloud bucket to use for preview content.")
  parser.add_argument("--public_host", default=None,
                      help="Hostname for assets in urls.")
  parser.add_argument("--template_path",
                      default=os.path.join(os.getenv("HUNT2020_BASE"), "snellen/html"))
  parser.add_argument("--skip_upload", action="store_true",
                      help="Don't actually upload to GCS.")
  parser.add_argument("--socket", default="/tmp/preview",
                      help="Unix domain socket for server")
  parser.add_argument("-e", "--event_dir",
                      help="Path to event content.")
  options = parser.parse_args()

  options.credentials = oauth2.Oauth2Token(options.credentials)
  Puzzle.options = options

  if not options.public_host:
    options.public_host = options.bucket + ".storage.googleapis.com"

  load_saved_puzzles(options)

  print("Load map config...")
  with open(os.path.join(options.event_dir, "map_config.json")) as f:
    cfg = json.load(f)
    UploadHandler.static_content = cfg["static"]

  app = tornado.web.Application(
    [
      (r"/", PreviewPage),
      (r"/upload", UploadHandler, {"options": options}),
      (r"/saved", SavedPage),
      (r"/error/(\d+)", ErrorPage),
    ],
    template_path=options.template_path,
    options=options)

  server = tornado.httpserver.HTTPServer(app)
  socket = tornado.netutil.bind_unix_socket(options.socket, mode=0o666)
  server.add_socket(socket)

  tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
  main()
