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


OPTIONS = None


class LandMapPage(util.TeamPageHandler):
  RECENT_SECONDS = 10.0

  @login.required("team")
  def get(self, shortname):
    self.show_map(shortname)

  def show_map(self, shortname):
    if shortname == "home":
      land = game.Land.BY_SHORTNAME[self.team.map_mode]
    else:
      land = game.Land.BY_SHORTNAME.get(shortname, None)
      if not land:
        raise tornado.web.HTTPError(http.client.NOT_FOUND)
      if land not in self.team.open_lands:
        raise tornado.web.HTTPError(http.client.NOT_FOUND)
    self.land = land
    mapdata = self.team.get_land_data(land)
    json_data = "<script>var initial_json = """ + mapdata + ";</script>"
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


class MapDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self, shortname):
    if shortname == "home":
      land = game.Land.BY_SHORTNAME[self.team.map_mode]
    else:
      land = game.Land.BY_SHORTNAME.get(shortname, None)
      if not land:
        raise tornado.web.HTTPError(http.client.NOT_FOUND)
      if land not in self.team.open_lands:
        raise tornado.web.HTTPError(http.client.NOT_FOUND)
    mapdata = self.team.get_land_data(land)
    self.set_header("Content-Type", "application/json")
    self.write(mapdata)


class PlayerHomePage(LandMapPage):
  @login.required("team", require_start=False)
  def get(self):
    if not game.Global.STATE.event_start_time:
      self.render("not_started.html",
                  open_time=game.Global.STATE.expected_start_time,
                  css=(self.static_content["notopen.css"],))
      return
    self.show_map("home")


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

    # if (state.state == game.PuzzleState.SOLVED and
    #     not state.recent_solve()):
    #   thumb = puzzle.icon.solved_thumb
    # else:
    #   thumb = puzzle.icon.unlocked_thumb

    if puzzle.icon.headerimage:
      supertitle=f'<img src="{puzzle.icon.headerimage}"><br>'
    else:
      supertitle=""

    self.puzzle = puzzle
    self.render("puzzle_frame.html", thumb=None, supertitle=supertitle,
                solved=(state.state == state.SOLVED))


class ActivityLogPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.session.visit_page("activity")
    self.render("activity_log.html")

class ActivityLogDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self):
    d = {"log": self.team.activity_log.get_data()}
    self.set_header("Content-Type", "application/json")
    self.write(json.dumps(d))

class VideosPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.session.visit_page("videos")
    self.render("videos.html")

class VideosDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self):
    urls = []
    for i in range(1, self.team.videos+1):
      urls.append(OPTIONS.static_content.get(f"video{i}.mp4"))
    self.set_header("Content-Type", "application/json")
    self.write(json.dumps(urls))

class AchievementPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.session.visit_page("pins")
    self.render("achievements.html", achievements=game.Achievement.ALL)

class AchievementDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self):
    ach = [{"name": a.name, "subtitle": a.subtitle} for a in self.team.achievements]
    self.set_header("Content-Type", "application/json")
    self.write(json.dumps(ach))

class EventsPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.session.visit_page("events")
    self.puzzle = game.Event.PUZZLE
    ps = self.team.puzzle_state[self.puzzle]
    completed = [e.answer in ps.answers_found for e in game.Event.ALL_EVENTS]

    self.render("events.html", events=game.Event.ALL_EVENTS, completed=completed)

class EventsDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self):
    self.write(json.dumps({}))

class GuestServicesPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.session.visit_page("guest_services")
    d = {"fastpass": self.team.get_fastpass_data(),
         "hints": self.team.get_open_hints_data()}
    json_data = "<script>var initial_json = " + json.dumps(d) + ";</script>"
    self.render("guest_services.html", json_data=json_data)

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
    if ((len(state.puzzle.answers) > 1 or state.puzzle.land.shortname == "safari")
        and state.puzzle.land.land_order < 1000):
      d["correct"] = len(state.answers_found)
      d["total"] = len(state.puzzle.answers)

    # if state.recent_solve():
    #   d["overlay"] = state.puzzle.icon.solved_thumb.url
    #   d["width"], d["height"] = state.puzzle.icon.solved_thumb.size

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
    text = self.args["text"].rstrip()
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

    d = {"history": [msg.json_dict() for msg in state.hints if not msg.admin_only]}
    self.write(json.dumps(d))

def GetHandlers():
  handlers = [
    (r"/", PlayerHomePage),
    (r"/log", ActivityLogPage),
    (r"/videos", VideosPage),
    (r"/pins", AchievementPage),
    (r"/events", EventsPage),
    (r"/guest_services$", GuestServicesPage),
    (r"/health_and_safety", HealthAndSafetyPage),
    (r"/land/([a-z0-9_]+)", LandMapPage),
    (r"/puzzle/([a-z0-9_]+)/?", PuzzlePage),
    (r"/submit", SubmitHandler),
    (r"/submit_history/([a-z][a-z0-9_]*)", SubmitHistoryHandler),
    (r"/submit_cancel/([a-z][a-z0-9_]*)/(\d+)", SubmitCancelHandler),
    (r"/hintrequest", HintRequestHandler),
    (r"/hinthistory/([a-z][a-z0-9_]*)", HintHistoryHandler),
    (r"/pennypass/([a-z][a-z0-9_]*)$", ApplyFastPassHandler),
    (r"/js/log", ActivityLogDataHandler),
    (r"/js/pins", AchievementDataHandler),
    (r"/js/videos", VideosDataHandler),
    (r"/js/map/([a-z][a-z0-9_]+)$", MapDataHandler),
  ]

  return handlers

