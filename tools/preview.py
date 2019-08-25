#!/usr/bin/python3

import argparse
import asyncio
import json
import os
import re
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


class Puzzle:
  NEXT_PID = 1
  BY_PID = {}

  def __init__(self):
    self.pid = Puzzle.NEXT_PID
    Puzzle.NEXT_PID += 1
    Puzzle.BY_PID[self.pid] = self

  def process(self, zip_data):
    self.prefix = common.hash_name(zip_data)
    self.pp = ppp.Puzzle(zip_data, self.options, include_solutions=True)
    self.pp.land = Land


class PreviewPage(tornado.web.RequestHandler):
  def get(self):
    self.render("preview.html")


class UploadHandler(tornado.web.RequestHandler):
  def initialize(self, options):
    self.options = options

  def post(self):
    p = Puzzle()

    save = self.get_body_argument("save", False)
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

      path = f"html/{p.prefix}/solution.html"
      puzzle_html = self.render_string("solution_frame.html",
                                       solution_url=None,
                                       puzzle=p.pp,
                                       authors=authors,
                                       team=Team,
                                       css=[self.static_content["event.css"]],
                                       script=None,
                                       json_data=None)
      common.upload_object("solution.html",
                           self.options.bucket, path,
                           common.CONTENT_TYPES[".html"],
                           puzzle_html, self.options.credentials)

      p.solution_url = f"https://{self.options.public_host}/{path}"

      path = f"html/{p.prefix}/puzzle.html"
      puzzle_html = self.render_string("solution_frame.html",
                                       solution_url=p.solution_url,
                                       puzzle=p.pp,
                                       authors=None,
                                       team=Team,
                                       css=[self.static_content["event.css"]],
                                       script=None,
                                       json_data=None)
      common.upload_object("puzzle.html",
                           self.options.bucket, path,
                           common.CONTENT_TYPES[".html"],
                           puzzle_html, self.options.credentials)

      p.puzzle_url = f"https://{self.options.public_host}/{path}"

      path = f"html/{p.prefix}/for_ops.html"
      puzzle_html = self.render_string("preview_for_ops.html",
                                       puzzle=p.pp,
                                       team=Team,
                                       css=[self.static_content["event.css"]],
                                       script=None,
                                       json_data=None)
      common.upload_object("for_ops.html",
                           self.options.bucket, path,
                           common.CONTENT_TYPES[".html"],
                           puzzle_html, self.options.credentials)

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
                           meta_html, self.options.credentials)

      p.meta_url = f"https://{self.options.public_host}/{path}"

      if save:
        path = f"saved/{p.pp.shortname}/{timestamp}.{who}.{p.prefix}.zip"
        common.upload_object("puzzle zip",
                             self.options.save_bucket, path,
                             "appliction/zip",
                             zip_data, self.options.credentials)

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


def main():
  parser = argparse.ArgumentParser(description="Live puzzle zip previewer")
  parser.add_argument("--credentials", help="Private key for google cloud service account.")
  parser.add_argument("--save_bucket", default="snellen-prod-zip",
                      help="Google cloud bucket to use for saved zips.")
  parser.add_argument("--bucket", default="snellen-preview",
                      help="Google cloud bucket to use for preview content.")
  parser.add_argument("--public_host", help="Hostname for assets in urls.")
  parser.add_argument("--template_path")
  parser.add_argument("--skip_upload", action="store_true",
                      help="Don't actually upload to GCS.")
  parser.add_argument("--socket", default="/tmp/preview",
                      help="Unix domain socket for server")
  parser.add_argument("-e", "--event_dir",
                      help="Path to event content.")
  options = parser.parse_args()

  options.credentials = oauth2.Oauth2Token(options.credentials)
  Puzzle.options = options

  print("Load map config...")
  with open(os.path.join(options.event_dir, "map_config.json")) as f:
    cfg = json.load(f)
    UploadHandler.static_content = cfg["static"]

  app = tornado.web.Application(
    [
      (r"/", PreviewPage),
      (r"/upload", UploadHandler, {"options": options}),
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
