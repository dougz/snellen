import tornado.web
import login

class AdminHome(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.render("admin.html", user=self.user)


class AdminUsers(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.render("admin_users.html")

class CreateUser(tornado.web.RequestHandler):
  def initialize(self, admin_user_db=None):
    self.admin_user_db = admin_user_db

  @login.required("create_users")
  def post(self):
    username = self.get_argument("username")
    fullname = self.get_argument("fullname")
    password = self.get_argument("password")
    self.admin_user_db.add_user(
      username, self.admin_user_db.make_hash(password), fullname, ())

    self.redirect("/admin_users")


class StopServer(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    loop = tornado.ioloop.IOLoop.current()
    loop.call_later(0.5, loop.stop)


def GetHandlers(admin_user_db):
  return [
    (r"/admin", AdminHome),
    (r"/admin_users", AdminUsers),
    (r"/create_user", CreateUser, dict(admin_user_db=admin_user_db)),
    (r"/stop_server", StopServer),
    ]





