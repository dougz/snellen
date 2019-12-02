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

ADMIN = """dougz""".split()

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


async def show_stats(options):
  last = None
  while True:
    if last != stats:
      last = copy.copy(stats)
      print(f"{time.time()}: {last}")
    await asyncio.sleep(1.0)

    if not LAUNCH.is_set() and last.get("LOGIN", 0) == options.teams * options.browsers * options.tabs:
      print("launching!")
      LAUNCH.set()


async def main(options):
  soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
  resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))

  client = tornado.httpclient.AsyncHTTPClient.configure(
    "tornado.curl_httpclient.CurlAsyncHTTPClient", max_clients=10000)
  client = tornado.httpclient.AsyncHTTPClient()

  logins = asyncio.Semaphore(value=2)
  options.logins = logins

  await asyncio.gather(*[simulate_team(client, username, "snth", options) for username in TEAMS[:options.teams]],
                       simulate_admin(client, ADMIN[0], "snth", options),
                       show_stats(options))


async def simulate_team(client, username, password, options):
  print(f"starting {username}")
  await asyncio.gather(*[simulate_browser(f"{username}_{i}", client, username, password, i * .1, options) for i in range(options.browsers)])

async def simulate_admin(client, username, password, options):

  # Submit the login page.

  async with options.logins:
    print(f"--- ADMIN {username} logging in ---")
    req = tornado.httpclient.HTTPRequest(
      f"{options.base_url}/login_submit",
      method="POST",
      body=f"username={username}&password={password}",
      follow_redirects=False)

    try:
      response = await client.fetch(req)
      assert False
    except tornado.httpclient.HTTPClientError as e:
      assert e.code == 302
      cookie = e.response.headers["Set-Cookie"].split(";")[0]

      print(f"--- ADMIN {username} logged in ---")

  await tasker(username, cookie, client, options)

async def tasker(username, cookie, client, options):
  while True:
    req = tornado.httpclient.HTTPRequest(
      f"{options.base_url}/admin/js/taskqueue",
      connect_timeout=5.0,
      request_timeout=10.0,
      follow_redirects=False,
      headers={"Cookie": cookie})

    try:
      response = await client.fetch(req)
    except tornado.httpclient.HTTPClientError as e:
      print(f"--- ADMIN {username} solver puzzle fetch failed: {e} ---")
      return

    j = json.loads(response.body)
    count = 0
    threshold = time.time() - 60
    for t in j.get("queue", ()):
      key = t.get("key", "")
      if not key.startswith("t-"): continue
      if t["when"] > threshold: continue
      d = {"action": "complete_task", "key": key, "which": "done"}
      print(f"ADMIN {username} completing {key}")

      req = tornado.httpclient.HTTPRequest(
        f"{options.base_url}/admin/action",
        method="POST",
        body=json.dumps(d),
        follow_redirects=False,
        headers={"Cookie": cookie})

      try:
        response = await client.fetch(req)
      except tornado.httpclient.HTTPClientError as e:
        print(f"--- ADMIN {username} failed to submit: {e} ---")
        return

      if response.code != 204:
        print(f"--- ADMIN {username} got back: {response.code} ---")

      count += 1
      if count >= 20: break

    await asyncio.sleep(10)



async def simulate_browser(my_id, client, username, password, delay, options):
  await asyncio.sleep(delay)

  # Submit the login page.

  async with options.logins:
    print(f"--- {my_id} logging in ---")
    req = tornado.httpclient.HTTPRequest(
      f"{options.base_url}/login_submit",
      method="POST",
      body=f"username={username}&password={password}",
      follow_redirects=False)

    try:
      response = await client.fetch(req)
      assert False
    except tornado.httpclient.HTTPClientError as e:
      assert e.code == 302
      cookie = e.response.headers["Set-Cookie"].split(";")[0]

    print(f"--- {my_id} logged in ---")

  await asyncio.gather(solver(my_id, cookie, client, options),
                       *[simulate_tab(my_id, i, cookie, client, options) for i in range(options.tabs)])

async def solver(my_id, cookie, client, options):
  solves_per_minute = random.random() * 7 + 3
  while True:
    delay = -math.log(1.0 - random.random()) / solves_per_minute * 60
    await asyncio.sleep(delay)
    if not await solve_one(my_id, cookie, client, options): break

async def solve_one(my_id, cookie, client, options):
  req = tornado.httpclient.HTTPRequest(
    f"{options.base_url}/js/puzzles",
    connect_timeout=5.0,
    request_timeout=10.0,
    follow_redirects=False,
    headers={"Cookie": cookie})

  try:
    response = await client.fetch(req)
  except tornado.httpclient.HTTPClientError as e:
    print(f"--- {my_id} solver puzzle fetch failed: {e} ---")
    return

  j = json.loads(response.body)

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

  to_solve = random.choice(list(open_puzzles.keys()))

  have = [canonicalize_answer(a) for a in open_puzzles[to_solve]]
  #print(f"answers {INFO_DUMP['puzzles'][to_solve]} have {open_puzzles[to_solve]}")
  for a in INFO_DUMP["puzzles"][to_solve]:
    if a not in have:
      break
  print(f"{my_id} submitting {a} for {to_solve}")

  d = {"action": "submit", "answer": a, "puzzle_id": to_solve}

  req = tornado.httpclient.HTTPRequest(
    f"{options.base_url}/action",
    method="POST",
    body=json.dumps(d),
    follow_redirects=False,
    headers={"Cookie": cookie})

  try:
    response = await client.fetch(req)
  except tornado.httpclient.HTTPClientError as e:
    print(f"--- {my_id} failed to submit: {e} ---")
    return

  if response.code == 204 or response.code == 409:
    return True



async def simulate_tab(my_id, tab_num, cookie, client, options):
  #print(f"--- {my_id}.{tab_num} starting {cookie} ---")

  stats["LOGIN"] = stats.get("LOGIN", 0) + 1
  await LAUNCH.wait()

  #await asyncio.sleep(tab_num * 1.0)

  # Now we can fetch the home page to get assigned a waiter_id.

  req = tornado.httpclient.HTTPRequest(
    f"{options.base_url}/",
    connect_timeout=5.0,
    request_timeout=10.0,
    follow_redirects=False,
    headers={"Cookie": cookie})

  #print(f"--- {my_id}.{tab_num} fetching ---")
  try:
    response = await client.fetch(req)
  except tornado.httpclient.HTTPClientError as e:
    print(f"--- {my_id}.{tab_num} failed: {e} ---")
    return

  #print(f"--- {my_id}.{tab_num} fetched ---")

  m = re.search(rb"(?:wid|waiter_id) = (\d+)", response.body)
  wid = int(m.group(1))

  print(f"--- {my_id}.{tab_num} wid {wid} ---")

  serial = 0
  stats[serial] = stats.get(serial, 0) + 1
  while True:
    #print(f"--- {my_id}.{tab_num} waiting (wid {wid}) ---")
    req = tornado.httpclient.HTTPRequest(
      f"{options.base_url}/wait/{wid}/{serial}/10",
      follow_redirects=False,
      headers={"Cookie": cookie},
      request_timeout=600.0)

    old_serial = serial

    try:
      response = await client.fetch(req)
    except tornado.httpclient.HTTPClientError as e:
      print(e)
      continue

    #print(f"--- {my_id}.{tab_num} response ---")
    d = json.loads(response.body)
    for ser, msg in d:
      serial = max(serial, ser)
      #pprint.pprint(msg)

    stats[old_serial] -= 1
    if not stats[old_serial]: del stats[old_serial]
    stats[serial] = stats.get(serial, 0) + 1

    # random delay before waiting again, same as client.js
    await asyncio.sleep(random.random() * .250)


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("-t", "--teams", type=int, default=1)
  parser.add_argument("-b", "--browsers", type=int, default=1)
  parser.add_argument("-i", "--tabs", type=int, default=1)
  parser.add_argument("-a", "--info_dump", default=None)
  parser.add_argument("-u", "--base_url", default="http://snellen.fun")
  options = parser.parse_args()

  if options.info_dump:
    global INFO_DUMP
    with open(options.info_dump) as f:
      INFO_DUMP = json.load(f)
    pprint.pprint(INFO_DUMP)

  async def go():
    await main(options)

  ioloop = tornado.ioloop.IOLoop.current()
  ioloop.run_sync(go)
