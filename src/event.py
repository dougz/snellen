import http.client
import json
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
  def get(self, shortname):
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      print(f"no puzzle called {shortname}")
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    script = f"""<script>\nvar puzzle_id = "{puzzle.shortname}";\n</script>\n"""

    if self.application.settings.get("debug"):
      script += ("""<script src="/closure/goog/base.js"></script>\n"""
                 """<script src="/client-debug.js"></script>""")
    else:
      script += """<script src="/client.js"></script>"""

    self.render("puzzle_frame.html", title=puzzle.title, body=puzzle.html_body,
                script=script)

class WaitHandler(tornado.web.RequestHandler):
  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  async def get(self, received_serial):
    received_serial = int(received_serial)
    q = self.session.wait_queue
    # Client acks all messages up through received_serial; these can
    # be discarded.
    while q and q[0][0] <= received_serial:
      q.popleft()

    while True:
      if q:
        self.set_header("Content-Type", "application/json")
        self.write(b"[")
        for ser, obj in q:
          self.write(f"[{ser},{obj}]".encode("utf-8"))
        self.write(b"]")
        return
      await self.session.wait_event.wait()
      self.session.wait_event.clear()


class SubmitHandler(tornado.web.RequestHandler):
  def prepare(self):
    self.args = json.loads(self.request.body)

  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  def post(self):
    answer = self.args["answer"]
    shortname = self.args["puzzle_id"]
    success = self.team.submit_answer(shortname, answer)
    if success:
      self.set_status(http.client.NO_CONTENT.value)
    else:
      print(f"FAILED to submit {answer} for {shortname}")
      self.set_status(http.client.BAD_REQUEST.value)

class SubmitHistoryHandler(tornado.web.RequestHandler):
  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  def get(self, shortname):
    state = self.team.get_puzzle_state(shortname)
    if not state:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    self.set_header("Content-Type", "application/json")
    self.write(json.dumps(state.submit_history))


class ClientDebugJS(tornado.web.RequestHandler):
  @login.required("team")
  def get(self):
    self.set_header("Content-Type", "text/javascript")
    with open("src/client.js", "rb") as f:
      self.write(f.read())

class ClientJS(tornado.web.RequestHandler):
  def initialize(self, compiled_js):
    self.compiled_js = compiled_js
  @login.required("team")
  def get(self):
    self.set_header("Content-Type", "text/javascript")
    self.write(self.compiled_js)

class EventCSS(tornado.web.RequestHandler):
  def initialize(self, event_css):
    self.event_css = event_css
  @login.required("team")
  def get(self):
    self.set_header("Content-Type", "text/css")
    self.write(self.event_css)

class PuzzleAsset(tornado.web.RequestHandler):
  MIME_TYPES = {".jpg": "image/jpeg"}

  def initialize(self, event_dir=None):
    self.event_dir = event_dir

  @login.required("team")
  def get(self, shortname, path):
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    _, ext = os.path.splitext(path)
    mime_type = self.MIME_TYPES.get(ext, "application/octet-stream")

    self.set_header("Content-Type", mime_type)
    with open(os.path.join(self.event_dir, "puzzles", shortname, path), "rb") as f:
      self.write(f.read())


def GetHandlers(event_dir, debug, compiled_js, event_css):
  handlers = [
    (r"/", EventHome),
    (r"/puzzle/([^/]+)/", PuzzlePage),
    (r"/puzzle/([^/]+)/(.*)", PuzzleAsset, {"event_dir": event_dir}),
    (r"/client.js", ClientJS, {"compiled_js": compiled_js}),
    (r"/event.css", EventCSS, {"event_css": event_css}),
    (r"/submit", SubmitHandler),
    (r"/submit_history/(.*)", SubmitHistoryHandler),
    (r"/wait/(\d+)", WaitHandler),
    ]
  if debug:
    handlers.append((r"/client-debug.js", ClientDebugJS))
  return handlers

