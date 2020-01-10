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


def dump_info(fn):
  plist = {}
  for p in game.Puzzle.BY_SHORTNAME.values():
    plist[p.shortname] = [p.meta, list(p.answers)]

  d = {"puzzles": plist}
  with open(fn, "w") as f:
    json.dump(d, f, indent=True)

async def main_server(options):
  if options.debug:
    game.Submission.PER_ANSWER_DELAY = 20

  game.Global.set_submit_log_filename(
    os.path.join(options.event_dir, "submit_log.csv"))

  with open(os.path.join(os.getenv("HUNT2020_BASE"), "snellen/static/emoji.json")) as f:
    emoji = json.load(f)
    allowed = set()
    for _, g in emoji:
      for e in g:
        for k in e[1]:
          allowed.add(k)
    allowed = frozenset(allowed)
    game.Puzzle.EXTRA_ALLOWED_CHARS = allowed

  print("Load map config...")
  with open(os.path.join(options.event_dir, "map_config.json")) as f:
    cfg = json.load(f)

  c = cfg["constants"]
  game.CONSTANTS = c
  admin.CONSTANTS = c

  game.VIDEOS = cfg["videos"]
  event.VIDEOS = cfg["videos"]

  static_content = {}
  for key, v in cfg["static"].items():
    if isinstance(v, str):
      static_content[key] = v
    else:
      url, path = v
      if options.debug:
        static_content[key] = "/debug/" + path
      else:
        static_content[key] = url
  options.static_content = static_content

  for shortname, d in cfg["maps"].items():
    game.Land(shortname, d, options.event_dir)
  util.TeamPageHandler.set_static_content(static_content)
  util.AdminPageHandler.set_static_content(static_content)
  game.Land.resolve_lands()
  for shortname, d in cfg["events"].items():
    game.Event(shortname, d)
  if "workshop" in cfg:
    game.Workshop.build(cfg["workshop"])
  if "runaround" in cfg:
    game.Runaround.build(cfg["runaround"])
  if options.debug:
    debug.DebugPathHandler.set_static_content(static_content)
  login.Login.set_static_content(static_content)

  save_state.set_classes(AdminUser=login.AdminUser,
                         Team=game.Team,
                         Global=game.Global,
                         Puzzle=game.Puzzle)

  with open(os.path.join(options.event_dir, "teams.json")) as f:
    teams = json.load(f)
    for username, d in teams.items():
      game.Team(username, d)

  game.Event.post_init()
  game.Workshop.post_init()
  game.Runaround.post_init()

  for team in game.Team.all_teams():
    team.post_init()

  if options.dump_info:
    dump_info(options.dump_info);

  save_state.open(os.path.join(options.event_dir, "state.log"))
  replay_count = save_state.replay(advance_time=game.Submission.process_submit_queue)

  if not login.AdminUser.BY_USERNAME:
    with open(os.path.join(options.event_dir, "admins.json")) as f:
      admins = json.load(f)
      for username, d in admins.items():
        login.AdminUser(username, d["pwhash"], d["name"], d.get("roles", ()))

  wait_proxy.Server.init_proxies(options.wait_proxies)

  admin.PuzzleJsonHandler.build()
  admin.TeamJsonHandler.build()

  if not game.Global.STATE: game.Global()

  await game.Global.STATE.task_queue.purge(None)
  # arrange to purge any tasks marked complete in the last 20 seconds
  # of replay time.
  asyncio.create_task(game.Global.STATE.task_queue.purge(20))

  if options.start_event and not game.Global.STATE.event_start_time:
    game.Global.STATE.start_event(False)

  for team in game.Team.BY_USERNAME.values():
    team.discard_messages()
    team.message_serial = (replay_count * 1000000) + 1
  login.AdminUser.message_serial = (replay_count * 1000000) + 1

  login.Session.set_session_log(
    os.path.join(options.event_dir, "session.log"))

  game.Global.STATE.task_queue.build()

  game.Global.STATE.maybe_preload()

  app = make_app(options, cfg["static"], autoreload=False)

  server = tornado.httpserver.HTTPServer(app)
  socket = tornado.netutil.bind_sockets(options.base_port, address="localhost")
  server.add_sockets(socket)

  loop = asyncio.get_event_loop()
  loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=4))
  loop.create_task(game.Submission.realtime_process_submit_queue())
  loop.create_task(game.Puzzle.realtime_open_hints())
  loop.create_task(game.Team.realtime_expire_fastpasses())
  loop.create_task(game.Team.realtime_trim_last_hour())

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

  # debugging flags
  parser.add_argument("--start_event", action="store_true",
                      help="Immediately start event.")
  parser.add_argument("--debug", action="store_true",
                      help="Serve debug javascript.")
  parser.add_argument("--placeholders", action="store_true",
                      help="Replace all puzzles with placeholders.")
  parser.add_argument("--default_credentials",
                      help="Fill username/password field automatically.")
  parser.add_argument("--start_delay",
                      type=int, default=None,
                      help=("Seconds to count down before starting event."))
  parser.add_argument("--dump_info", default=None,
                      help=("Dump all puzzle info to this file"))

  # wait proxy configuration
  parser.add_argument("-w", "--wait_proxies",
                      type=int, default=2,
                      help="Number of wait proxy servers to start.")
  parser.add_argument("--base_port",
                      type=int, default=2020,
                      help=("Port for communicating between wait proxy "
                            "and main server"))

  options = parser.parse_args()

  assert options.template_path is not None, "Must specify --template_path."
  assert options.event_dir is not None, "Must specify --event_dir."

  if options.start_delay is None:
    if options.debug:
      options.start_delay = 30
    else:
      options.start_delay = 3600

  game.OPTIONS = options
  event.OPTIONS = options
  admin.OPTIONS = options

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

