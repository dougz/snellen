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
    self.return_json(self.team.get_land_data(land))


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
    self.return_json(d)

class CurrentHeaderDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self):
    self.return_json(self.team.get_header_data())

class VideosPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.session.visit_page("videos")
    self.render("videos.html")

class VideosDataHandler(util.TeamHandler):
  @login.required("team", require_start=False)
  def get(self):
    urls = []
    for i in range(1, self.team.videos+1):
      urls.append(OPTIONS.static_content.get(f"video{i}.mp4"))
    self.return_json(urls)

class AchievementPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.session.visit_page("pins")
    self.render("achievements.html", achievements=game.Achievement.ALL)

class AchievementDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self):
    ach = [{"name": a.name, "subtitle": a.subtitle} for a in self.team.achievements]
    return self.return_json(ach)

class EventsPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.session.visit_page("events")
    self.puzzle = game.Event.PUZZLE
    ps = self.team.puzzle_state[self.puzzle]
    completed = [e.answer in ps.answers_found for e in game.Event.ALL_EVENTS]

    self.render("events.html", events=game.Event.ALL_EVENTS, completed=completed)

class EventsDataHandler(util.TeamHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.write(json.dumps({}))

class WorkshopPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.puzzle = game.Workshop.PUZZLE
    ps = self.team.puzzle_state[self.puzzle]
    if ps.state == game.PuzzleState.CLOSED:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    self.render("workshop.html")

class WorkshopDataHandler(util.TeamHandler):
  @login.required("team", require_start=False)
  def get(self):
    d = {"earned": [p.name for p in self.team.pennies_earned],
         "collected": [p.name for p in self.team.pennies_collected]}
    self.return_json(d)

class ErrataPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    errata = self.team.get_errata_data()
    if not errata:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    json_data = "<script>var initial_json = """ + json.dumps(errata) + ";</script>"
    self.render("errata.html", json_data=json_data)

class GuestServicesPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    shortname = self.get_argument("p", None)
    if shortname:
      state = self.team.get_puzzle_state(shortname)
      if state and state.state != state.CLOSED:
        self.puzzle_id = state.puzzle.shortname
    self.session.visit_page("guest_services")
    d = {"fastpass": self.team.get_fastpass_data(),
         "hints": self.team.get_open_hints_data()}
    json_data = "<script>var initial_json = " + json.dumps(d) + ";</script>"
    self.render("guest_services.html", json_data=json_data)

class HintsOpenDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self):
    self.return_json(self.team.get_open_hints_data())

class ApplyFastPassHandler(util.TeamHandler):
  @login.required("team")
  def get(self, land_name):
    if self.team.apply_fastpass(land_name):
      self.set_status(http.client.NO_CONTENT.value)
    else:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

class AllPuzzlesPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.session.visit_page("all_puzzles")
    json_data = ""
    self.render("all_puzzles.html", json_data=json_data)

class AllPuzzlesDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self):
    self.return_json(self.team.get_all_puzzles_data())


class HealthAndSafetyPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.session.visit_page("health_safety")
    self.render("health_safety.html")

class SponsorPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.session.visit_page("sponsor")
    self.render("sponsor.html")

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
    ps = self.team.get_puzzle_state(shortname)
    if not ps or ps.state == game.PuzzleState.CLOSED:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    # Allow submit if the puzzle is open, and if there are fewer than
    # the max allowed pending submissions.
    submit_allowed = False
    if ps.state == game.PuzzleState.OPEN:
      pending = sum(1 for s in ps.submissions if s.state == s.PENDING)
      if pending < ps.puzzle.max_queued:
        submit_allowed = True

    d = {"allowed": submit_allowed,
         "history": [sub.json_dict() for sub in ps.submissions],
         }
    if ps.puzzle.errata:
      d["errata"] = True
    if ((len(ps.puzzle.answers) > 1 or ps.puzzle.land.shortname == "safari")
        and ps.puzzle.land.land_order < 1000):
      d["correct"] = len(ps.answers_found)
      d["total"] = len(ps.puzzle.answers)

    self.return_json(d)

class SubmitCancelHandler(util.TeamHandler):
  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  def get(self, shortname, submit_id):
    submit_id = int(submit_id)
    self.team.cancel_submission(submit_id, shortname)
    self.team.send_messages([{"method": "history_change", "puzzle_id": shortname}])
    self.set_status(http.client.NO_CONTENT.value)

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
    ps = self.team.puzzle_state[puzzle]
    if not ps.hints_available:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST)
    if self.team.current_hint_puzzlestate not in (None, ps):
      raise tornado.web.HTTPError(http.client.BAD_REQUEST)
    self.team.add_hint_text(shortname, None, text)
    self.set_status(http.client.NO_CONTENT.value)
    asyncio.create_task(login.AdminUser.flush_messages())

class HintHistoryHandler(util.TeamHandler):
  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  def get(self, shortname):
    ps = self.team.get_puzzle_state(shortname)
    if not ps:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    d = {"history": [msg.json_dict() for msg in ps.hints if not msg.admin_only],
         "puzzle_id": ps.puzzle.shortname}
    self.write(json.dumps(d))

def GetHandlers():
  handlers = [
    (r"/", PlayerHomePage),
    (r"/log", ActivityLogPage),
    (r"/videos", VideosPage),
    (r"/pins", AchievementPage),
    (r"/events", EventsPage),
    (r"/workshop", WorkshopPage),
    (r"/puzzles", AllPuzzlesPage),
    (r"/errata", ErrataPage),
    (r"/guest_services$", GuestServicesPage),
    (r"/health_and_safety", HealthAndSafetyPage),
    (r"/sponsors", SponsorPage),
    (r"/land/([a-z0-9_]+)", LandMapPage),
    (r"/puzzle/([a-z0-9_]+)/?", PuzzlePage),
    (r"/submit", SubmitHandler),
    (r"/cancel/([a-z][a-z0-9_]*)/(\d+)", SubmitCancelHandler),
    (r"/hintrequest", HintRequestHandler),
    (r"/hinthistory/([a-z][a-z0-9_]*)", HintHistoryHandler),
    (r"/pennypass/([a-z][a-z0-9_]*)$", ApplyFastPassHandler),
    (r"/js/submit/([a-z][a-z0-9_]*)$", SubmitHistoryHandler),
    (r"/js/log", ActivityLogDataHandler),
    (r"/js/pins", AchievementDataHandler),
    (r"/js/videos", VideosDataHandler),
    (r"/js/hintsopen", HintsOpenDataHandler),
    (r"/js/puzzles", AllPuzzlesDataHandler),
    (r"/js/header", CurrentHeaderDataHandler),
    (r"/js/workshop", WorkshopDataHandler),
    (r"/js/map/([a-z][a-z0-9_]+)$", MapDataHandler),
  ]

  return handlers

