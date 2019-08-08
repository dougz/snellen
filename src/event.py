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

    self.land = land

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

          d["solved"] = False
          if i.unlocked.url:
            d["icon_url"] = i.unlocked.url
            d["pos_x"], d["pos_y"] = i.unlocked.pos
            d["width"], d["height"] = i.unlocked.size
            if i.unlocked.poly: d["poly"] = i.unlocked.poly

        elif st.state == game.PuzzleState.SOLVED:
          d["solved"] = True
          if i.solved.url:
            d["icon_url"] = i.solved.url
            d["pos_x"], d["pos_y"] = i.solved.pos
            d["width"], d["height"] = i.solved.size
            if i.solved.poly: d["poly"] = i.solved.poly

      else:
        if i.to_land not in self.team.open_lands: continue
        d = { "name": i.to_land.title,
              "url": i.to_land.url,
              "icon_url": i.unlocked.url }

      items.append(d)

    json_data = "<script>var mapdata = """ + json.dumps(mapdata) + ";</script>"

    self.render("land.html", land=land, json_data=json_data)

  def get_template_namespace(self):
    d = super().get_template_namespace()
    if self.application.settings.get("debug"):
      d["css"].append(f"/assets/{self.land.shortname}/land.css")
    else:
      css = f"{self.land.shortname}/land.css"
      if css in self.static_content:
        d["css"].append(self.static_content[css])
    return d


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

    if (state.state == game.PuzzleState.SOLVED and
        not state.recent_solve()):
      thumb = puzzle.icon.solved_thumb
    else:
      thumb = puzzle.icon.unlocked_thumb

    self.puzzle = puzzle
    self.render("puzzle_frame.html", thumb=thumb)

  def get_template_namespace(self):
    land = self.puzzle.land
    d = super().get_template_namespace()
    if self.application.settings.get("debug"):
      d["css"].append(f"/assets/{land.shortname}/land.css")
    else:
      css = f"{land.shortname}/land.css"
      if css in self.static_content:
        d["css"].append(self.static_content[css])
    return d


class ActivityLogPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.team.delayed_achieve(game.Achievement.visit_log)
    json_data = """<script>var log_entries = """ + json.dumps(self.team.activity_log) + ";</script>"
    self.render("activity_log.html", json_data=json_data)

class AchievementPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.render("achievements.html", achievements=game.Achievement.ALL)

class SubmitHandler(util.TeamHandler):
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
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle: raise tornado.web.HTTPError(http.client.NOT_FOUND)

    submit_id = self.team.next_submit_id()

    self.team.submit_answer(submit_id, shortname, answer)
    self.set_status(http.client.NO_CONTENT.value)

class SubmitHistoryHandler(util.TeamHandler):
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

    if state.recent_solve():
      d["overlay"] = state.puzzle.icon.solved_thumb.url
      d["width"], d["height"] = state.puzzle.icon.solved_thumb.size

    self.write(json.dumps(d))

class SubmitCancelHandler(util.TeamHandler):
  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  def get(self, shortname, submit_id):
    submit_id = int(submit_id)
    self.team.cancel_submission(submit_id, shortname)
    self.team.send_messages([{"method": "history_change", "puzzle_id": shortname}])

def GetHandlers():
  handlers = [
    (r"/", EventHomePage),
    (r"/log", ActivityLogPage),
    (r"/pins", AchievementPage),
    (r"/land/([a-z0-9_]+)", LandMapPage),
    (r"/puzzle/([^/]+)/?", PuzzlePage),
    (r"/submit", SubmitHandler),
    (r"/submit_history/([a-z][a-z0-9_]*)", SubmitHistoryHandler),
    (r"/submit_cancel/([a-z][a-z0-9_]*)/(\d+)", SubmitCancelHandler),
    ]
  return handlers

