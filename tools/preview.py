#!/usr/bin/python3

import argparse
import asyncio
import json
import os
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
  team_name = "Team Name Here"


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

    try:
      p.process(self.request.files["zip"][0]["body"])

      path = f"html/{p.pp.prefix}/solution.html"
      puzzle_html = self.render_string("solution_frame.html",
                                       solution_url=None,
                                       puzzle=p.pp,
                                       team=Team,
                                       css=self.static_content["event.css"],
                                       script=None,
                                       json_data=None)
      common.upload_object(self.options.bucket, path,
                           common.CONTENT_TYPES[".html"],
                           puzzle_html, self.options.credentials)

      p.solution_url = f"https://{self.options.public_host}/{path}"

      path = f"html/{p.pp.prefix}/puzzle.html"
      puzzle_html = self.render_string("solution_frame.html",
                                       solution_url=p.solution_url,
                                       puzzle=p.pp,
                                       team=Team,
                                       css=self.static_content["event.css"],
                                       script=None,
                                       json_data=None)
      common.upload_object(self.options.bucket, path,
                           common.CONTENT_TYPES[".html"],
                           puzzle_html, self.options.credentials)

      p.puzzle_url = f"https://{self.options.public_host}/{path}"
      self.redirect(p.puzzle_url)
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
  parser.add_argument("--bucket", default="snellen-preview",
                      help="Google cloud bucket to use.")
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
