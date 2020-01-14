import asyncio
import html
import http.client
import json
import os
import random
import re
import time
import tornado.web
import yaml

import game
import login
import util


OPTIONS = None


class LandMapPage(util.TeamPageHandler):
  RECENT_SECONDS = 10.0

  @login.required("team")
  def get(self, shortname):
    self.show_map(shortname)

  def show_map(self, shortname, launch=False):
    if shortname == "mainmap":
      j = self.team.get_mainmap_data()
      land = game.Land.BY_SHORTNAME["mainmap"]
      self.land = land
    else:
      land = game.Land.BY_SHORTNAME.get(shortname, None)
      if not land:
        return self.not_found()
      if land not in self.team.open_lands:
        return self.not_found()
      self.land = land
      j = self.team.get_land_data(land)
    json_data = "<script>var initial_json = """ + j + ";</script>"

    if launch:
      if not self.team.cached_launch_page:
        self.team.cached_launch_page = self.render_string("land.html", land=land, json_data=json_data,
                                                          event_hash=game.Global.STATE.event_hash)
      self.write(self.team.cached_launch_page)
      return

    self.render("land.html", land=land, json_data=json_data,
                event_hash=game.Global.STATE.event_hash)


class MapDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self, shortname):
    if shortname == "mainmap":
      j = self.team.get_mainmap_data()
    else:
      land = game.Land.BY_SHORTNAME.get(shortname, None)
      if not land:
        return self.not_found()
      if land not in self.team.open_lands:
        return self.not_found()
      j = self.team.get_land_data(land)
    self.return_json(j)


class PlayerHomePage(LandMapPage):
  @login.required("team", require_start=False)
  def get(self):
    if not game.Global.STATE.event_start_time:
      if self.application.settings.get("debug"):
        css = self.static_content["notopen.css"]
      else:
        css = self.static_content["notopen-compiled.css"]

      self.render("not_started.html",
                  open_time=game.Global.STATE.expected_start_time,
                  css=(css,))
      return
    self.show_map("mainmap", launch=time.time() < game.Global.STATE.event_start_time + 15)

class PuzzlePage(util.TeamPageHandler):
  @login.required("team")
  def get(self, shortname):
    ps = self.team.get_puzzle_state(shortname)
    if not ps or ps.state == game.PuzzleState.CLOSED:
      return self.not_found()

    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      print(f"no puzzle called {shortname}")
      return self.not_found()

    if puzzle.icon.headerimage:
      supertitle=f'<img src="{puzzle.icon.headerimage}"><br>'
    else:
      supertitle=""

    self.puzzle = puzzle

    self.render("puzzle_frame.html", thumb=None, supertitle=supertitle,
                solved=(ps.state == game.PuzzleState.SOLVED))


class ActivityLogPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
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

class AboutTheParkPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.render("about_the_park.html", static_content=self.static_content,
                videos=VIDEOS[:self.team.videos])

class RulesPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.render("rules.html", static_content=self.static_content)

class VideosDataHandler(util.TeamHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.return_json(VIDEOS[:self.team.videos])

class EventsPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.puzzle = game.Event.PUZZLE
    ps = self.team.puzzle_state[self.puzzle]
    completed = [e.answer in ps.answers_found for e in game.Event.ALL_EVENTS]

    self.render("events.html", events=game.Event.ALL_EVENTS,
                completed=completed,
                solved=(ps.state == game.PuzzleState.SOLVED))

class WorkshopPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.puzzle = game.Workshop.PUZZLE
    ps = self.team.puzzle_state[self.puzzle]
    if ps.state == game.PuzzleState.CLOSED:
      return self.not_found()
    self.render("workshop.html", allow_submit=game.Workshop.submit_filter(ps),
                solved=(ps.state == game.PuzzleState.SOLVED))

class WorkshopDataHandler(util.TeamHandler):
  @login.required("team", require_start=False)
  def get(self):
    ps = self.team.puzzle_state[game.Workshop.PUZZLE]
    if ps.state == game.PuzzleState.CLOSED:
      return self.not_found()
    d = {"earned": [p.name for p in self.team.pennies_earned],
         "collected": [p.name for p in self.team.pennies_collected],
         "allow_submit": game.Workshop.submit_filter(ps)}
    self.return_json(d)

class RunaroundPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.puzzle = game.Runaround.PUZZLE
    ps = self.team.puzzle_state[self.puzzle]
    if ps.state == game.PuzzleState.CLOSED:
      return self.not_found()
    self.render("runaround.html", segments=game.Runaround.SEGMENTS, ps=ps,
                static=OPTIONS.static_content,
                solved=(ps.state == game.PuzzleState.SOLVED))

class RunaroundDataHandler(util.TeamHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.return_json(None)

class ErrataPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    errata = self.team.get_errata_data()
    if not errata:
      return self.not_found()
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
    d = {"fastpass": self.team.get_fastpass_data(),
         "hints": self.team.get_open_hints_data()}
    json_data = "<script>var initial_json = " + json.dumps(d) + ";</script>"
    self.render("guest_services.html", json_data=json_data)

class HintsOpenDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self):
    self.return_json(self.team.get_open_hints_data())

class AllPuzzlesPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    json_data = ""
    self.render("all_puzzles.html", json_data=json_data)

class AllPuzzlesDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self):
    self.return_json(self.team.get_all_puzzles_data())

class HealthAndSafetyPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.render("health_safety.html")

class SponsorPage(util.TeamPageHandler):
  @login.required("team", require_start=False)
  def get(self):
    self.render("sponsor.html", static_content=self.static_content)

class SubmitHistoryHandler(util.TeamHandler):
  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  def get(self, shortname):
    ps = self.team.get_puzzle_state(shortname)
    if not ps or ps.state == game.PuzzleState.CLOSED:
      return self.not_found()

    # Allow submit if the puzzle is open, and if there are fewer than
    # the max allowed pending submissions.
    submit_allowed = False
    if ps.state == game.PuzzleState.OPEN:
      if ps.puzzle.wait_for_requested:
        submit_allowed = True
        if ps.submissions and ps.submissions[-1].state == game.Submission.REQUESTED:
          submit_allowed = False
      else:
        pending = sum(1 for s in ps.submissions if s.state == s.PENDING)
        if pending < ps.puzzle.max_queued:
          submit_allowed = True

    d = {"allowed": submit_allowed,
         "history": [sub.json_dict() for sub in ps.submissions if sub.state != sub.RESET],
         }
    if ps.puzzle.errata:
      d["errata"] = [{"when": e.when, "text": e.text} for e in reversed(ps.puzzle.errata)]

    if ((len(ps.puzzle.answers) > 1 or ps.puzzle.land.shortname == "safari")
        and ps.puzzle.land.land_order < 1000):
      d["correct"] = len(ps.answers_found)
      d["total"] = len(ps.puzzle.answers)

    self.return_json(d)

class HintHistoryHandler(util.TeamHandler):
  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  def get(self, shortname):
    ps = self.team.get_puzzle_state(shortname)
    if not ps:
      return self.not_found()
    d = {"history": ps.get_hint_data_team(),
         "puzzle_id": ps.puzzle.shortname}
    self.return_json(d)


class YesterdayMetaDataHandler(util.TeamHandler):
  @login.required("team")
  def get(self):
    self.return_json(self.team.get_jukebox_data())


class ActionHandler(util.AdminHandler):
  def prepare(self):
    self.args = json.loads(self.request.body)

  @login.required("team", on_fail=http.client.UNAUTHORIZED)
  async def post(self):
    self.action = self.args.get("action", "")
    fn = getattr(self, "ACTION_" + self.action, None)
    if fn:
      await fn()
      await self.team.flush_messages()
    else:
      # Unknown (or no) "action" field.
      self.set_status(http.client.BAD_REQUEST.value)

  async def ACTION_update_phone(self):
    new_phone = self.args.get("phone", "").strip()
    if not new_phone:
      self.set_status(http.client.BAD_REQUEST.value)
      return
    self.team.update_phone(new_phone)
    self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_update_location(self):
    new_location = self.args.get("location", "").strip()
    if not new_location:
      self.set_status(http.client.BAD_REQUEST.value)
      return
    self.team.update_location(new_location)
    self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_apply_pennypass(self):
    land_name = self.args.get("land", "")
    if self.team.apply_fastpass(land_name):
      self.set_status(http.client.NO_CONTENT.value)
    else:
      return self.not_found()

  async def ACTION_hint_request(self):
    text = self.args["text"].rstrip()
    text = html.escape(text).replace("\n", "<br>")
    shortname = self.args["puzzle_id"]
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      return self.not_found()
    ps = self.team.puzzle_state[puzzle]
    if not ps.hints_available:
      self.set_status(http.client.BAD_REQUEST.value)
      return
    if self.team.current_hint_puzzlestate not in (None, ps):
      self.set_status(http.client.BAD_REQUEST.value)
      return
    self.team.add_hint_text(shortname, None, text)
    self.set_status(http.client.NO_CONTENT.value)
    await login.AdminUser.flush_messages()

  async def ACTION_cancel_hint(self):
    ps = self.team.current_hint_puzzlestate
    self.set_status(http.client.NO_CONTENT.value)
    if not ps:
      # Nothing to cancel
      return
    self.team.add_hint_text(ps.puzzle.shortname, None, None)
    await login.AdminUser.flush_messages()

  async def ACTION_cancel_submit(self):
    shortname = self.args.get("puzzle_id", "")
    submit_id = self.args.get("submit_id", -1)
    submit_id = int(submit_id)
    self.team.cancel_submission(submit_id, shortname)
    self.team.send_messages([{"method": "history_change", "puzzle_id": shortname}])
    self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_submit(self):
    if self.team.no_submit:
      self.write("Submit not allowed for this team.")
      self.set_status(http.client.CONFLICT.value)
      return
    answer = self.args["answer"]
    shortname = self.args["puzzle_id"]
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle: return self.not_found()
    submit_id = self.team.get_submit_id()
    result = self.team.submit_answer(submit_id, shortname, answer)
    if result == "":
      self.write(f"Invalid submission.")
      self.set_status(http.client.CONFLICT.value)
    elif result is not None:
      self.write(f"You've already submitted <b>{html.escape(result)}</b>.")
      self.set_status(http.client.CONFLICT.value)
    else:
      self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_adjust_offset(self):
    if not self.application.settings.get("debug"):
      self.set_status(http.client.BAD_REQUEST.value)
      return

    land = self.args["land"]
    icon = self.args["icon"]
    dx = int(self.args.get("dx", 0))
    dy = int(self.args.get("dy", 0))
    dw = int(self.args.get("dw", 0))

    land = game.Land.BY_SHORTNAME[land]
    icon = land.icons[icon]
    icon.offset = [icon.offset[0] + dx, icon.offset[1] + dy, icon.offset[2] + dw]
    self.team.dirty_lands.add(land.shortname)
    self.team.cached_mapdata.pop(land, None)
    self.set_status(http.client.NO_CONTENT.value)

class OffsetsPage(util.TeamPageHandler):
  def get(self):
    if not self.application.settings.get("debug"):
      self.set_status(http.client.BAD_REQUEST.value)
      return

    out = {}
    for land in game.Land.BY_SHORTNAME.values():
      d = {}
      for n, i in land.icons.items():
        if i.offset != [0,0,0]:
          d[n] = i.offset
      if d:
        out[land.shortname] = d
    text = yaml.dump(out)

    self.set_header("Content-Type", "text/plain")
    self.set_header("Cache-Control", "no-store")
    self.write(text)



def GetHandlers():
  handlers = [
    (r"/", PlayerHomePage),

    (r"/log", ActivityLogPage),
    (r"/about_the_park", AboutTheParkPage),
    (r"/rules", RulesPage),
    (r"/events", EventsPage),
    (r"/workshop", WorkshopPage),
    (r"/heart_of_the_park", RunaroundPage),
    (r"/puzzles", AllPuzzlesPage),
    (r"/errata", ErrataPage),
    (r"/guest_services$", GuestServicesPage),
    (r"/health_and_safety", HealthAndSafetyPage),
    (r"/sponsors", SponsorPage),
    (r"/land/([a-z0-9_]+)", LandMapPage),
    (r"/puzzle/([a-z0-9_]+)/?", PuzzlePage),

    (r"/offsets", OffsetsPage),

    (r"/action$", ActionHandler),

    (r"/js/submit/([a-z][a-z0-9_]*)$", SubmitHistoryHandler),
    (r"/js/log", ActivityLogDataHandler),
    (r"/js/videos", VideosDataHandler),
    (r"/js/hintsopen", HintsOpenDataHandler),
    (r"/js/puzzles", AllPuzzlesDataHandler),
    (r"/js/header", CurrentHeaderDataHandler),
    (r"/js/workshop", WorkshopDataHandler),
    (r"/js/map/([a-z][a-z0-9_]+)$", MapDataHandler),
    (r"/js/yes", YesterdayMetaDataHandler),
    (r"/js/hints/([a-z][a-z0-9_]*)$", HintHistoryHandler),
  ]

  return handlers

