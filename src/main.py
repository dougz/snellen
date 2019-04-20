#!/usr/bin/python3

import getopt
import os
import sys

import tornado.ioloop
import tornado.httpserver
import tornado.netutil
import tornado.template
import tornado.web


import admin
import event
import game
import login
from state import save_state


def make_app(event_dir, **kwargs):
  with open("bin/client-compiled.js", "rb") as f:
    compiled_js = f.read()

  return tornado.web.Application(
    login.GetHandlers() +
    admin.GetHandlers() +
    event.GetHandlers(event_dir, kwargs.get("debug"), compiled_js),
    **kwargs)


def main():
  template_path = None
  cookie_secret = "1234"
  root_password = None
  event_dir = None
  debug = False
  default_username = None
  default_password = None

  opts, args = getopt.getopt(sys.argv[1:],
                             "c:e:r:t:",
                             ["cookie_secret=",
                              "debug",
                              "default_credentials=",
                              "event_dir=",
                              "root_password=",
                              "template_path=",
                             ])
  for o, a in opts:
    if o in ("-t", "--template_path"):
      template_path = a
    elif o in ("-c", "--cookie_secret"):
      cookie_secret = a
    elif o in ("-r", "--root_password"):
      root_password = a
    elif o in ("-e", "--event_dir"):
      event_dir = a
    elif o == "--debug":
      debug = True
    elif o == "--default_credentials":
      default_username, default_password = a.split(":", 1)
    else:
      assert False, f"unhandled option {o}"

  assert template_path is not None, "Must specify --template_path."
  assert event_dir is not None, "Must specify --event_dir."

  save_state.set_classes(AdminUser=login.AdminUser,
                         Team=game.Team)
  save_state.open(os.path.join(event_dir, "state.log"))
  save_state.replay()

  print("Adding teams...")
  with open(os.path.join(event_dir, "teams.py")) as f:
    exec(f.read(), {"add_team": game.Team.add_team})

  print("Adding puzzles...")
  with open(os.path.join(event_dir, "puzzles.py")) as f:
    def add_puzzle(nickname):
      game.Puzzle(os.path.join(event_dir, "puzzles", nickname))
    exec(f.read(), {"add_puzzle": add_puzzle})

  if root_password:
    print("Enabling root user...")
    login.AdminUser.enable_root(login.make_hash(root_password))

  app = make_app(event_dir,
                 template_path=template_path,
                 cookie_secret=cookie_secret,
                 debug=debug,
                 default_username=default_username,
                 default_password=default_password)

  server = tornado.httpserver.HTTPServer(app)
  socket = tornado.netutil.bind_unix_socket("/tmp/snellen", mode=0o666)
  server.add_socket(socket)
  print("Serving...")
  tornado.ioloop.IOLoop.instance().start()

  save_state.close()

if __name__ == "__main__":
  main()

