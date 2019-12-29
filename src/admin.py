import asyncio
import datetime
import dateutil.parser
import hashlib
import html
import http.client
import itertools
import json
import time
import tornado.web
import unicodedata

import game
import login
import util
import wait_proxy

class AdminHomePage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    st = game.Global.STATE
    args = {"user": self.user,
            "game_state": st}

    if not st.event_start_time:
      d = datetime.datetime.fromtimestamp(st.expected_start_time)
      args["expected_start_time_text"] = d.ctime()

    self.render("admin_home.html", **args)


class AdminUsersPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_users.html",
                roles=login.AdminRoles.ROLES,
                users=login.AdminUser.all_users(),
                user=self.user)

class AdminServerPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_server.html")

class ServerDataHandler(util.AdminHandler):
  @login.required("admin")
  def get(self):
    stats = wait_proxy.Server.get_stats()

    keys = set()
    waits = 0
    proxy_load = []
    for p in stats:
      proxy_waits = 0
      for ts in p.values():
        keys.update(ts.keys())
        proxy_waits += sum(ts.values())
      proxy_load.append(proxy_waits)
      waits += proxy_waits

    d = {"waits": waits,
         "sessions": len(keys),
         "proxy_waits": proxy_load}

    self.return_json(d)

class ErrataPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_errata.html")

class ErrataDataHandler(util.AdminHandler):
  @login.required("admin")
  def get(self):
    d = game.Global.STATE.get_errata_data()
    self.return_json(d)

class ListTeamsPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_list_teams.html",
                teams=game.Team.BY_USERNAME)


class TeamPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self, username):
    self.get_team(username)
    label_info = game.Team.bb_label_info()
    self.render("admin_team_page.html", label_info=json.dumps({"lands": label_info}))

class TeamDataHandler(util.AdminHandler):
  @login.required("admin")
  def get(self, username):
    team = self.get_team(username)

    open_list = []
    for s in team.puzzle_state.values():
      if s.state == s.OPEN:
        d = {"shortname": s.puzzle.shortname,
             "open_time": s.open_time,
             "title": s.puzzle.title,
             "symbol": s.puzzle.land.symbol,
             "color": s.puzzle.land.color}
        if s.answers_found:
          af = list(s.answers_found)
          af.sort()
          d["answers_found"] = af
        open_list.append(((s.puzzle.land.land_order, s.open_time, s.puzzle.title), d))
    open_list.sort()
    open_list = [i[1] for i in open_list]

    d = {"open_puzzles": open_list,
         "fastpasses": team.fastpasses_available,
         "log": team.admin_log.get_data(),
         "svg": team.bb_data()["svg"],
         "score": team.score,
         "phone": html.escape(team.attrs.get("phone", "(unknown)"))}
    self.return_json(d)

class PuzzleContentPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self, which, shortname):
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      print(f"no puzzle called {shortname}")
      return self.not_found()

    if puzzle.icon.headerimage:
      supertitle=f'<img src="{puzzle.icon.headerimage}"><br>'
    else:
      supertitle=""

    self.pagepuzzle = puzzle
    if which == "puzzle":
      head = puzzle.html_head
      body = puzzle.html_body
    else:
      head = puzzle.solution_head
      body = puzzle.solution_body

    self.render("admin_puzzle_frame.html", supertitle=supertitle,
                head=head, body=body)

  def get_template_namespace(self):
    land = self.pagepuzzle.land
    d = super().get_template_namespace()
    d["css"] = [self.static_content["event.css"], self.static_content["admin-lite.css"]]
    css = f"{land.shortname}/land.css"
    if css in self.static_content:
      d["css"].append(self.static_content[css])
    else:
      d["css"].append(self.static_content["default.css"])
    return d


class PuzzlePage(util.AdminPageHandler):
  @login.required("admin")
  def get(self, shortname):
    self.get_puzzle(shortname)
    self.render("admin_puzzle_page.html")

class PuzzleDataHandler(util.AdminHandler):
  @login.required("admin")
  def get(self, shortname):
    puzzle = self.get_puzzle(shortname)

    errata = [e.to_json() for e in itertools.chain(game.Global.STATE.errata,
                                                   game.Global.STATE.reloads) if e.puzzle == puzzle]
    errata.sort(key=lambda x: x["when"])

    d = {"median_solve": puzzle.median_solve_duration,
         "open_count": len(puzzle.open_teams),
         "submitted_count": len(puzzle.submitted_teams),
         "solve_count": len(puzzle.solve_durations),
         "incorrect_answers": puzzle.incorrect_counts,
         "hint_time": puzzle.hints_available_time,
         "log": puzzle.puzzle_log.get_data(),
         "errata": errata,
         "hint_replies": puzzle.get_hint_reply_data()}
    self.return_json(d)

class FixPuzzlePage(util.AdminPageHandler):
  @login.required("edit_puzzles")
  def get(self, shortname):
    puzzle = self.get_puzzle(shortname)
    self.render("admin_fix_puzzle_page.html", puzzle_path=getattr(puzzle, "path", None))

class TeamPuzzlePage(util.AdminPageHandler):
  @login.required("admin")
  def get(self, username, shortname):
    team = self.get_team(username)
    puzzle = self.get_puzzle(shortname)
    self.render("admin_team_puzzle_page.html")


class TeamPuzzleDataHandler(util.AdminHandler):
  @login.required("admin")
  def get(self, username, shortname):
    team = self.get_team(username)
    ps = team.get_puzzle_state(shortname)
    if not ps:
      return self.not_found()

    d = {"history": ps.get_hint_data_admin(),
         "submits": [sub.json_dict() for sub in ps.submissions],
         "hints_open": ps.hints_available,
         "state": ps.state}
    if ps.open_time: d["open_time"] = ps.open_time
    if ps.solve_time: d["solve_time"] = ps.solve_time
    if ps.claim:
      d["claim"] = ps.claim.fullname

    self.return_json(d)


class BecomeTeamHandler(util.AdminPageHandler):
  @login.required("admin")
  def get(self, username, confirmed):
    team = self.get_team(username)

    if confirmed:
      domain = self.request.headers.get("host", None)
      if not domain:
        print(f"Missing host header")
        domain = "pennypark.fun"

      # Create a new player session for this team.
      session = login.Session(login.Session.PLAYER_COOKIE_NAME)
      session.team = team
      session.capabilities = {"team"}
      session.was_admin = True
      team.attach_session(session)
      session.set_cookie(self, domain)

      self.redirect("/")
    else:
      self.render("admin_become.html", team=team)


class ListPuzzlesPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_list_puzzles.html",
                lands=game.Land.ordered_lands)


class PuzzlePage(util.AdminPageHandler):
  @login.required("admin")
  def get(self, shortname):
    puzzle = self.get_puzzle(shortname)

    solve_list = []
    for t, d in puzzle.solve_durations.items():
      solve_list.append((d, t, util.format_duration(d)))
    solve_list.sort()

    self.render("admin_puzzle_page.html", solve_list=solve_list)


class CreateUserHandler(util.AdminHandler):
  @login.required(login.AdminRoles.CREATE_USERS)
  async def post(self):
    username = self.get_argument("username")
    fullname = self.get_argument("fullname")
    password = self.get_argument("password")
    if login.AdminUser.get_by_username(username) is not None:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST, "User already exists")
    pwhash = await login.AdminUser.hash_password(password)
    login.AdminUser.create_new_user(username, pwhash, fullname)
    self.redirect("/admin/users")

class ChangePasswordHandler(util.AdminHandler):
  @login.required("admin")
  async def post(self):
    username = self.get_argument("team_username", None)
    password = self.get_argument("password", None)
    new_password = self.get_argument("newpassword")
    confirm = self.get_argument("confirm")

    if login.AdminRoles.CREATE_USERS in self.user.roles:
      change_user = login.AdminUser.get_by_username(username)
      if not change_user:
        raise tornado.web.HTTPError(http.client.BAD_REQUEST, "No such user")
    else:
      change_user = self.user
      if not password:
        raise tornado.web.HTTPError(http.client.BAD_REQUEST, "Current password not correct")
      password = password
      if not await change_user.check_password(password):
        raise tornado.web.HTTPError(http.client.BAD_REQUEST, "Current password not correct")

    if new_password != confirm:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST, "New passwords don't match")

    change_user.update_pwhash(await change_user.hash_password(new_password))
    self.redirect("/admin/users")


class ChangeStartPage(util.AdminPageHandler):
  @login.required(login.AdminRoles.CONTROL_EVENT)
  def get(self):
    new_time_text = self.get_argument("start_time", None)
    if not new_time_text:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST,
                                  "No new time given")
    new_time = dateutil.parser.parse(new_time_text)
    new_timestamp = int(new_time.timestamp())
    from_now = new_timestamp - time.time()
    if from_now < 5:
      self.render("admin_change_start.html",
                  error="Time is in the past (or not far enough in the future).")
      return

    confirm_text = new_time.ctime()

    self.render("admin_change_start.html",
                confirm_text=confirm_text,
                new_timestamp=new_timestamp,
                error=None)

class ConfirmChangeStartPage(util.AdminPageHandler):
  @login.required(login.AdminRoles.CONTROL_EVENT)
  def get(self):
    new_timestamp = self.get_argument("new_start", None)
    if not new_timestamp:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST,
                                  "No new time given")
    new_timestamp = int(new_timestamp)
    game.Global.STATE.update_event_start(new_timestamp)
    self.redirect("/admin")


class StartEvent(util.AdminHandler):
  @login.required(login.AdminRoles.CONTROL_EVENT)
  def get(self):
    game.Global.STATE.start_event()
    self.redirect("/admin")


class TaskQueuePage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_task_queue.html")

class TaskQueueHandler(util.AdminHandler):
  @login.required("admin")
  def get(self):
    self.return_json(game.Global.STATE.task_queue.to_json())

class PuzzleJsonHandler(util.AdminHandler):
  @classmethod
  def build(cls):
    out = []
    for p in game.Puzzle.all_puzzles():
      out.append([p.shortname, p.title, p.bbid])
    out.sort()
    cls.body = "var puzzle_list = " + json.dumps(out) + ";\n"
    h = hashlib.md5(cls.body.encode("utf-8")).hexdigest()[:12]
    cls.etag = h
    util.AdminPageHandler.set_attribute("puzzle_json_url", "/admin/puzzle_json/" + h)

  @login.required("admin")
  async def get(self):
    self.set_header("Content-Type", "application/json")
    self.set_header("Cache-Control", "private, max-age=3600")
    self.set_header("ETag", self.etag)
    self.write(self.body)

class TeamJsonHandler(util.AdminHandler):
  @classmethod
  def build(cls):
    out = []
    for t in game.Team.all_teams():
      name = t.name
      for k in name:
        if unicodedata.category(k)[0] == "L":
          break
      else:
        name += f" ({t.username})"
      out.append([t.username, name])
    out.sort()
    cls.body = "var team_list = " + json.dumps(out) + ";\n"
    h = hashlib.md5(cls.body.encode("utf-8")).hexdigest()[:12]
    cls.etag = h
    util.AdminPageHandler.set_attribute("team_json_url", "/admin/team_json/" + h)

  @login.required("admin")
  async def get(self):
    self.set_header("Content-Type", "application/json")
    self.set_header("Cache-Control", "private, max-age=3600")
    self.set_header("ETag", self.etag)
    self.write(self.body)


class BigBoardPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    label_info = game.Team.bb_label_info()
    self.render("admin_bigboard.html", label_info=json.dumps({"lands": label_info}))

class BigBoardTaskQueueDataHandler(util.AdminHandler):
  @login.required("admin")
  def get(self):
    self.return_json(game.Global.STATE.bb_task_queue_data())

class BigBoardTeamDataHandler(util.AdminHandler):
  @login.required("admin")
  def get(self, username):
    if username:
      username = username.lstrip("/")
      team = game.Team.get_by_username(username)
      if not team:
        return self.not_found()
      data = team.bb_data()
    else:
      data = {}
      for t in game.Team.all_teams():
        data[t.username] = t.bb_data()
    self.return_json(data)


class ActionHandler(util.AdminHandler):
  def prepare(self):
    self.args = json.loads(self.request.body)

  @login.required("admin")
  async def post(self):
    self.action = self.args.get("action", "")
    fn = getattr(self, "ACTION_" + self.action, None)
    if fn:
      await fn()
    else:
      # Unknown (or no) "action" field.
      self.set_status(http.client.BAD_REQUEST.value)

  async def ACTION_bestow_fastpass(self):
    username = self.args.get("team_username", None)
    duration = CONSTANTS["pennypass_expiration_sec"]
    if username is None:
      # User must have CONTROL_EVENT to give all teams a pass.
      if not self.user.has_role(login.AdminRoles.CONTROL_EVENT):
        self.set_status(http.client.UNAUTHORIZED.value)
        return

      for team in game.Team.all_teams():
        team.bestow_fastpass(duration, self.user.username)
    else:
      team = self.get_team(username)
      team.bestow_fastpass(duration, self.user.username)
    self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_update_hint_time(self):
    shortname = self.args.get("puzzle_id")
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      return self.not_found()

    try:
      text = self.args.get("hint_time")
      text = text.split(":")
      while text and not text[0]: text.pop(0)
      text = [int(t, 10) for t in text]

      secs = 0
      if text: secs += text.pop()
      if text: secs += 60 * text.pop()
      if text: secs += 3600 * text.pop()
      if text:
        raise tornado.web.HTTPError(http.client.BAD_REQUEST)

    except (KeyError, ValueError):
      raise tornado.web.HTTPError(http.client.BAD_REQUEST)

    if secs < 0:
      secs = 0

    puzzle.set_hints_available_time(secs, self.user.username)
    self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_add_note(self):
    username = self.args.get("team_username")
    team = self.get_team(username)

    text = self.args.get("text")
    if not text:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST)
    text = text.strip()
    if text:
      text = html.escape(text).replace("\n", "<br>")
      team.add_admin_note(self.user.fullname, text)

    self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_hint_reply(self):
    username = self.args.get("team_username")
    team = self.get_team(username)

    shortname = self.args.get("puzzle_id")
    puzzle = self.get_puzzle(shortname)

    text = self.args.get("text", None)
    if text:
      text = text.rstrip()
      text = html.escape(text).replace("\n", "<br>")
      team.add_hint_text(shortname, self.session.user.username, text)
    else:
      team.hint_no_reply(shortname, self.session.user.username)

    await team.flush_messages()
    self.set_status(http.client.NO_CONTENT.value)


  async def ACTION_fix_puzzle(self):
    if login.AdminRoles.EDIT_PUZZLES not in self.user.roles:
      self.set_status(http.client.UNAUTHORIZED.value)
      return

    puzzle = self.get_puzzle(self.args.get("puzzle_id"))
    text = self.args.get("text", None)
    do_reload = self.args.get("reload", None)

    print(f"fixing puzzle {puzzle} reload: {not not do_reload} text: {not not text}")
    message = ""
    if do_reload:
      message = puzzle.reload()
      if message:
        d = {"success": False,
             "message": f"Error: {message}<br>(Errata was not posted.)"}
        self.return_json(d)
      message = "Puzzle updated."
      game.Global.STATE.save_reload(puzzle.shortname, self.user.username)

    if text:
      game.Global.STATE.post_erratum(puzzle.shortname, text, self.user.username)
      message += " Erratum posted."
    for t in puzzle.open_teams:
      t.cached_errata_data = None
      t.send_messages([{"method": "history_change", "puzzle_id": puzzle.shortname},
                       {"method": "post_erratum", "title": puzzle.title}])
      await t.flush_messages()
    login.AdminUser.send_messages([{"method": "update", "puzzle_id": puzzle.shortname}])
    await login.AdminUser.flush_messages()

    d = {"success": True, "message": message}
    self.return_json(d)

  async def ACTION_update_claim(self):
    task_key = self.args.get("key")
    unclaim = (self.args.get("which") == "unclaim")

    if task_key.startswith("t-"):
      if unclaim:
        game.Global.STATE.claim_task(task_key, None)
      else:
        game.Global.STATE.claim_task(task_key, self.user.username)
    elif task_key.startswith("h-"):
      _, username, shortname = task_key.split("-")
      team = self.get_team(username)
      puzzle = self.get_puzzle(shortname)
      ps = team.puzzle_state[puzzle]
      if unclaim:
        if ps.claim:
          ps.claim = None
          team.invalidate(puzzle)
          game.Global.STATE.task_queue.change()
      else:
        if ps.claim is None:
          ps.claim = self.user
          team.invalidate(puzzle)
          game.Global.STATE.task_queue.change()
    self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_complete_task(self):
    task_key = self.args.get("key")
    undone = (self.args.get("which") == "undone")
    if self.args.get("immediate"):
      # do it now.
      game.Global.STATE.complete_task(task_key)
    else:
      # 5-second undo period
      game.Global.STATE.mark_task_complete(task_key, not not undone)
    self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_update_admin_role(self):
    if login.AdminRoles.CREATE_USERS not in self.user.roles:
      self.set_status(http.client.UNAUTHORIZED.value)
      return

    username = self.args.get("username")
    role = self.args.get("role")
    which = self.args.get("which")

    if role not in login.AdminRoles.ROLES:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST)
    user = login.AdminUser.get_by_username(username)
    if user is None:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST)
    user.update_role(role, which == "set")
    self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_reset_spam(self):
    username = self.args.get("team_username")
    team = self.get_team(username)
    shortname = self.args.get("puzzle_id")
    puzzle = game.Puzzle.get_by_shortname(shortname)
    team.reset_spam(shortname, self.user.username)

    team.send_messages([{"method": "history_change", "puzzle_id": shortname}])
    await team.flush_messages()
    team.invalidate(puzzle)

    self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_open_all_lands(self):
    # User must have CONTROL_EVENT to open all lands
    if not self.user.has_role(login.AdminRoles.CONTROL_EVENT):
      self.set_status(http.client.UNAUTHORIZED.value)
      return

    for team in game.Team.all_teams():
      team.open_all_lands()
      await team.flush_messages()

    self.set_status(http.client.NO_CONTENT.value)

  async def ACTION_open_all_puzzles(self):
    # User must have CONTROL_EVENT to open all puzzles
    if not self.user.has_role(login.AdminRoles.CONTROL_EVENT):
      self.set_status(http.client.UNAUTHORIZED.value)
      return

    for team in game.Team.all_teams():
      team.open_all_puzzles()
      await team.flush_messages()

    self.set_status(http.client.NO_CONTENT.value)




class VisitPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self, mode):
    if not mode:
      self.render("admin_visit.html", mode="select", js="", team_data="null")
    else:
      looking_for = f"-{mode}-visit"
      teams = {}
      ordered = []
      for t in game.Global.STATE.task_queue.tasks.values():
        if t.key.endswith(looking_for):
          ordered.append((t.team.name, t.team.username))
          teams[t.team.username] = {"name": t.team.name,
                                    "location": t.team.attrs.get("location", "(unknown)"),
                                    "phone": t.team.attrs.get("phone", "(unknown)"),
                                    "key": t.key}
      ordered.sort()
      if self.application.settings.get("debug"):
        script = ("""<script src="/closure/goog/base.js"></script>\n"""
                  """<script src="/debug/snellen/src/visit.js"></script>""")
      else:
        script = f"""<script src="{self.static_content["visit-compiled.js"]}"></script>"""

      self.render("admin_visit.html", mode=mode, teams=teams,
                  ordered=[x[1] for x in ordered],
                  team_data=json.dumps(teams), js=script)

class ConciergeHandler(util.AdminHandler):
  @login.required("admin")
  async def get(self):
    print("starting handler")
    username = self.get_argument('u', None)
    submit_id = self.get_argument('s', None)
    result = self.get_argument('result', None)
    team = game.Team.get_by_username(username)
    if not team: return self.not_found()

    print(f"team is {team}")
    if result not in ("no_answer", "wrong_number", "complete", "correct"):
      return self.not_found()

    print(f"result is {result}")

    try:
      submit_id = int(submit_id)
    except ValueError:
      return self.not_found()

    team.concierge_update(submit_id, result)

    team.send_messages([{"method": "history_change", "puzzle_id": "concierge_services"}])
    await team.flush_messages()

    task_key = f"t-{team.username}-concierge-callback-{submit_id}"
    game.Global.STATE.complete_task(task_key)

    self.redirect("/admin/taskqueue")


def GetHandlers():
  handlers = [
    (r"/admin$", AdminHomePage),

    (r"/admin/bigboard$", BigBoardPage),
    (r"/admin/change_start$", ChangeStartPage),
    (r"/admin/confirm_change_start$", ConfirmChangeStartPage),
    (r"/admin/taskqueue$", TaskQueuePage),
    (r"/admin/puzzle/([a-z0-9_]+)$", PuzzlePage),
    (r"/admin/fix/([a-z0-9_]+)$", FixPuzzlePage),
    (r"/admin/show/(puzzle|solution)/([a-z0-9_]+)$", PuzzleContentPage),
    (r"/admin/puzzles$", ListPuzzlesPage),
    (r"/admin/team/([a-z0-9_]+)$", TeamPage),
    (r"/admin/team/([a-z0-9_]+)/puzzle/([a-z0-9_]+)$", TeamPuzzlePage),
    (r"/admin/teams$", ListTeamsPage),
    (r"/admin/users$", AdminUsersPage),
    (r"/admin/server$", AdminServerPage),
    (r"/admin/visit(?:/(penny|loony))?$", VisitPage),
    (r"/admin/errata$", ErrataPage),

    (r"/admin/action$", ActionHandler),
    (r"/admin/become/([a-z0-9_]+)(/confirmed)?$", BecomeTeamHandler),
    (r"/admin/change_password$", ChangePasswordHandler),
    (r"/admin/create_user$", CreateUserHandler),
    (r"/admin/concierge$", ConciergeHandler),

    (r"/admin/puzzle_json/.*", PuzzleJsonHandler),
    (r"/admin/team_json/.*", TeamJsonHandler),
    (r"/admin/js/team/([a-z0-9_]+)$", TeamDataHandler),
    (r"/admin/js/puzzle/([a-z0-9_]+)$", PuzzleDataHandler),
    (r"/admin/js/teampuzzle/([a-z0-9_]+)/([a-z0-9_]+)$", TeamPuzzleDataHandler),
    (r"/admin/js/server$", ServerDataHandler),
    (r"/admin/js/taskqueue$", TaskQueueHandler),
    (r"/admin/js/bbtaskqueue$", BigBoardTaskQueueDataHandler),
    (r"/admin/js/bbteam(/[a-z0-9_]+)?$", BigBoardTeamDataHandler),
    (r"/admin/js/errata$", ErrataDataHandler),
    ]
  return handlers





