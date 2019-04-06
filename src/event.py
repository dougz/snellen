import tornado.web

class Home(tornado.web.RequestHandler):
  def get(self):
    self.render("home.html")

