import asyncio
import json
import tornado.web
import tornado.httpclient


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
  async def send_message(cls, team, objs):
    if not isinstance(team, str):
      team = team.username
    x = (team, objs)
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


def GetHandlers():
  return [
    (r"/proxywait/(\d+)", ProxyWaitHandler),
  ]


##
## client side
##


class ProxyWaitClient:
  def __init__(self, wpid):
    self.wpid = wpid

    tornado.httpclient.AsyncHTTPClient.configure(
      "tornado.curl_httpclient.CurlAsyncHTTPClient", max_clients=10000)
    self.client = tornado.httpclient.AsyncHTTPClient()

  async def serve(self):
    # Give main server time to start up.
    await asyncio.sleep(2.0)

    while True:
      msgs = await get_messages(self.client, self.wpid)
      print(msgs)


async def get_messages(client, wpid):
  while True:
    req = tornado.httpclient.HTTPRequest(
      f"http://localhost/proxywait/{wpid}",
      connect_timeout=5.0,
      request_timeout=PROXY_WAIT_TIMEOUT+10)
    try:
      return await client.fetch(req)
    except tornado.httpclient.HTTPClientError as e:
      if e.code == 502:
        print(f"proxy {wpid} got 502; retrying")
        await asyncio.sleep(1.0)
      else:
        raise









