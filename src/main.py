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



class TestHandler(tornado.web.RequestHandler):
  def get(self):
    self.set_header("Content-Type", "text/html")
    self.write("<html><body>hello, world</body></html>")


def make_app(**kwargs):
  return tornado.web.Application([
    (r"/", event.Home),
    (r"/admin", admin.AdminHome),
    (r"/testz", TestHandler),
  ] + login.HANDLERS, **kwargs)


def main():
  template_path = None
  cookie_secret = "1234"

  opts, args = getopt.getopt(sys.argv[1:],
                             "t:c:",
                             ["template_path=",
                              "cookie_secret="])
  for o, a in opts:
    if o in ("-t", "--template_path"):
      template_path = a
    elif o in ("-c", "--cookie_secret"):
      cookie_secret = a
    else:
      assert False, f"unhandled option {o}"

  assert template_path is not None, "Must specify --template_path."

  app = make_app(template_path=template_path,
                 cookie_secret=cookie_secret)

  server = tornado.httpserver.HTTPServer(app)
  socket = tornado.netutil.bind_unix_socket("/tmp/snellen", mode=0o666)
  server.add_socket(socket)
  print("Serving...")
  tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
  main()

