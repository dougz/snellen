#!/usr/bin/python3

import argparse
import asyncio
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
    self.pp = ppp.Puzzle(zip_data, self.args)
    self.pp.land = Land


class PreviewPage(tornado.web.RequestHandler):
  def get(self):
    self.render("preview.html")

class UploadHandler(tornado.web.RequestHandler):
  def initialize(self, args):
    self.args = args

  def post(self):
    p = Puzzle()

    try:
      p.process(self.request.files["zip"][0]["body"])

      path = f"{p.pp.prefix}/puzzle.html"
      puzzle_html = self.render_string("puzzle_frame.html",
                                       puzzle=p.pp,
                                       team=Team,
                                       script=None,
                                       json_data=None)
      common.upload_object(self.args.bucket, path, "text/html",
                           puzzle_html, self.args.credentials)
      p.puzzle_url = f"https://{self.args.bucket}.storage.googleapis.com/{path}"

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
  parser.add_argument("--template_path")
  parser.add_argument("--skip_upload", action="store_true",
                      help="Don't actually upload to GCS.")
  parser.add_argument("--socket", default="/tmp/preview",
                      help="Unix domain socket for server")
  args = parser.parse_args()

  args.credentials = oauth2.Oauth2Token(args.credentials)
  Puzzle.args = args

  app = tornado.web.Application(
    [
      (r"/", PreviewPage),
      (r"/upload", UploadHandler, {"args": args}),
      (r"/error/(\d+)", ErrorPage),
    ],
    template_path=args.template_path,
    args=args)

  server = tornado.httpserver.HTTPServer(app)
  socket = tornado.netutil.bind_unix_socket(args.socket, mode=0o666)
  server.add_socket(socket)

  tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
  main()
