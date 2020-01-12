#!/usr/bin/python3

import argparse
import asyncio
import copy
import json
import math
import pprint
import random
import re
import resource
import time
import unicodedata

import tornado.ioloop
import tornado.httpclient


ADMIN = """fakedougz""".split()

stats = {"page_loads": [], "start_times": {}}

LAUNCH = asyncio.Event()

def canonicalize_answer(text):
  text = unicodedata.normalize("NFD", text.upper())
  out = []
  for k in text:
    cat = unicodedata.category(k)
    # Letters, "other symbols", or specific characters needed for complex emojis
    if cat == "So" or cat[0] == "L" or k == u"\u200D" or k == u"\uFE0F":
      out.append(k)
  return "".join(out)


class Simulation:
  def __init__(self, options):
    self.options = options

    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))

    tornado.httpclient.AsyncHTTPClient.configure(
      "tornado.curl_httpclient.CurlAsyncHTTPClient", max_clients=10000)
    self.client = tornado.httpclient.AsyncHTTPClient()

    self.logins = asyncio.Semaphore(value=2)

  async def go(self):
    admin = SimAdmin(self, ADMIN[0], "snth")
    teams = await admin.get_teams()
    print(teams)

    tasks = []
    for username in teams[:self.options.teams]:
      for i in range(self.options.browsers):
        t = SimTeam(self, username, "snth", self.options.tabs)
        tasks.append(t.go())

    expected = self.options.teams * self.options.browsers * self.options.tabs
    tasks.append(self.show_stats(expected))
    await asyncio.gather(*tasks)

  async def show_stats(self, expected):
    while len(stats["page_loads"]) < expected:
      pprint.pprint(stats["start_times"])
      await asyncio.sleep(1.0)

    print(stats["page_loads"])
    print(len(stats["page_loads"]), expected)

    with open("/tmp/times.txt", "w") as f:
      for x in stats["page_loads"]:
        f.write(f"{x}\n")


class SimBrowser:
  def __init__(self, sim, username, password):
    self.sim = sim
    self.username = username
    self.password = password

  async def login(self):
    async with self.sim.logins:
      #print(f"--- {self.username} logging in ---")
      req = tornado.httpclient.HTTPRequest(
        f"{self.sim.options.base_url}/login_submit",
        method="POST",
        connect_timeout=5.0,
        request_timeout=10.0,
        body=f"username={self.username}&password={self.password}",
        follow_redirects=False)

      try:
        response = await self.sim.client.fetch(req)
        raise RuntimeError()
      except tornado.httpclient.HTTPClientError as e:
        assert e.code == 302
        self.cookie = e.response.headers["Set-Cookie"].split(";")[0]

        #print(f"--- {self.username} logged in ---")

  async def get(self, url, timeout=10):
    req = tornado.httpclient.HTTPRequest(
      f"{self.sim.options.base_url}{url}",
      connect_timeout=timeout,
      request_timeout=timeout,
      follow_redirects=False,
      headers={"Cookie": self.cookie})

    try:
      response = await self.sim.client.fetch(req)
      return response.body
    except tornado.httpclient.HTTPClientError as e:
      print(e)
      return None

  async def post(self, url, data):
      req = tornado.httpclient.HTTPRequest(
        f"{self.sim.options.base_url}{url}",
        method="POST",
        body=data,
        connect_timeout=5.0,
        request_timeout=10.0,
        follow_redirects=False,
        headers={"Cookie": self.cookie})

      try:
        response = await self.sim.client.fetch(req)
      except tornado.httpclient.HTTPClientError as e:
        raise RuntimeError()

      if response.code == 200:
        return response.body
      elif response.code == 204 or response_code == 409:
        return None
      else:
        raise RuntimeError()


class SimTeam(SimBrowser):
  def __init__(self, sim, username, password, tabs):
    super().__init__(sim, username, password)
    self.tabs = tabs

  async def do_action(self, **d):
    await self.post("/action", json.dumps(d))

  async def go(self):
    print(f"starting {self.username}")
    await self.login()

    tasks = [self.one_tab() for i in range(self.tabs)]
    await asyncio.gather(*tasks)

  async def one_tab(self):
    wid, serial = await self.load_page("/")
    start_time = await self.wait_for_launch(wid, serial)
    if start_time:
      wid, serial = await self.load_page("/")
      if not serial:
        stats["page_loads"].append("fail")
      else:
        now = time.time()
        delay = now - start_time
        stats["page_loads"].append(int(delay*1000))

  async def load_page(self, url):
    result = await self.get("/")
    if not result: return None, None
    result = result.decode("utf-8")

    m = re.search(r"var wid = (\d+);", result)
    assert m
    wid = int(m.group(1))

    m = re.search(r"var received_serial = (\d+);", result)
    assert m
    serial = int(m.group(1))

    return wid, serial

  async def wait_for_launch(self, wid, serial):
    delay = 10.0
    start_time = None
    known_times = stats["start_times"]
    known_times[start_time] = known_times.get(start_time, 0) + 1
    while start_time is None or time.time() < start_time + 15:
      #print(f"waiting ({int(delay)})...")
      r = await self.get(f"/wait/{wid}/{serial}/{int(delay)}", timeout=delay+5)
      if r is None:
        print("error")
        return

      j = json.loads(r.decode("utf-8"))
      if not j:
        delay = min(300, delay*1.5)
        continue

      delay = 10.0
      for ser, msg in j:
        serial = max(serial, ser)
        #print(msg)
        if msg["method"] == "update_start":
          known_times[start_time] = known_times.get(start_time, 0) - 1
          if known_times[start_time] == 0:
            del known_times[start_time]
          start_time = msg["new_start"]
          known_times[start_time] = known_times.get(start_time, 0) + 1
        if msg["method"] == "to_page": return start_time


class SimAdmin(SimBrowser):
  def __init__(self, sim, username, password):
    super().__init__(sim, username, password)

  async def do_action(self, **d):
    await self.post("/admin/action", json.dumps(d))

  async def get_teams(self):
    await self.login()

    j = json.loads(await self.get("/admin/js/teams"))
    return [d["url"].split("/")[-1] for d in j if "allopen" not in d["url"]]


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("-t", "--teams", type=int, default=1)
  parser.add_argument("-b", "--browsers", type=int, default=1)
  parser.add_argument("-i", "--tabs", type=int, default=1)
  parser.add_argument("-u", "--base_url", default="http://snellen.fun")
  options = parser.parse_args()

  sim = Simulation(options)

  async def go():
    await sim.go()

  ioloop = tornado.ioloop.IOLoop.current()
  ioloop.run_sync(go)
