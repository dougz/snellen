import http.client
import tornado.web

import game
import login
import util

class AdminHomePage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):

    self.render("admin_home.html",
                user=self.user,
                game_state=game.Global.STATE,
                sessions=len(login.Session.BY_KEY))


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


class ShowTeamsPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("teams.html", user=self.user,
                teams=game.Team.BY_USERNAME)


class ShowPuzzlesPage(util.AdminPageHandler):
  @login.required("admin")
  def get(self):
    self.render("puzzles.html", user=self.user,
                puzzles=game.Puzzle.BY_SHORTNAME)


class CreateUser(tornado.web.RequestHandler):
  @login.required(login.AdminRoles.CREATE_USERS)
  def post(self):
    username = self.get_argument("username")
    fullname = self.get_argument("fullname")
    password = self.get_argument("password")

    if login.AdminUser.get_by_username(username) is not None:
      # error
      raise tornado.web.HTTPError(http.client.BAD_REQUEST,
                                  "User already exists")


    login.AdminUser(username, login.make_hash(password), fullname, ())
    self.redirect("/admin_users")


class StopServerPage(util.AdminPageHandler):
  def initialize(self, answer_checking):
    self.answer_checking = answer_checking

  @login.required(login.AdminRoles.CONTROL_EVENT)
  def get(self):
    self.answer_checking.stop()
    loop = tornado.ioloop.IOLoop.current()
    loop.call_later(1.5, loop.stop)
    self.write("Stopping server\u2026")


class StartEvent(tornado.web.RequestHandler):
  @login.required(login.AdminRoles.CONTROL_EVENT)
  def get(self):
    game.Global.STATE.start_event()
    self.redirect("/admin")

# Debug-only handlers that reread the source file each time.

class AdminJS(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.set_header("Content-Type", "text/javascript; charset=utf-8")
    with open("src/admin.js", "rb") as f:
      self.write(f.read())

class AdminCSS(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.set_header("Content-Type", "text/css; charset=utf-8")
    with open("static/admin.css", "rb") as f:
      self.write(f.read())


def GetHandlers(debug, answer_checking):
  handlers = [
    (r"/admin", AdminHomePage),
    (r"/admin_users", AdminUsersPage),
    (r"/(set|clear)_admin_role/([^/]+)/([^/]+)", UpdateAdminRole),
    (r"/create_user", CreateUser),
    (r"/start_event", StartEvent),
    (r"/stop_server", StopServerPage, {"answer_checking": answer_checking}),
    (r"/teams", ShowTeamsPage),
    (r"/puzzles", ShowPuzzlesPage),
    ]
  if debug:
    handlers.append((r"/admin.js", AdminJS))
    handlers.append((r"/admin.css", AdminCSS))
  return handlers





