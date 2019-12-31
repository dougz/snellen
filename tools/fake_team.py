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


TEAMS = """acorns amateur area51 astro awesome bah band bees biggame blazers
bruins central codex conduction constructs control corvus dalton death
donner dootdoot dragoncakehat ducksoup dynamite etphone exercise exit
fellowship fevers fighters fish flower frumious galactic gnus
hedgehogs hunches hunters immoral janedoe knock ladder lastplace
lexhunt lexingtons love malls manateem mathcampers mathletes
metaphysical mindthegap mystere n3xt nair neuromology neverever nope
offinthelab omnom palindrome palmford plain planetix pluto praxis
providenc puzzkill puzzledom quiz reptilian resistance rhinos rofls
secrets sg shortz shrug singles slack slalom sloan snowman sorrymom
squad stooth team teammate teapots tng tried turquoise twtw unclear
unclear unseen uplate vaguely wafflehaus waslater whitelotus wizards
wpi wranglers wwe leftout""".split()

ADMIN = """fakedougz""".split()

stats = {}
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
    teams = [SimTeam(self, username, "snth") for username in TEAMS[:self.options.teams]]
    tasks = [t.go() for t in teams]

    if self.options.admin:
      admin = SimAdmin(self, ADMIN[0], "snth")
      tasks.append(admin.go())

    #tasks.append(self.show_stats())
    await asyncio.gather(*tasks)

  async def show_stats(self):
    last = None
    while True:
      if last != stats:
        last = copy.copy(stats)
        print(f"{time.time()}: {last}")
      await asyncio.sleep(1.0)

      if not LAUNCH.is_set() and last.get("LOGIN", 0) == self.options.teams * self.options.browsers * self.options.tabs:
        print("launching!")
        LAUNCH.set()

class SimBrowser:
  def __init__(self, sim, username, password):
    self.sim = sim
    self.username = username
    self.password = password

  async def login(self):
    async with self.sim.logins:
      print(f"--- {self.username} logging in ---")
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

        print(f"--- {self.username} logged in ---")

  async def get(self, url):
    req = tornado.httpclient.HTTPRequest(
      f"{self.sim.options.base_url}{url}",
      connect_timeout=5.0,
      request_timeout=10.0,
      follow_redirects=False,
      headers={"Cookie": self.cookie})

    try:
      response = await self.sim.client.fetch(req)
      return response.body
    except tornado.httpclient.HTTPClientError as e:
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
  def __init__(self, sim, username, password):
    super().__init__(sim, username, password)

  async def do_action(self, **d):
    await self.post("/action", json.dumps(d))

  async def go(self):
    print(f"starting {self.username}")
    await self.login()

    print(f"{self.username} logged in")
    if self.sim.options.slow:
      solves_per_minute = random.random() * 0.4 + 0.1
    else:
      solves_per_minute = random.random() * 7 + 3

    while True:
      delay = -math.log(1.0 - random.random()) / solves_per_minute * 60
      await asyncio.sleep(delay)
      if not await self.solve_one(): break
      await self.hint_one()

  async def solve_one(self):
    j = json.loads(await self.get("/js/puzzles"))

    open_puzzles = {}
    for land in j["lands"]:
      if "puzzles" not in land: continue
      for p in land["puzzles"]:
        url = p.get("url", "")
        if url.startswith("/puzzle/"):
          if "answer" not in p:
            open_puzzles[url[8:]] = ()
          elif p["answer"].endswith("\u2026"):
            a = p["answer"].split(",")
            a.pop()
            open_puzzles[url[8:]] = [i.strip() for i in a]

    if not open_puzzles:
      print("all puzzles solved")
      return len(j["lands"]) < 10

    for i in range(5):
      to_solve = random.choice(list(open_puzzles.keys()))
      if to_solve == "concierge_services": continue
      # Don't solve metas.
      meta = INFO_DUMP["puzzles"][to_solve][0]
      if not meta or random.random() < 0.1: break
    else:
      return True

    have = [canonicalize_answer(a) for a in open_puzzles[to_solve]]
    for a in INFO_DUMP["puzzles"][to_solve][1]:
      if a not in have:
        break
    print(f"{self.username} submitting {a} for {to_solve}")

    await self.do_action(action="submit", answer=a, puzzle_id=to_solve)
    return True

  async def hint_one(self):
    j = json.loads(await self.get("/js/hintsopen"))

    if j["current"]: return # waiting for response
    if not j["available"]: return  # no hints available

    a = [p for p in j["available"] if not p[2]]
    if not a: return  # all hint-available puzzles solved

    shortname = random.choice(a)[0]
    print(f"{self.username} requesting hint on {shortname}")

    await self.do_action(action="hint_request", puzzle_id=shortname, text="please help")



class SimAdmin(SimBrowser):
  def __init__(self, sim, username, password):
    super().__init__(sim, username, password)

  async def do_action(self, **d):
    await self.post("/admin/action", json.dumps(d))

  async def go(self):
    print(f"starting {self.username}")
    await self.login()

    print("logged in")
    while True:
      j = json.loads(await self.get("/admin/js/taskqueue"))
      count = 0
      claim_threshold = time.time() - (120 if self.sim.options.slow else 30)
      complete_threshold = time.time() - (300 if self.sim.options.slow else 60)
      for t in j.get("queue", ()):
        key = t.get("key", "")
        d = None
        if t["when"] < complete_threshold:
          if key.startswith("t-"):
            if not t.get("done_pending"):
              print(f"ADMIN {self.username} completing {key}")
              await self.do_action(action="complete_task", key=key, which="done")
          else:
            _, team_username, puzzle_id = key.split("-")
            print(f"ADMIN {self.username} replying to hint {key}")
            await self.do_action(action="hint_reply", team_username=team_username,
                                 puzzle_id=puzzle_id, text="be smarter")
        elif not t["claimant"] and t["when"] < claim_threshold:
          print(f"ADMIN {self.username} claiming {key}")
          await self.do_action(action="update_claim", key=key, which="claim")
        else:
          continue

      await asyncio.sleep(10)


  # async def simulate_browser(self, my_id, username, password, delay):
  #   await asyncio.sleep(delay)

  #   # Submit the login page.

  #   async with self.logins:
  #     print(f"--- {my_id} logging in ---")
  #     req = tornado.httpclient.HTTPRequest(
  #       f"{self.options.base_url}/login_submit",
  #       method="POST",
  #       body=f"username={username}&password={password}",
  #       follow_redirects=False)

  #     try:
  #       response = await self.client.fetch(req)
  #       assert False
  #     except tornado.httpclient.HTTPClientError as e:
  #       assert e.code == 302
  #       cookie = e.response.headers["Set-Cookie"].split(";")[0]

  #     print(f"--- {my_id} logged in ---")

  #   await asyncio.gather(self.solver(my_id, cookie))
  #   #*[self.simulate_tab(my_id, i, cookie) for i in range(options.tabs)])


  # async def simulate_tab(self, my_id, tab_num, cookie):
  #   #print(f"--- {my_id}.{tab_num} starting {cookie} ---")

  #   stats["LOGIN"] = stats.get("LOGIN", 0) + 1
  #   await LAUNCH.wait()

  #   #await asyncio.sleep(tab_num * 1.0)

  #   # Now we can fetch the home page to get assigned a waiter_id.

  #   req = tornado.httpclient.HTTPRequest(
  #     f"{self.options.base_url}/",
  #     connect_timeout=5.0,
  #     request_timeout=10.0,
  #     follow_redirects=False,
  #     headers={"Cookie": cookie})

  #   #print(f"--- {my_id}.{tab_num} fetching ---")
  #   try:
  #     response = await self.client.fetch(req)
  #   except tornado.httpclient.HTTPClientError as e:
  #     print(f"--- {my_id}.{tab_num} failed: {e} ---")
  #     return

  #   #print(f"--- {my_id}.{tab_num} fetched ---")

  #   m = re.search(rb"(?:wid|waiter_id) = (\d+)", response.body)
  #   wid = int(m.group(1))

  #   print(f"--- {my_id}.{tab_num} wid {wid} ---")

  #   serial = 0
  #   stats[serial] = stats.get(serial, 0) + 1
  #   while True:
  #     #print(f"--- {my_id}.{tab_num} waiting (wid {wid}) ---")
  #     req = tornado.httpclient.HTTPRequest(
  #       f"{self.options.base_url}/wait/{wid}/{serial}/10",
  #       follow_redirects=False,
  #       headers={"Cookie": cookie},
  #       request_timeout=600.0)

  #     old_serial = serial

  #     try:
  #       response = await self.client.fetch(req)
  #     except tornado.httpclient.HTTPClientError as e:
  #       print(e)
  #       continue

  #     #print(f"--- {my_id}.{tab_num} response ---")
  #     d = json.loads(response.body)
  #     for ser, msg in d:
  #       serial = max(serial, ser)
  #       #pprint.pprint(msg)

  #     stats[old_serial] -= 1
  #     if not stats[old_serial]: del stats[old_serial]
  #     stats[serial] = stats.get(serial, 0) + 1

  #     # random delay before waiting again, same as client.js
  #     await asyncio.sleep(random.random() * .250)


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("-t", "--teams", type=int, default=1)
  parser.add_argument("-b", "--browsers", type=int, default=1)
  parser.add_argument("-i", "--tabs", type=int, default=1)
  parser.add_argument("-a", "--info_dump", default=None)
  parser.add_argument("-u", "--base_url", default="http://snellen.fun")
  parser.add_argument("--slow", action="store_true", default=None)
  parser.add_argument("--admin", action="store_true", default=None)
  options = parser.parse_args()

  if options.info_dump:
    global INFO_DUMP
    with open(options.info_dump) as f:
      INFO_DUMP = json.load(f)
    pprint.pprint(INFO_DUMP)

  sim = Simulation(options)

  async def go():
    await sim.go()

  ioloop = tornado.ioloop.IOLoop.current()
  ioloop.run_sync(go)
