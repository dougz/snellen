import http.client
import tornado.web

import game
import login

class EventHome(tornado.web.RequestHandler):
  @login.required("team")
  def get(self):
    self.render("home.html", team=self.team)

def GetHandlers():
  return [
    (r"/", EventHome),
    ]
