import asyncio
import collections
import http.client
import json
import random
import time
import tornado.web
import tornado.httpclient
import tornado.httpserver
import tornado.netutil

class ProxyTeam:
  BY_TEAM = {}

  @classmethod
  def get_team(cls, team):
    t = cls.BY_TEAM.get(team)
    if t: return t
    t = ProxyTeam(team)
    cls.BY_TEAM[team] = t
    return t

  @classmethod
  def all_teams(cls):
    return cls.BY_TEAM.values()

  def __init__(self, team):
    self.team = team
    self.cv = asyncio.Condition()
    self.waiters = set()
    self.serial = 1
    self.sticky_messages = None

  def __str__(self):
    return f"<ProxyTeam {self.team}>"

  async def send_messages(self, msgs, sticky=None):
    if not msgs: return
    if not self.waiters: return
    async with self.cv:
      msgs = [(self.serial+i, json.dumps(m)) for (i, m) in enumerate(msgs)]
      self.serial += len(msgs)

      if sticky:
        self.sticky_messages = msgs[-sticky:]

      for w in self.waiters:
        w.q.extend(msgs)
      self.cv.notify_all()

  def add_waiter(self, waiter):
    self.waiters.add(waiter)
    return self.sticky_messages


class ScrumApp:
  def __init__(self, options, handlers):
    self.options = options

    self.session_cache = {}

    tornado.httpclient.AsyncHTTPClient.configure(
      "tornado.curl_httpclient.CurlAsyncHTTPClient", max_clients=10000)
    self.client = tornado.httpclient.AsyncHTTPClient()

    if hasattr(options, "wait_url"):
      r = f"/{options.wait_url}/(\\d+)/(\\d+)"
      handlers = [(r, WaitHandler, {"scrum_app": self})] + handlers
    app = tornado.web.Application(
      handlers,
      cookie_secret=options.cookie_secret,
      scrum_app=self)

    self.server = tornado.httpserver.HTTPServer(app)
    socket = tornado.netutil.bind_unix_socket(options.socket_path, mode=0o666, backlog=3072)
    self.server.add_socket(socket)

  def start(self):
    ioloop = tornado.ioloop.IOLoop.current()
    ioloop.spawn_callback(self.purge)
    #ioloop.spawn_callback(self.print_stats)
    try:
      print(f"scrum app listening")
      ioloop.start()
    except KeyboardInterrupt:
      pass

  def add_callback(self, callback):
    ioloop = tornado.ioloop.IOLoop.current()
    ioloop.spawn_callback(callback)

  async def print_stats(self):
    while True:
      out = {}
      for t in ProxyTeam.all_teams():
        out[t.team] = len(t.waiters)
      print(f"proxy #{self.wpid}: {out}")

      await asyncio.sleep(2.5)

  async def purge(self):
    while True:
      await asyncio.sleep(Waiter.WAITER_TIMEOUT)
      now = time.time()
      for t in ProxyTeam.all_teams():
        to_delete = set()
        for w in t.waiters:
          if w.purgeable(now):
            to_delete.add(w)
        if to_delete:
          t.waiters -= to_delete

  async def check_session(self, key):
    key = key.decode("ascii")
    v = self.session_cache.get(key)
    if v:
      team, expiration, size = v
      if team and expiration > time.time(): return team, size

    req = tornado.httpclient.HTTPRequest(
      f"http://localhost:{self.options.main_server_port}/checksession/{key}",
      connect_timeout=5.0,
      request_timeout=10.0)
    try:
      response = await self.client.fetch(req)
      reply = response.body.decode("utf-8")
      if reply:
        d = json.loads(reply)
        team = d["group"]
        expiration = d["expire"] - 15
        size = d["size"]
        self.session_cache[key] = (team, expiration, size)
        return team, size
    except tornado.httpclient.HTTPClientError as e:
      pass

    raise tornado.web.HTTPError(http.client.UNAUTHORIZED)

  async def check_cookie(self, req):
    key = req.get_secure_cookie("SESSION") # login.Session.COOKIE_NAME
    if not key:
      raise tornado.web.HTTPError(http.client.UNAUTHORIZED)
    team, size = await self.check_session(key)
    team = ProxyTeam.get_team(team)
    team.size = size
    return team, key

  async def on_wait(self, team, session, wid):
    pass


class Waiter:
  # If we replied to a waiter more than this long ago and haven't
  # received a new request, the client is assumed to be dead.
  WAITER_TIMEOUT = 30  # seconds

  BY_WID = {}

  @classmethod
  def get_waiter(cls, wid, team):
    if wid not in cls.BY_WID:
      cls.BY_WID[wid] = Waiter(wid, team)
    return cls.BY_WID[wid]

  def __init__(self, wid, team):
    self.team = team
    initial_msgs = team.add_waiter(self)
    self.last_acked = 0
    self.wid = wid
    self.q = collections.deque()
    if initial_msgs: self.q.extend(initial_msgs)

    self.wait_in_progress = False
    self.last_return = time.time()

  def __str__(self):
    return f"<Waiter {self.wid} {self.team.team}>"

  def purgeable(self, now):
    return (not self.wait_in_progress and
            now - self.last_return > self.WAITER_TIMEOUT)

  async def wait(self, received_serial, timeout):
    self.wait_in_progress = True
    # Discard any messages that have been acked.
    q = self.q
    while q and q[0][0] <= received_serial:
      q.popleft()

    allow_empty = False
    while True:
      if q or allow_empty:
        self.wait_in_progress = False
        self.last_return = time.time()
        return q
      allow_empty = True
      async with self.team.cv:
        try:
          await asyncio.wait_for(self.team.cv.wait(), timeout)
        except asyncio.TimeoutError:
          pass


class WaitHandler(tornado.web.RequestHandler):
  DEFAULT_WAIT_TIMEOUT = 600
  DEFAULT_WAIT_SMEAR = 60

  def initialize(self, scrum_app):
    self.scrum_app = scrum_app

  async def get(self, wid, received_serial):
    team, session = await self.scrum_app.check_cookie(self)

    wid = int(wid)
    received_serial = int(received_serial)

    waiter = Waiter.get_waiter(wid, team)

    wait_timeout = getattr(self.scrum_app, "WAIT_TIMEOUT", self.DEFAULT_WAIT_TIMEOUT)
    wait_smear = getattr(self.scrum_app, "WAIT_SMEAR", self.DEFAULT_WAIT_SMEAR)

    # Choose the timeout for the first wait evenly across the whole
    # interval, to avoid the thundering herd problem.
    if received_serial == 0:
      timeout = random.random() * (wait_timeout + wait_smear)
    else:
      timeout = wait_timeout + random.random() * wait_smear

    await self.scrum_app.on_wait(team, session, wid)

    msgs = await waiter.wait(received_serial, timeout)

    if False:
      if msgs:
        print(f"msgs {msgs[0][0]}..{msgs[-1][0]} to {team} wid {wid}")
      else:
        print(f"empty response to {team} wid {wid}")

    self.set_header("Content-Type", "application/json")
    self.set_header("Cache-Control", "no-store")
    self.write(b"[")
    for i, (ser, obj) in enumerate(msgs):
      if i > 0: self.write(b",")
      self.write(f"[{ser},{obj}]".encode("utf-8"))
    self.write(b"]")
