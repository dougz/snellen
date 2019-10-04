import asyncio
import html
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
    mapdata = self.team.get_land_data(land)
    json_data = "<script>var initial_json = """ + json.dumps(mapdata) + ";</script>"
    self.render("land.html", land=land, json_data=json_data)

  def get_template_namespace(self):
    d = super().get_template_namespace()
    if hasattr(self, "land"):
      if False and self.application.settings.get("debug"):
        d["css"].append(f"/assets/{self.land.shortname}/land.css")
      else:
        css = f"{self.land.shortname}/land.css"
        if css in self.static_content:
          d["css"].append(self.static_content[css])
    return d


class EventHomePage(LandMapPage):
  @login.required()
  def get(self):
    if self.team:
      if not game.Global.STATE.event_start_time:
        self.render("not_started.html",
                    open_time=game.Global.STATE.expected_start_time,
                    css=(self.static_content["notopen.css"],))
        return
      self.show_map("inner_only")
    elif self.user:
      self.redirect("/admin")


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

    if puzzle.icon.headerimage:
      supertitle=f'<img src="{puzzle.icon.headerimage}"><br>'
    else:
      supertitle=""

    self.puzzle = puzzle
    self.render("puzzle_frame.html", thumb=thumb, supertitle=supertitle,
                solved=(state.state == state.SOLVED))

  def get_template_namespace(self):
    land = self.puzzle.land
    d = super().get_template_namespace()
    css = f"{land.shortname}/land.css"
    if css in self.static_content:
      d["css"].append(self.static_content[css])
    if self.puzzle.emojify:
      # TODO: consider hosting (or implementing) twemoji locally
      d["script"] += """
        <script src="https://twemoji.maxcdn.com/v/latest/twemoji.min.js" crossorigin="anonymous"></script>
        """
      d["script"] += f"""<script>var edb = "{self.static_content["emoji.json"]}";</script>"""

    return d


class ActivityLogPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.session.visit_page("activity")
    json_data = """<script>var log_entries = """ + self.team.activity_log.json() + ";</script>"
    self.render("activity_log.html", json_data=json_data)

class AchievementPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.session.visit_page("pins")
    self.render("achievements.html", achievements=game.Achievement.ALL)

class FastPassPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.session.visit_page("fastpass")
    json_data = "<script>var initial_json = " + json.dumps(self.team.get_fastpass_data()) + ";</script>"
    self.render("fastpass.html", json_data=json_data)

class ApplyFastPassHandler(util.TeamHandler):
  @login.required("team")
  def get(self, land_name):
    if self.team.apply_fastpass(land_name):
      self.set_status(http.client.NO_CONTENT.value)
    else:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

class HealthAndSafetyPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.session.visit_page("health_safety")
    self.render("health_safety.html")

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

    result = self.team.submit_answer(submit_id, shortname, answer)
    if result:
      self.write(result)
      self.set_status(http.client.CONFLICT.value)
    else:
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

class HintRequestHandler(util.TeamHandler):
  def prepare(self):
    self.args = json.loads(self.request.body)

  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  def post(self):
    text = self.args["text"].strip()
    text = html.escape(text).replace("\n", "<br>")
    shortname = self.args["puzzle_id"]
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    state = self.team.puzzle_state[puzzle]
    if not state.hints_available:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST)
    self.team.add_hint_text(shortname, None, text)
    self.set_status(http.client.NO_CONTENT.value)
    asyncio.create_task(login.AdminUser.flush_messages())

class HintHistoryHandler(util.TeamHandler):
  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  def get(self, shortname):
    state = self.team.get_puzzle_state(shortname)
    if not state:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    d = {"history": [msg.json_dict() for msg in state.hints]}
    self.write(json.dumps(d))

def GetHandlers():
  handlers = [
    (r"/", EventHomePage),
    (r"/log", ActivityLogPage),
    (r"/pins", AchievementPage),
    (r"/fastpass$", FastPassPage),
    (r"/health_and_safety", HealthAndSafetyPage),
    (r"/land/([a-z0-9_]+)", LandMapPage),
    (r"/puzzle/([a-z0-9_]+)/?", PuzzlePage),
    (r"/submit", SubmitHandler),
    (r"/submit_history/([a-z][a-z0-9_]*)", SubmitHistoryHandler),
    (r"/submit_cancel/([a-z][a-z0-9_]*)/(\d+)", SubmitCancelHandler),
    (r"/hintrequest", HintRequestHandler),
    (r"/hinthistory/([a-z][a-z0-9_]*)", HintHistoryHandler),
    (r"/fastpass/([a-z][a-z0-9_]*)$", ApplyFastPassHandler),
  ]

  return handlers

