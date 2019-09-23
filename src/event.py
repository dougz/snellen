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
  NEW_PUZZLE_SECONDS = 300  # 5 minutes

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
    mapdata = {"base_url": land.base_img}
    now = time.time()

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
            d["mask_url"] = i.unlocked_mask.url
            d["pos_x"], d["pos_y"] = i.unlocked.pos
            d["width"], d["height"] = i.unlocked.size
            if i.unlocked.poly: d["poly"] = i.unlocked.poly

          if (now - st.open_time < self.NEW_PUZZLE_SECONDS and
              st.open_time != game.Global.STATE.event_start_time):
            d["new_open"] = True

        elif st.state == game.PuzzleState.SOLVED:
          d["solved"] = True
          if i.solved.url:
            d["icon_url"] = i.solved.url
            d["mask_url"] = i.solved_mask.url
            d["pos_x"], d["pos_y"] = i.solved.pos
            d["width"], d["height"] = i.solved.size
            if i.solved.poly: d["poly"] = i.solved.poly

        items.append((p.sortkey, d))
      else:
        if i.to_land not in self.team.open_lands: continue
        d = { "name": i.to_land.title,
              "url": i.to_land.url,
              "icon_url": i.unlocked.url }
        d["pos_x"], d["pos_y"] = i.unlocked.pos
        d["width"], d["height"] = i.unlocked.size
        if i.unlocked.poly: d["poly"] = i.unlocked.poly
        items.append((i.to_land.sortkey, d))

    items.sort()
    mapdata["items"] = [i[1] for i in items]

    json_data = "<script>var mapdata = """ + json.dumps(mapdata) + ";</script>"

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
        json_data = "<script>var open_time = """ + str(game.Global.STATE.expected_start_time) + ";</script>"
        self.render("not_started.html", json_data=json_data,
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
    if self.application.settings.get("debug"):
      d["css"].append(f"/debug/assets/{land.shortname}/land.css")
    else:
      css = f"{land.shortname}/land.css"
      if css in self.static_content:
        d["css"].append(self.static_content[css])
    if self.puzzle.emojify:
      # TODO: consider hosting these locally
      d["css"].append(
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css")
      d["script"] += """
        <script src="https://twemoji.maxcdn.com/v/latest/twemoji.min.js" crossorigin="anonymous"></script>
        """
      if self.application.settings.get("debug"):
        d["script"] += """<script>var edb = "/debug/static/emojisprite.json";</script>"""
      else:
        d["script"] += f"""<script>var edb = "{self.static_content["emoji.json"]}";</script>"""

    return d


class ActivityLogPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.session.visit_page("activity")
    temp_log = [(a.when, a.for_team) for a in self.team.activity_log if a.for_team is not None]
    json_data = """<script>var log_entries = """ + json.dumps(temp_log) + ";</script>"
    self.render("activity_log.html", json_data=json_data)

class AchievementPage(util.TeamPageHandler):
  @login.required("team")
  def get(self):
    self.session.visit_page("pins")
    self.render("achievements.html", achievements=game.Achievement.ALL)

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
    text = self.args["text"]
    shortname = self.args["puzzle_id"]
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    if not puzzle.hints_available:
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
    (r"/health_and_safety", HealthAndSafetyPage),
    (r"/land/([a-z0-9_]+)", LandMapPage),
    (r"/puzzle/([a-z0-9_]+)/?", PuzzlePage),
    (r"/submit", SubmitHandler),
    (r"/submit_history/([a-z][a-z0-9_]*)", SubmitHistoryHandler),
    (r"/submit_cancel/([a-z][a-z0-9_]*)/(\d+)", SubmitCancelHandler),
    (r"/hintrequest", HintRequestHandler),
    (r"/hinthistory/([a-z][a-z0-9_]*)", HintHistoryHandler),
  ]

  return handlers

