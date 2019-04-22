import http.client
import tornado.web

import game
import login

class AdminHome(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.render("admin.html", user=self.user)


class AdminUsers(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_users.html")


class ShowTeams(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.render("teams.html", teams=game.Team.BY_USERNAME)


class ShowPuzzles(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.render("puzzles.html", puzzles=game.Puzzle.BY_SHORTNAME)


class CreateUser(tornado.web.RequestHandler):
  @login.required("create_users")
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

  @login.required("admin")
  def get(self):
    self.answer_checking.stop()
    loop = tornado.ioloop.IOLoop.current()
    loop.call_later(0.5, loop.stop)


def GetHandlers(answer_checking):
  return [
    (r"/admin", AdminHome),
    (r"/admin_users", AdminUsers),
    (r"/create_user", CreateUser),
    (r"/stop_server", StopServer, {"answer_checking": answer_checking}),
    (r"/teams", ShowTeams),
    (r"/puzzles", ShowPuzzles),
    ]





