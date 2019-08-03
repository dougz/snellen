#!/usr/bin/python3

import argparse
import asyncio
import concurrent
import json
import os
import resource
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
import wait_proxy
import util


assert sys.hexversion >= 0x03070300, "Need Python 3.7.3 or newer!"
assert tornado.version_info >= (5, 1, 1, 0), "Need Tornado 5.1.1 or newer!"


def make_app(options, **kwargs):
  debug = kwargs.get("debug")
  return tornado.web.Application(
    login.GetHandlers() +
    admin.GetHandlers(options.debug) +
    event.GetHandlers(options.debug) +
    wait_proxy.GetHandlers(),
    options=options,
    cookie_secret=options.cookie_secret,
    template_path=options.template_path,
    debug=options.debug,
    **kwargs)


def main_server(options):
  print("Load map config...")
  with open(os.path.join(options.event_dir, "map_config.json")) as f:
    cfg = json.load(f)
    for shortname, d in cfg["maps"].items():
      game.Land(shortname, d, options.event_dir)
    util.TeamPageHandler.set_static_content(cfg["static"])
    util.AdminPageHandler.set_static_content(cfg["static"])
  game.Land.resolve_lands()
  game.Achievement.define_achievements(cfg["static"])

  save_state.set_classes(AdminUser=login.AdminUser,
                         Team=game.Team,
                         Global=game.Global)
  save_state.open(os.path.join(options.event_dir, "state.log"))
  save_state.replay(advance_time=game.Submission.process_submit_queue)

  wait_proxy.Server.init_proxies(options.wait_proxies)

  if not game.Global.STATE: game.Global()

  print("Adding new teams...")
  with open(os.path.join(options.event_dir, "teams.py")) as f:
    exec(f.read(), {"add_team": game.Team.add_team})

  start_map = game.Land.BY_SHORTNAME["inner_only"]
  for team in game.Team.BY_USERNAME.values():
    team.open_lands[start_map] = 0
    team.discard_messages()

  if options.start_event:
    game.Global.STATE.start_event()

  if options.root_password:
    print("Enabling root user...")
    login.AdminUser.enable_root(login.make_hash(options.root_password))

  app = make_app(options, autoreload=False)

  server = tornado.httpserver.HTTPServer(app)
  sockets = [tornado.netutil.bind_unix_socket(options.socket_path, mode=0o666, backlog=3072)]
  sockets.extend(tornado.netutil.bind_sockets(options.wait_proxy_port, address="localhost"))
  server.add_sockets(sockets)

  loop = asyncio.get_event_loop()
  loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=4))
  loop.create_task(game.Submission.realtime_process_submit_queue())

  try:
    print("Serving...")
    tornado.ioloop.IOLoop.current().start()
  except KeyboardInterrupt:
    pass

  save_state.close()


def wait_server(n, options):
  wait_proxy.Client(n, options).start()


def main():
  parser = argparse.ArgumentParser(
    description="Main server for MIT Mystery Hunt.")
  parser.add_argument("-t", "--template_path",
                      help="Path to HTML templates.")
  parser.add_argument("-c", "--cookie_secret",
                      default="snellen2020",
                      help="Secret used to create session cookies.")
  parser.add_argument("-r", "--root_password",
                      help="Password for root admin user.")
  parser.add_argument("-e", "--event_dir",
                      help="Path to event content.")
  parser.add_argument("-s", "--socket_path",
                      default="/tmp/snellen",
                      help="Socket for proxy to reach this server.")
  parser.add_argument("--start_event", action="store_true",
                      help="Start event for all teams.")
  parser.add_argument("--debug", action="store_true",
                      help="Serve debug javascript.")
  parser.add_argument("--default_credentials",
                      help="Fill username/password field automatically.")
  parser.add_argument("-w", "--wait_proxies",
                      type=int, default=2,
                      help="Number of wait proxy servers to start.")
  parser.add_argument("--wait_proxy_port",
                      type=int, default=2020,
                      help=("Port for communicating between wait proxy "
                            "and main server"))

  options = parser.parse_args()

  assert options.template_path is not None, "Must specify --template_path."
  assert options.event_dir is not None, "Must specify --event_dir."

  soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
  resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
  print(f"Raised limit to {hard} file descriptors.")

  for i in range(options.wait_proxies):
    if os.fork() == 0:
      wait_server(i, options)
      return

  main_server(options)



if __name__ == "__main__":
  main()

