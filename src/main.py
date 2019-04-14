#!/usr/bin/python3

import getopt
import sys

import tornado.ioloop
import tornado.httpserver
import tornado.netutil
import tornado.template
import tornado.web


import admin
import event
import login
from state import save_state


class TestHandler(tornado.web.RequestHandler):
  def get(self):
    self.set_header("Content-Type", "text/html")
    self.write("<html><body>hello, world</body></html>")


def make_app(**kwargs):
  return tornado.web.Application([
    (r"/", event.Home),
    (r"/testz", TestHandler),
  ] + login.GetHandlers() + admin.GetHandlers(), **kwargs)


def main():
  template_path = None
  cookie_secret = "1234"
  root_password = None

  opts, args = getopt.getopt(sys.argv[1:],
                             "t:c:r:",
                             ["template_path=",
                              "cookie_secret=",
                              "root_password="])
  for o, a in opts:
    if o in ("-t", "--template_path"):
      template_path = a
    elif o in ("-c", "--cookie_secret"):
      cookie_secret = a
    elif o in ("-r", "--root_password"):
      root_password = a
    else:
      assert False, f"unhandled option {o}"

  assert template_path is not None, "Must specify --template_path."

  save_state.set_classes(AdminUser=login.AdminUser)
  save_state.open("state.log")
  save_state.replay()

  if root_password:
    print("Enabling root user...")
    login.AdminUser.enable_root(login.AdminUser.make_hash(root_password))

  app = make_app(template_path=template_path,
                 cookie_secret=cookie_secret)

  server = tornado.httpserver.HTTPServer(app)
  socket = tornado.netutil.bind_unix_socket("/tmp/snellen", mode=0o666)
  server.add_socket(socket)
  print("Serving...")
  tornado.ioloop.IOLoop.instance().start()

  save_state.close()

if __name__ == "__main__":
  main()

