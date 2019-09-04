import http.client
import tornado.web

import datetime
import dateutil.parser
import game
import json
import login
import time
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

class UpdateAdminRole(tornado.web.RequestHandler):
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


class AdminTeamPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self, username):
    team = game.Team.get_by_username(username)
    if not team:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    now = time.time()
    open_list = []
    for s in team.puzzle_state.values():
      if s.state == s.OPEN:
        open_list.append((s.open_time, s.puzzle, util.format_duration(now-s.open_time), s.answers_found))
    open_list.sort()

    log = []
    for e in team.activity_log[-100:]:
      d = datetime.datetime.fromtimestamp(e.when)
      log.append((d.strftime("%a %H:%M:%S"), e.for_admin))

    self.render("admin_team_page.html", team=team, open_list=open_list, log=log)

class AdminTeamPuzzlePage(util.AdminPageHandler):
  @login.required("admin")
  def get(self, username, shortname):
    team = game.Team.get_by_username(username)
    if not team:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)

    self.render("admin_team_puzzle_page.html",
                team=team, puzzle=puzzle, state=team.puzzle_state[puzzle])

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

    team.add_hint_text(shortname, self.session.user.username, text)
    await team.flush_messages()
    self.set_status(http.client.NO_CONTENT.value)


class ListPuzzlesPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_list_puzzles.html",
                puzzles=game.Puzzle.BY_SHORTNAME)


class AdminPuzzlePage(util.AdminPageHandler):
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


class CreateUser(tornado.web.RequestHandler):
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


class StopServerPage(util.AdminPageHandler):
  @login.required(login.AdminRoles.CONTROL_EVENT)
  async def get(self):
    self.write("Stopping server\u2026")
    await wait_proxy.Server.exit()
    await game.Global.STATE.stop_server()


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


def GetHandlers():
  handlers = [
    (r"/admin$", AdminHomePage),
    (r"/admin/users$", AdminUsersPage),
    (r"/(set|clear)_admin_role/([^/]+)/([^/]+)$", UpdateAdminRole),
    (r"/create_user$", CreateUser),
    (r"/change_start$", ChangeStartPage),
    (r"/confirm_change_start$", ConfirmChangeStartPage),
    (r"/stop_server$", StopServerPage),
    (r"/admin/teams$", ListTeamsPage),
    (r"/admin/team/([a-z0-9_]+)$", AdminTeamPage),
    (r"/admin/teampuzzle/([a-z0-9_]+)/([a-z0-9_]+)$", AdminTeamPuzzlePage),
    (r"/admin/puzzles$", ListPuzzlesPage),
    (r"/admin/puzzle/([a-z0-9_]+)$", AdminPuzzlePage),
    (r"/hintreply", HintReplyHandler),
    ]
  return handlers





