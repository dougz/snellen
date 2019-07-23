import asyncio
import http.client
import json
import os
import random
import re
import time
import tornado.web

import game
import login
import util


class LandMapPage(util.TeamPageHandler):
  RECENT_SECONDS = 10.0

  @login.required("team")
  def get(self, shortname):
    self.show_map(shortname)

  def show_map(self, shortname):
    land = game.Land.BY_SHORTNAME.get(shortname, None)
    if not land:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    if land not in self.team.open_lands:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    items = []
    mapdata = {"base_url": land.base_img,
               "items": items}

    for i in land.icons.values():
      if i.puzzle:
        p = i.puzzle
        st = self.team.puzzle_state[p]
        if st.state == game.PuzzleState.CLOSED: continue

        d = { "name": p.title, "url": p.url }

        if st.answers_found:
          d["answer"] = ", ".join(sorted(p.display_answers[a] for a in st.answers_found))

        if st.state == game.PuzzleState.OPEN:
          if "answer" in d: d["answer"] += ", \u2026"

          open_time = self.team.puzzle_state[p].open_time
          duration = time.time() - open_time
          recent = (duration < self.RECENT_SECONDS and
                    open_time != game.Global.STATE.event_start_time)
          if recent: d["animate"] = "delay_fade"
          d["solved"] = False
          d["icon_url"] = i.images["unlocked"]

        elif st.state == game.PuzzleState.SOLVED:
          duration = time.time() - self.team.puzzle_state[p].solve_time
          recent = duration < self.RECENT_SECONDS
          if recent:
            dd = {"icon_url": i.images["unlocked"],
                  "pos_x": i.pos[0],
                  "pos_y": i.pos[1],
                  "width": i.size[0],
                  "height": i.size[1]}
            items.append(dd)
            d["animate"] = "sparkle"
          d["solved"] = True
          d["icon_url"] = i.images["solved"]
      else:
        if i.to_land not in self.team.open_lands: continue
        d = { "name": i.to_land.title,
              "url": i.to_land.url,
              "icon_url": i.images["unlocked"] }

      d["pos_x"], d["pos_y"] = i.pos
      d["width"], d["height"] = i.size
      if i.poly: d["poly"] = i.poly
      items.append(d)

    json_data = "<script>var mapdata = """ + json.dumps(mapdata) + ";</script>"

    self.render("land.html", land=land, json_data=json_data)


class EventHomePage(LandMapPage):
  @login.required("team", require_start=False)
  def get(self):
    if not game.Global.STATE.event_start_time:
      self.render("not_started.html")
      return
    self.show_map("inner_only")


class PuzzlePage(util.TeamPageHandler):
  @login.required("team")
  def get(self, shortname):
    state = self.team.get_puzzle_state(shortname)
    if not state or state.state == state.CLOSED:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      print(f"no puzzle called {shortname}")
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    self.puzzle = puzzle
    self.render("puzzle_frame.html")

class ActivityLogPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    json_data = """<script>var log_entries = """ + json.dumps(self.team.activity_log) + ";</script>"
    self.render("activity_log.html", json_data=json_data)

class WaitHandler(tornado.web.RequestHandler):
  WAIT_TIMEOUT = 300
  WAIT_SMEAR = 20

  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  async def get(self, wid, received_serial):
    wid = int(wid)
    received_serial = int(received_serial)

    waiter = self.session.get_waiter(wid)
    if not waiter:
      print(f"unknown waiter {wid}")
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    msgs = await waiter.wait(received_serial,
                       self.WAIT_TIMEOUT + random.random() * self.WAIT_SMEAR)

    self.set_header("Content-Type", "application/json")
    self.set_header("Cache-Control", "no-store")
    self.write(b"[")
    for i, (ser, obj) in enumerate(msgs):
      if i > 0: self.write(b",")
      self.write(f"[{ser},{obj}]".encode("utf-8"))
    self.write(b"]")


class SubmitHandler(tornado.web.RequestHandler):
  def prepare(self):
    self.args = json.loads(self.request.body)

  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  async def post(self):
    answer = self.args["answer"]

    # Worst-case option for entering a single-emoji answer: enter the
    # code point preceded by "U+" (eg, "U+1F460").
    answer = re.sub(r"[Uu]\+([0-9a-fA-F]{4,5})",
                    lambda m: chr(int(m.group(1), 16)), answer)

    shortname = self.args["puzzle_id"]
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle: raise tornado.web.HTTPError(http.client.NOT_FOUND)

    submit_id = self.team.next_submit_id()

    r = self.team.submit_answer(submit_id, shortname, answer)
    if r:
      msgs = [{"method": "history_change", "puzzle_id": shortname,
               "frompage": puzzle.url, "topage": puzzle.land.url}]
    else:
      msgs = [{"method": "history_change", "puzzle_id": shortname}]
    await self.team.send_message(msgs)

    if r:
      await self.team.send_message(r, delay=1.5)
    self.set_status(http.client.NO_CONTENT.value)


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
  async def get(self, shortname, submit_id):
    submit_id = int(submit_id)
    self.team.cancel_submission(submit_id, shortname)
    await self.team.send_message({"method": "history_change", "puzzle_id": shortname})

class ClientDebugJS(tornado.web.RequestHandler):
  @login.required("team")
  def get(self):
    self.set_header("Content-Type", "text/javascript")
    with open("src/client.js", "rb") as f:
      self.write(f.read())

class ClientJS(tornado.web.RequestHandler):
  def initialize(self, compiled_js):
    self.compiled_js = compiled_js
  @login.required("team", require_start=False)
  def get(self):
    self.set_header("Content-Type", "text/javascript")
    self.write(self.compiled_js)

class EventCSS(tornado.web.RequestHandler):
  def initialize(self, event_css):
    self.event_css = event_css
  @login.required("team", require_start=False)
  def get(self):
    self.set_header("Content-Type", "text/css")
    self.write(self.event_css)

def GetHandlers(event_dir, debug, compiled_js, event_css):
  handlers = [
    (r"/", EventHomePage),
    (r"/log", ActivityLogPage),
    (r"/land/([a-z0-9_]+)", LandMapPage),
    (r"/puzzle/([^/]+)/?", PuzzlePage),
    (r"/client.js", ClientJS, {"compiled_js": compiled_js}),
    (r"/event.css", EventCSS, {"event_css": event_css}),
    (r"/submit", SubmitHandler),
    (r"/submit_history/([a-z][a-z0-9_]*)", SubmitHistoryHandler),
    (r"/submit_cancel/([a-z][a-z0-9_]*)/(\d+)", SubmitCancelHandler),
    (r"/wait/(\d+)/(\d+)", WaitHandler),
    ]
  if debug:
    handlers.append((r"/client-debug.js", ClientDebugJS))
  return handlers

