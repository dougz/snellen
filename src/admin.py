import tornado.web
import login

class AdminHome(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.render("admin.html", user=self.user)

