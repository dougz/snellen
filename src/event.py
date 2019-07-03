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

    lands = []
    for land in game.Land.BY_SHORTNAME.values():
      if land in self.team.open_lands:
        lands.append((land.unlocked_image, land.pos[0], land.pos[1]))
      else:
        lands.append((land.locked_image, land.pos[0], land.pos[1]))
    script += """<script>var icons = """ + json.dumps(lands) + ";</script>"

    self.render("map.html", team=self.team, script=script)


class LandMapPage(tornado.web.RequestHandler):
  @login.required("team")
  def get(self, shortname):
    land = game.Land.BY_SHORTNAME.get(shortname, None)
    if not land:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    if land not in self.team.open_lands:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    script = ""
    if self.application.settings.get("debug"):
      script += ("""<script src="/closure/goog/base.js"></script>\n"""
                 """<script src="/client-debug.js"></script>""")
    else:
      script += """<script src="/client.js"></script>"""

    icons = []
    for p in land.puzzles:
      s = self.team.puzzle_state[p].state
      if s == game.PuzzleState.OPEN:
        icons.append((p.icon + "_unlocked.png", p.pos_x, p.pos_y))
      elif s == game.PuzzleState.SOLVED:
        icons.append((p.icon + "_solved.png", p.pos_x, p.pos_y))
    script += "<script>var icons = """ + json.dumps(icons) + ";</script>"

    self.render("land.html", team=self.team, land=land, script=script)




class DebugStartPage(tornado.web.RequestHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.render("debug_start.html", team=self.team)

class DebugDoStartEvent(tornado.web.RequestHandler):
  @login.required("team", require_start=False)
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

    self.render("puzzle_frame.html", team=self.team, puzzle=puzzle, state=self.team.puzzle_state[puzzle], script=script)

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
    d = {"allowed": submit_allowed,
         "history": [sub.json_dict() for sub in state.submissions],
         }
    if len(state.puzzle.answers) > 1:
      d["correct"] = len(state.answers_found)
      d["total"] = len(state.puzzle.answers)
    self.write(json.dumps(d))

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
    (r"/land/([a-z0-9_]+)", LandMapPage),
    (r"/DEBUGstartevent", DebugStartPage),
    (r"/DEBUGdostartevent", DebugDoStartEvent),
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

