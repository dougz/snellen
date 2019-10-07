import datetime
import dateutil.parser
import hashlib
import html
import http.client
import json
import time
import tornado.web

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

class UpdateAdminRoleHandler(tornado.web.RequestHandler):
  @login.required(login.AdminRoles.CREATE_USERS)
  def get(self, action, username, role):
    if role not in login.AdminRoles.ROLES:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST)
    user = login.AdminUser.get_by_username(username)
    if user is None:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST)
    user.update_role(role, action == "set")
    self.set_status(http.client.NO_CONTENT.value)

class ListTeamsPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_list_teams.html",
                teams=game.Team.BY_USERNAME)


class TeamPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self, username):
    team = game.Team.get_by_username(username)
    if not team:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    now = time.time()
    open_list = []
    for s in team.puzzle_state.values():
      if s.state == s.OPEN:
        open_list.append((s.open_time, s.puzzle, s.answers_found))
    open_list.sort()

    self.render("admin_team_page.html", team=team, open_list=open_list, log=team.admin_log)

class TeamPuzzlePage(util.AdminPageHandler):
  @login.required("admin")
  def get(self, username, shortname):
    team = game.Team.get_by_username(username)
    if not team:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    state = team.puzzle_state[puzzle]
    if state.state == state.SOLVED:
      dur = state.solve_time - state.open_time
      dur = "(" + util.format_duration(dur) + " after open)"
    else:
      dur = ""

    self.render("admin_team_puzzle_page.html",
                team=team, puzzle=puzzle, state=state, solve_duration=dur)


class HintHistoryHandler(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self, team_username, shortname):
    team = game.Team.get_by_username(team_username)
    if not team:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    state = team.get_puzzle_state(shortname)
    if not state:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    d = {"history": [msg.json_dict(for_admin=True) for msg in state.hints]}
    if state.claim:
      d["claim"] = state.claim.fullname
    self.set_header("Content-Type", "application/json")
    self.write(json.dumps(d))


class BestowFastpassHandler(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self, team_username):
    team = game.Team.get_by_username(team_username)
    if not team:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    team.receive_fastpass(300)
    self.set_status(http.client.NO_CONTENT.value)


class BecomeTeamHandler(util.AdminPageHandler):
  @login.required("admin", clear_become=False)
  def get(self, team_username):
    team = game.Team.get_by_username(team_username)
    if not team:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    if self.session.pending_become == team:
      self.session.team = team
      self.session.user = None
      self.session.capabilities = {"team"}
      self.session.was_admin = True
      self.session.next_msg_serial = 1
      self.session.pending_become = None
      team.attach_session(self.session)
      self.redirect("/")
    else:
      self.session.pending_become = team
      self.render("admin_become.html", team=team)


class HintReplyHandler(tornado.web.RequestHandler):
  def prepare(self):
    self.args = json.loads(self.request.body)

  @login.required("admin")
  async def post(self):
    team_username = self.args.get("team_username")
    team = game.Team.get_by_username(team_username)
    if not team:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    shortname = self.args.get("puzzle_id");
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    text = self.args.get("text", "").strip()
    if not text:
      raise tornado.web.HTTPError(http.client.BAD_REQUEST)
    text = html.escape(text).replace("\n", "<br>")

    team.add_hint_text(shortname, self.session.user.username, text)
    await team.flush_messages()
    await login.AdminUser.flush_messages()
    self.set_status(http.client.NO_CONTENT.value)


class ListPuzzlesPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_list_puzzles.html",
                lands=game.Land.ordered_lands)


class PuzzlePage(util.AdminPageHandler):
  @login.required("admin")
  def get(self, shortname):
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    solve_list = []
    for t, d in puzzle.solve_durations.items():
      solve_list.append((d, t, util.format_duration(d)))
    solve_list.sort()

    self.render("admin_puzzle_page.html", puzzle=puzzle, solve_list=solve_list)


class CreateUserHandler(tornado.web.RequestHandler):
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

class ChangePasswordHandler(tornado.web.RequestHandler):
  @login.required("admin")
  async def post(self):
    username = self.get_argument("username", None)
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
    if from_now < 60:
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


class StartEvent(tornado.web.RequestHandler):
  @login.required(login.AdminRoles.CONTROL_EVENT)
  def get(self):
    game.Global.STATE.start_event()
    self.redirect("/admin")


class HintQueuePage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_hint_queue.html")

class HintQueueHandler(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.set_header("Content-Type", "application/json")
    self.write(game.Global.STATE.hint_queue.to_json())

class HintClaimHandler(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self, un, username, shortname):
    team = game.Team.get_by_username(username)
    if not team:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    ps = team.puzzle_state[puzzle]
    if un:
      if ps.claim:
        ps.claim = None
        login.AdminUser.send_messages([{"method": "hint_history",
                                        "team_username": team.username,
                                        "puzzle_id": puzzle.shortname}])
        game.Global.STATE.hint_queue.change()
    else:
      if ps.claim is None:
        ps.claim = self.user
        login.AdminUser.send_messages([{"method": "hint_history",
                                        "team_username": team.username,
                                        "puzzle_id": puzzle.shortname}])
        game.Global.STATE.hint_queue.change()

    self.redirect(f"/admin/team/{username}/puzzle/{shortname}")

class HintTimeChangeHandler(tornado.web.RequestHandler):
  def prepare(self):
    self.args = json.loads(self.request.body)

  @login.required("admin")
  async def post(self):
    shortname = self.args.get("puzzle_id")
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    try:
      text = self.args.get("hint_time")
      text = text.split(":")
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

class PuzzleJsonHandler(tornado.web.RequestHandler):
  @classmethod
  def build(cls):
    out = []
    for p in game.Puzzle.all_puzzles():
      out.append([p.shortname, p.title])
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

class TeamJsonHandler(tornado.web.RequestHandler):
  @classmethod
  def build(cls):
    out = []
    for t in game.Team.all_teams():
      out.append([t.username, t.name])
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
    self.render("admin_bigboard.html")

class BigBoardHintQueueDataHandler(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    data = game.Global.STATE.bb_hint_queue_data()
    self.set_header("Content-Type", "application/json")
    self.write(json.dumps(data))

class BigBoardTeamDataHandler(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self, username):
    if username:
      username = username.lstrip("/")
      team = game.Team.get_by_username(username)
      if not team:
        raise tornado.web.HTTPError(http.client.NOT_FOUND)
      data = team.bb_data()
    else:
      data = {}
      for t in game.Team.all_teams():
        data[t.username] = t.bb_data()
    self.set_header("Content-Type", "application/json")
    self.write(json.dumps(data))




def GetHandlers():
  handlers = [
    (r"/admin$", AdminHomePage),

    (r"/admin/bigboard$", BigBoardPage),
    (r"/admin/change_start$", ChangeStartPage),
    (r"/admin/confirm_change_start$", ConfirmChangeStartPage),
    (r"/admin/hintqueue$", HintQueuePage),
    (r"/admin/puzzle/([a-z0-9_]+)$", PuzzlePage),
    (r"/admin/puzzles$", ListPuzzlesPage),
    (r"/admin/team/([a-z0-9_]+)$", TeamPage),
    (r"/admin/team/([a-z0-9_]+)/puzzle/([a-z0-9_]+)$", TeamPuzzlePage),
    (r"/admin/teams$", ListTeamsPage),
    (r"/admin/users$", AdminUsersPage),

    (r"/admin/(set|clear)_role/([^/]+)/([^/]+)$", UpdateAdminRoleHandler),
    (r"/admin/(un)?claim/([a-z0-9_]+)/([a-z0-9_]+)$", HintClaimHandler),
    (r"/admin/become/([a-z0-9_]+)$", BecomeTeamHandler),
    (r"/admin/bestowfastpass/([a-z0-9_]+)$", BestowFastpassHandler),
    (r"/admin/bb/hintqueue$", BigBoardHintQueueDataHandler),
    (r"/admin/bb/team(/[a-z0-9_]+)?$", BigBoardTeamDataHandler),
    (r"/admin/change_password$", ChangePasswordHandler),
    (r"/admin/create_user$", CreateUserHandler),
    (r"/admin/hinthistory/([a-z0-9_]+)/([a-z0-9_]+)$", HintHistoryHandler),
    (r"/admin/hintqueuedata$", HintQueueHandler),
    (r"/admin/hintreply$", HintReplyHandler),
    (r"/admin/hinttimechange$", HintTimeChangeHandler),

    (r"/admin/puzzle_json/.*", PuzzleJsonHandler),
    (r"/admin/team_json/.*", TeamJsonHandler),
    ]
  return handlers





