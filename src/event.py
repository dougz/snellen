import http.client
import os
import tornado.web

import game
import login

class EventHome(tornado.web.RequestHandler):
  @login.required("team")
  def get(self):
    self.render("home.html", team=self.team)

class PuzzlePage(tornado.web.RequestHandler):
  @login.required("team")
  def get(self, nickname):
    puzzle = game.Puzzle.get_by_nickname(nickname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    self.render("puzzle_frame.html", title=puzzle.title, body=puzzle.html_body)

class PuzzleAsset(tornado.web.RequestHandler):
  MIME_TYPES = {".jpg": "image/jpeg"}

  def initialize(self, event_dir=None):
    self.event_dir = event_dir

  @login.required("team")
  def get(self, nickname, path):
    puzzle = game.Puzzle.get_by_nickname(nickname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    _, ext = os.path.splitext(path)
    mime_type = self.MIME_TYPES.get(ext, "application/octet-stream")

    self.set_header("Content-Type", mime_type)
    with open(os.path.join(self.event_dir, "puzzles", nickname, path), "rb") as f:
      self.write(f.read())


def GetHandlers(event_dir):
  return [
    (r"/", EventHome),
    (r"/puzzle/([^/]+)/", PuzzlePage),
    (r"/puzzle/([^/]+)/(.*)", PuzzleAsset, {"event_dir": event_dir}),
    ]
