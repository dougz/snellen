import http.client
import tornado.web

import game
import login

class AdminHome(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_home.html", user=self.user, script=None)


class AdminUsers(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    if self.application.settings.get("debug"):
      script = ("""<script src="/closure/goog/base.js"></script>\n"""
                """<script src="/admin-debug.js"></script>""")
    else:
      script = """<script src="/admin.js"></script>"""
    script += """<script>\nwindow.onload = activateRoleCheckboxes;\n</script>"""

    self.render("admin_users.html",
                script=script,
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


class ShowTeams(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.render("teams.html", user=self.user,
                teams=game.Team.BY_USERNAME, script=None)


class ShowPuzzles(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.render("puzzles.html", user=self.user,
                puzzles=game.Puzzle.BY_SHORTNAME, script=None)


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


class StopServer(tornado.web.RequestHandler):
  def initialize(self, answer_checking):
    self.answer_checking = answer_checking

  @login.required(login.AdminRoles.CONTROL_EVENT)
  def get(self):
    self.answer_checking.stop()
    loop = tornado.ioloop.IOLoop.current()
    loop.call_later(1.5, loop.stop)
    self.write("Stopping server\u2026")


class AdminDebugJS(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.set_header("Content-Type", "text/javascript")
    with open("src/admin.js", "rb") as f:
      self.write(f.read())

class AdminJS(tornado.web.RequestHandler):
  def initialize(self, compiled_admin_js):
    self.compiled_admin_js = compiled_admin_js
  @login.required("admin")
  def get(self):
    self.set_header("Content-Type", "text/javascript")
    self.write(self.compiled_admin_js)

class AdminCSS(tornado.web.RequestHandler):
  def initialize(self, admin_css):
    self.admin_css = admin_css
  @login.required("admin")
  def get(self):
    self.set_header("Content-Type", "text/css")
    self.write(self.admin_css)


def GetHandlers(debug, answer_checking, admin_css, compiled_admin_js):
  handlers = [
    (r"/admin", AdminHome),
    (r"/admin_users", AdminUsers),
    (r"/(set|clear)_admin_role/([^/]+)/([^/]+)", UpdateAdminRole),
    (r"/create_user", CreateUser),
    (r"/stop_server", StopServer, {"answer_checking": answer_checking}),
    (r"/teams", ShowTeams),
    (r"/puzzles", ShowPuzzles),
    (r"/admin.js", AdminJS, {"compiled_admin_js": compiled_admin_js}),
    (r"/admin.css", AdminCSS, {"admin_css": admin_css}),
    ]
  if debug:
    handlers.append((r"/admin-debug.js", AdminDebugJS))
  return handlers





