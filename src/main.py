#!/usr/bin/python3

import argparse
import asyncio
import concurrent
import json
import os
import resource
import signal
import sys
import time

import tornado.ioloop
import tornado.httpserver
import tornado.netutil
import tornado.template
import tornado.web

import admin
import debug
import event
import game
import login
from state import save_state
import wait_proxy
import util


assert sys.hexversion >= 0x03070300, "Need Python 3.7.3 or newer!"
assert tornado.version_info >= (5, 1, 1, 0), "Need Tornado 5.1.1 or newer!"


def make_app(options, static_dir, **kwargs):
  handlers = []
  handlers.extend(login.GetHandlers())
  handlers.extend(admin.GetHandlers())
  handlers.extend(event.GetHandlers())
  handlers.extend(wait_proxy.GetHandlers())
  if options.debug:
    handlers.extend(debug.GetHandlers())

  return tornado.web.Application(
    handlers,
    options=options,
    static_dir=static_dir,
    cookie_secret=options.cookie_secret,
    template_path=options.template_path,
    debug=options.debug,
    **kwargs)


async def main_server(options):
  if options.debug:
    game.Submission.PER_ANSWER_DELAY = 20

  print("Load map config...")
  with open(os.path.join(options.event_dir, "map_config.json")) as f:
    cfg = json.load(f)

  static_content = {}
  for key, (url, path) in cfg["static"].items():
    if options.debug:
      static_content[key] = "/debug/" + path
    else:
      static_content[key] = url

  for shortname, d in cfg["maps"].items():
    game.Land(shortname, d, options.event_dir)
  util.TeamPageHandler.set_static_content(static_content)
  util.AdminPageHandler.set_static_content(static_content)
  game.Land.resolve_lands()
  game.Achievement.define_achievements(static_content)
  if options.debug:
    debug.DebugPathHandler.set_static_content(static_content)
  login.Login.set_static_content(static_content)
  options.static_content = static_content

  save_state.set_classes(AdminUser=login.AdminUser,
                         Team=game.Team,
                         Global=game.Global,
                         Puzzle=game.Puzzle)

  with open(os.path.join(options.event_dir, "admins.json")) as f:
    admins = json.load(f)
    for username, d in admins.items():
      login.AdminUser(username, d["pwhash"], d["name"], d.get("roles", ()))

  with open(os.path.join(options.event_dir, "teams.json")) as f:
    teams = json.load(f)
    for username, d in teams.items():
      game.Team(username, d)


  save_state.open(os.path.join(options.event_dir, "state.log"))
  save_state.replay(advance_time=game.Submission.process_submit_queue)

  wait_proxy.Server.init_proxies(options.wait_proxies)

  if not game.Global.STATE: game.Global()

  if options.start_event:
    game.Global.STATE.start_event(False)

  for team in game.Team.BY_USERNAME.values():
    team.discard_messages()
  game.Global.STATE.hint_queue.build()

  app = make_app(options, cfg["static"], autoreload=False)

  server = tornado.httpserver.HTTPServer(app)
  sockets = [tornado.netutil.bind_unix_socket(options.socket_path, mode=0o666, backlog=3072)]
  sockets.extend(tornado.netutil.bind_sockets(options.wait_proxy_port, address="localhost"))
  server.add_sockets(sockets)

  loop = asyncio.get_event_loop()
  loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=4))
  loop.create_task(game.Submission.realtime_process_submit_queue())
  loop.create_task(game.Puzzle.realtime_open_hints())
  loop.create_task(game.Global.STATE.flawless_check())

  print("Serving...")
  async with game.Global.STATE.stop_cv:
    while not game.Global.STATE.stopping:
      await game.Global.STATE.stop_cv.wait()


def wait_server(n, options):
  try:
    asyncio.run(wait_proxy.Client(n, options).start(), debug=options.debug)
  except KeyboardInterrupt:
    pass


def main():
  parser = argparse.ArgumentParser(
    description="Main server for MIT Mystery Hunt.")
  parser.add_argument("-t", "--template_path",
                      help="Path to HTML templates.")
  parser.add_argument("-c", "--cookie_secret",
                      default="snellen2020",
                      help="Secret used to create session cookies.")
  parser.add_argument("-e", "--event_dir",
                      help="Path to event content.")
  parser.add_argument("-s", "--socket_path",
                      default="/tmp/snellen",
                      help="Socket for proxy to reach this server.")

  # debugging flags
  parser.add_argument("--start_event", action="store_true",
                      help="Immediately start event.")
  parser.add_argument("--debug", action="store_true",
                      help="Serve debug javascript.")
  parser.add_argument("--open_all", action="store_true",
                      help="Open all puzzles immediately.")
  parser.add_argument("--placeholders", action="store_true",
                      help="Replace all puzzles with placeholders.")
  parser.add_argument("--default_credentials",
                      help="Fill username/password field automatically.")
  parser.add_argument("--start_delay",
                      type=int, default=30,
                      help=("Seconds to count down before starting event."))

  # wait proxy configuration
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

  game.OPTIONS = options

  soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
  try:
    resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
    print(f"Raised limit to {hard} file descriptors.")
  except ValueError:
    print("Warning: unable to increase file descriptor limit!")

  original_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
  proxy_pids = []
  for i in range(options.wait_proxies):
    pid = os.fork()
    if pid == 0:
      wait_server(i, options)
      return
    proxy_pids.append(pid)
  signal.signal(signal.SIGINT, original_handler)

  try:
    asyncio.run(main_server(options), debug=options.debug)
  except KeyboardInterrupt:
    pass

  save_state.close()

  for pid in proxy_pids:
    os.kill(pid, signal.SIGKILL)



if __name__ == "__main__":
  main()

