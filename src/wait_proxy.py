import asyncio
import http.client
import json
import tornado.web
import tornado.httpclient
import tornado.httpserver
import tornado.netutil

import login

PROXY_WAIT_TIMEOUT = 30 # seconds


##
## server side
##


class ProxyWait:
  PROXIES = []

  def __init__(self, wpid):
    self.cv = asyncio.Condition()
    self.q = []

  @classmethod
  def init_proxies(cls, count):
    for i in range(count):
      cls.PROXIES.append(ProxyWait(i))

  @classmethod
  async def send_message(cls, team, strs):
    if not isinstance(team, str):
      team = team.username
    x = (team, strs)
    for p in cls.PROXIES:
      async with p.cv:
        p.q.append(x)
        p.cv.notify_all()


class ProxyWaitHandler(tornado.web.RequestHandler):
  async def get(self, wpid):
    wpid = int(wpid)
    proxy = ProxyWait.PROXIES[wpid]

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


class ProxyWaitClient:
  def __init__(self, wpid, options):
    self.wpid = wpid
    self.options = options

    self.session_cache = {}

    tornado.httpclient.AsyncHTTPClient.configure(
      "tornado.curl_httpclient.CurlAsyncHTTPClient", max_clients=10000)
    self.client = tornado.httpclient.AsyncHTTPClient()

    app = tornado.web.Application(
      [
        (r"/wait/(\d+)/(\d+)", WaitHandler, {"proxy_client": self}),
      ],
      cookie_secret=options.cookie_secret)

    self.server = tornado.httpserver.HTTPServer(app)
    socket = tornado.netutil.bind_unix_socket(f"{options.socket_path}_p{wpid}", mode=0o666, backlog=3072)
    self.server.add_socket(socket)


  async def fetch(self):
    # Give main server time to start up.
    await asyncio.sleep(2.0)

    print(f"fetcher {self.wpid} is starting")
    while True:
      msgs = await self.get_messages()
      print(msgs)


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
          print(f"proxy {wpid} got 502; retrying")
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



class WaitHandler(tornado.web.RequestHandler):
  WAIT_TIMEOUT = 300
  WAIT_SMEAR = 20

  def initialize(self, proxy_client):
    self.proxy_client = proxy_client

  async def get(self, wid, received_serial):
    key = self.get_secure_cookie(login.Session.COOKIE_NAME)
    team = await self.proxy_client.check_session(key)

    wid = int(wid)
    received_serial = int(received_serial)

    print(f"received wait {wid} {received_serial} session {key} team {team}")

    # waiter = self.session.get_waiter(wid)
    # if not waiter:
    #   print(f"unknown waiter {wid}")
    #   raise tornado.web.HTTPError(http.client.NOT_FOUND)

    # msgs = await waiter.wait(received_serial,
    #                    self.WAIT_TIMEOUT + random.random() * self.WAIT_SMEAR)
    await asyncio.sleep(10.0)
    msgs = ()

    self.set_header("Content-Type", "application/json")
    self.set_header("Cache-Control", "no-store")
    self.write(b"[")
    for i, (ser, obj) in enumerate(msgs):
      if i > 0: self.write(b",")
      self.write(f"[{ser},{obj}]".encode("utf-8"))
    self.write(b"]")







