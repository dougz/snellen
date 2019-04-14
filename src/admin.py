import http.client
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
  @login.required("create_users")
  def post(self):
    username = self.get_argument("username")
    fullname = self.get_argument("fullname")
    password = self.get_argument("password")

    if login.AdminUser.get_by_username(username) is not None:
      # error
      raise tornado.web.HTTPError(http.client.BAD_REQUEST,
                                  "User already exists")


    login.AdminUser(username, login.AdminUser.make_hash(password), fullname, ())
    self.redirect("/admin_users")


class StopServer(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    loop = tornado.ioloop.IOLoop.current()
    loop.call_later(0.5, loop.stop)


def GetHandlers():
  return [
    (r"/admin", AdminHome),
    (r"/admin_users", AdminUsers),
    (r"/create_user", CreateUser),
    (r"/stop_server", StopServer),
    ]





