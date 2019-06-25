import http.client
import json
import os
import re
import tornado.web

import game
import login

class EventHome(tornado.web.RequestHandler):
  @login.required("team")
  def get(self):
    script = """<script>\nvar puzzle_id = null;\n</script>\n"""
    if self.application.settings.get("debug"):
      script += ("""<script src="/closure/goog/base.js"></script>\n"""
                 """<script src="/client-debug.js"></script>""")
    else:
      script += """<script src="/client.js"></script>"""

    self.render("home.html", team=self.team, script=script)

class DebugStartEvent(tornado.web.RequestHandler):
  @login.required("team")
  def get(self):
    if self.team.event_start is None:
      self.team.start_event()
    self.redirect("/")

class PuzzlePage(tornado.web.RequestHandler):
  @login.required("team")
  def get(self, shortname):
    state = self.team.get_puzzle_state(shortname)
    if not state or state.state == state.CLOSED:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

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
        for i, (ser, obj) in enumerate(q):
          if i > 0: self.write(b",")
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

    # Worst-case option for entering a single-emoji answer: enter the
    # code point preceded by "U+" (eg, "U+1F460").
    answer = re.sub(r"[Uu]\+([0-9a-fA-F]{4,5})",
                    lambda m: chr(int(m.group(1), 16)), answer)

    shortname = self.args["puzzle_id"]
    submit_id = self.team.next_submit_id()
    success = self.team.submit_answer(submit_id, shortname, answer)
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

    # Allow submit if the puzzle is open, and if there are fewer than
    # the max allowed pending submissions.
    submit_allowed = False
    if state.state == state.OPEN:
      pending = sum(1 for s in state.submissions if s.state == s.PENDING)
      if pending < state.puzzle.max_queued:
        submit_allowed = True

    self.set_header("Content-Type", "application/json")
    self.write(f"[{json.dumps(submit_allowed)},")
    self.write("[" +
               ",".join(sub.to_json() for sub in state.submissions) +
               "]")
    self.write("]")

class SubmitCancelHandler(tornado.web.RequestHandler):
  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  def get(self, shortname, submit_id):
    submit_id = int(submit_id)
    self.team.cancel_submission(submit_id, shortname)


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
    (r"/DEBUGstartevent", DebugStartEvent),
    (r"/puzzle/([^/]+)/", PuzzlePage),
    (r"/puzzle/([^/]+)/(.*)", PuzzleAsset, {"event_dir": event_dir}),
    (r"/client.js", ClientJS, {"compiled_js": compiled_js}),
    (r"/event.css", EventCSS, {"event_css": event_css}),
    (r"/submit", SubmitHandler),
    (r"/submit_history/([a-z][a-z0-9_]*)", SubmitHistoryHandler),
    (r"/submit_cancel/([a-z][a-z0-9_]*)/(\d+)", SubmitCancelHandler),
    (r"/wait/(\d+)", WaitHandler),
    ]
  if debug:
    handlers.append((r"/client-debug.js", ClientDebugJS))
  return handlers

