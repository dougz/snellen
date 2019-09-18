import asyncio
import collections
import concurrent
import http.client
import json
import random
import sys
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
    self.wpid = wpid
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

  @classmethod
  async def exit(cls):
    await cls.send_message("__EXIT", 0, [""])
    await asyncio.sleep(1.0)


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
    if session is not None:
      session.expires = int(time.time()) + session.SESSION_TIMEOUT
      group = None
      if hasattr(session, "team") and session.team:
        group = session.team.username
      elif hasattr(session, "user") and session.user:
        group = "__ADMIN"
      if group:
        self.write(f"{group} {int(session.expires)}")

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

  async def start(self):
    #tornado.httpclient.AsyncHTTPClient.configure(
    #"tornado.curl_httpclient.CurlAsyncHTTPClient", max_clients=10000)
    self.client = tornado.httpclient.AsyncHTTPClient()

    app = tornado.web.Application(
      [(r"/wait/(\d+)/(\d+)", WaitHandler, {"proxy_client": self})],
      cookie_secret=self.options.cookie_secret)

    self.server = tornado.httpserver.HTTPServer(app)
    socket = tornado.netutil.bind_unix_socket(f"{self.options.socket_path}_p{self.wpid}", mode=0o666, backlog=3072)
    self.server.add_socket(socket)

    print(f"proxy waiter #{self.wpid} listening")
    await self.fetch()

  async def fetch(self):
    # Give main server time to start up.
    await asyncio.sleep(2.0)

    while True:
      msgs = await self.get_messages()
      for team, items in msgs:
        if team == "__EXIT":
          print(f"proxy waiter #{self.wpid} exiting")
          return
        team = ProxyTeam.get_team(team)
        await team.send_messages(items)

  async def get_messages(self):
    while True:
      req = tornado.httpclient.HTTPRequest(
        f"http://localhost:{self.options.wait_proxy_port}/proxywait/{self.wpid}",
        connect_timeout=5.0,
        request_timeout=PROXY_WAIT_TIMEOUT+10)
      try:
        response = await self.client.fetch(req)
        return json.loads(response.body)
      except tornado.httpclient.HTTPClientError as e:
        print(f"proxy {self.wpid} got {e.code}; retrying")
        await asyncio.sleep(1.0)
      except concurrent.futures.CancelledError:
        pass
      except ConnectionRefusedError:
        if self.options.debug:
          print(f"proxy {self.wpid} got connection refused; exiting")
          sys.exit(1)
        print(f"proxy {self.wpid} got connection refused; retrying")
        await asyncio.sleep(1.0)
      except Exception as e:
        print(repr(e), e)

  async def check_session(self, key, wid):
    if not key:
      raise tornado.web.HTTPError(http.client.UNAUTHORIZED)

    key = key.decode("ascii")
    team, expiration = self.session_cache.get((key, wid), (None, None))
    if team and expiration > time.time(): return team

    req = tornado.httpclient.HTTPRequest(
      f"http://localhost:{self.options.wait_proxy_port}/checksession/{key}",
      connect_timeout=5.0,
      request_timeout=10.0)
    try:
      response = await self.client.fetch(req)
      reply = response.body.decode("ascii")
      if reply:
        team, expiration = reply.split()
        expiration = int(expiration)
        expiration -= WaitHandler.WAIT_TIMEOUT + WaitHandler.WAIT_SMEAR
        self.session_cache[(key, wid)] = (team, expiration)
        return team
    except tornado.httpclient.HTTPClientError as e:
      pass
    except ValueError:
      pass

    raise tornado.web.HTTPError(http.client.UNAUTHORIZED)


class ProxyTeam:
  BY_TEAM = {}
  OLD_MESSAGE_AGE = 10.0

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
    self.q = collections.deque()

  def __str__(self):
    return f"<ProxyTeam {self.team}>"

  async def send_messages(self, msgs):
    if not msgs: return

    now = time.time()
    for m in msgs:
      self.q.append((now, m))

    async with self.cv:
      self.cv.notify_all()

    cutoff = time.time() - self.OLD_MESSAGE_AGE
    while self.q and self.q[0][0] < cutoff:
      el = self.q.popleft()

  async def await_new_messages(self, received_serial, timeout):
    while True:
      if self.q and self.q[-1][1][0] > received_serial:
        # at least one message to send
        out = collections.deque()
        for ts, (s, m) in reversed(self.q):
          if s > received_serial:
            out.appendleft((s,m))
        return out

      async with self.cv:
        try:
          await asyncio.wait_for(self.cv.wait(), timeout)
        except asyncio.TimeoutError:
          return []


class WaitHandler(tornado.web.RequestHandler):
  WAIT_TIMEOUT = 600
  WAIT_SMEAR = 60

  def initialize(self, proxy_client):
    self.proxy_client = proxy_client

  async def get(self, wid, received_serial):
    key = self.get_secure_cookie(login.Session.COOKIE_NAME)
    team = await self.proxy_client.check_session(key, wid)
    team = ProxyTeam.get_team(team)

    wid = int(wid)
    received_serial = int(received_serial)

    timeout = self.WAIT_TIMEOUT + random.random() * self.WAIT_SMEAR

    msgs = await team.await_new_messages(received_serial, timeout)

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
