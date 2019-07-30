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

import login

# Reply to wait proxies at least this often, even if we have no
# messages to send.
PROXY_WAIT_TIMEOUT = 30 # seconds


##
## server side
##


class Server:
  PROXIES = []
  NEXT_WID = 1

  def __init__(self, wpid):
    self.cv = asyncio.Condition()
    self.q = []

  @classmethod
  def init_proxies(cls, count):
    for i in range(count):
      cls.PROXIES.append(Server(i))

  @classmethod
  async def send_message(cls, team, serial, strs):
    if not isinstance(team, str):
      team = team.username
    x = (team,  tuple((serial+i, s) for (i, s) in enumerate(strs)))
    for p in cls.PROXIES:
      async with p.cv:
        p.q.append(x)
        p.cv.notify_all()

  @classmethod
  def new_waiter_id(cls):
    wid, cls.NEXT_WID = cls.NEXT_WID, cls.NEXT_WID+1
    return wid


class ProxyWaitHandler(tornado.web.RequestHandler):
  async def get(self, wpid):
    wpid = int(wpid)
    proxy = Server.PROXIES[wpid]

    async with proxy.cv:
      try:
        await asyncio.wait_for(proxy.cv.wait(), PROXY_WAIT_TIMEOUT)
      except asyncio.TimeoutError:
        pass

      content, proxy.q = proxy.q, []

    content = json.dumps(content)
    self.set_header("Content-Type", "application/json")
    self.set_header("Cache-Control", "no-store")
    self.write(content)


class CheckSessionHandler(tornado.web.RequestHandler):
  def get(self, key):
    key = key.encode("ascii")
    session = login.Session.from_key(key)
    self.set_header("Content-Type", "text/plain")
    if session is not None and hasattr(session, "team"):
      self.write(session.team.username)


def GetHandlers():
  return [
    (r"/proxywait/(\d+)", ProxyWaitHandler),
    (r"/checksession/(\S+)", CheckSessionHandler),
  ]


##
## client side
##


class Client:
  def __init__(self, wpid, options):
    self.wpid = wpid
    self.options = options

    self.session_cache = {}

    tornado.httpclient.AsyncHTTPClient.configure(
      "tornado.curl_httpclient.CurlAsyncHTTPClient", max_clients=10000)
    self.client = tornado.httpclient.AsyncHTTPClient()

    app = tornado.web.Application(
      [(r"/wait/(\d+)/(\d+)", WaitHandler, {"proxy_client": self})],
      cookie_secret=options.cookie_secret)

    self.server = tornado.httpserver.HTTPServer(app)
    socket = tornado.netutil.bind_unix_socket(f"{options.socket_path}_p{wpid}", mode=0o666, backlog=3072)
    self.server.add_socket(socket)

  def start(self):
    ioloop = tornado.ioloop.IOLoop.current()
    ioloop.spawn_callback(self.fetch)
    ioloop.spawn_callback(self.purge)
    #ioloop.spawn_callback(self.print_stats)
    try:
      print(f"proxy waiter #{self.wpid} listening")
      ioloop.start()
    except KeyboardInterrupt:
      pass

  async def print_stats(self):
    while True:
      out = {}
      for t in ProxyTeam.all_teams():
        out[t.team] = len(t.waiters)
      print(f"proxy #{self.wpid}: {out}")

      await asyncio.sleep(2.5)

  async def fetch(self):
    # Give main server time to start up.
    await asyncio.sleep(2.0)

    while True:
      msgs = await self.get_messages()
      for team, items in msgs:
        team = ProxyTeam.get_team(team)
        await team.send_messages(items)

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

  async def get_messages(self):
    while True:
      req = tornado.httpclient.HTTPRequest(
        f"http://localhost/proxywait/{self.wpid}",
        connect_timeout=5.0,
        request_timeout=PROXY_WAIT_TIMEOUT+10)
      try:
        response = await self.client.fetch(req)
        return json.loads(response.body)
      except tornado.httpclient.HTTPClientError as e:
        if e.code == 502:
          print(f"proxy {self.wpid} got 502; retrying")
          await asyncio.sleep(1.0)
        else:
          raise

  async def check_session(self, key):
    key = key.decode("ascii")
    team = self.session_cache.get(key)
    if team: return team

    req = tornado.httpclient.HTTPRequest(
      f"http://localhost/checksession/{key}",
      connect_timeout=5.0,
      request_timeout=10.0)
    try:
      response = await self.client.fetch(req)
      team = response.body.decode("ascii")
      if team:
        self.session_cache[key] = team
        return team
    except tornado.httpclient.HTTPClientError as e:
      pass

    raise tornado.web.HTTPError(http.client.UNAUTHORIZED)


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

  def __str__(self):
    return f"<ProxyTeam {self.team}>"

  async def send_messages(self, msgs):
    if not msgs: return
    if not self.waiters: return
    async with self.cv:
      for w in self.waiters:
        w.q.extend(msgs)
      self.cv.notify_all()

  def add_waiter(self, waiter):
    self.waiters.add(waiter)


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
    team.add_waiter(self)
    self.last_acked = 0
    self.wid = wid
    self.q = collections.deque()

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
  WAIT_TIMEOUT = 600
  WAIT_SMEAR = 60

  def initialize(self, proxy_client):
    self.proxy_client = proxy_client

  async def get(self, wid, received_serial):
    key = self.get_secure_cookie(login.Session.COOKIE_NAME)
    team = await self.proxy_client.check_session(key)
    team = ProxyTeam.get_team(team)

    wid = int(wid)
    received_serial = int(received_serial)

    waiter = Waiter.get_waiter(wid, team)

    # Choose the timeout for the first wait evenly across the whole
    # interval, to avoid the thundering herd problem.
    if received_serial == 0:
      timeout = random.random() * (self.WAIT_TIMEOUT + self.WAIT_SMEAR)
    else:
      timeout = self.WAIT_TIMEOUT + random.random() * self.WAIT_SMEAR

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
