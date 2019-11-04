#!/usr/bin/python3

import argparse
import asyncio
import copy
import json
import pprint
import random
import re
import resource
import time

import tornado.gen
import tornado.ioloop
import tornado.httpclient


TEAMS = """acorns amateur area51 astro awesome bah band bees biggame blazers
bruins central codex conduction constructs control corvus dalton death
donner dootdoot dragoncakehat ducksoup dynamite etphone exercise exit
fellowship fevers fighters fish flower frumious galactic gnus
hedgehogs hunches hunters immoral janedoe knock ladder lastplace
leftout lexhunt lexingtons love malls manateem mathcampers mathletes
metaphysical mindthegap mystere n3xt nair neuromology neverever nope
offinthelab omnom palindrome palmford plain planetix pluto praxis
providenc puzzkill puzzledom quiz reptilian resistance rhinos rofls
secrets sg shortz shrug singles slack slalom sloan snowman sorrymom
squad stooth team teammate teapots tng tried turquoise twtw unclear
unclear unseen uplate vaguely wafflehaus waslater whitelotus wizards
wpi wranglers wwe""".split()

stats = {}
LAUNCH = asyncio.Event()

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

  teams = tornado.gen.multi([simulate_team(client, username, "aoeu", options) for username in TEAMS[:options.teams]])

  await asyncio.gather(teams, show_stats(options))


async def simulate_team(client, username, password, options):
  print(f"starting {username}")
  browsers = tornado.gen.multi([simulate_browser(f"{username}_{i}", client, username, password, i * .025, options) for i in range(options.browsers)])
  await browsers

async def simulate_browser(my_id, client, username, password, delay, options):
  await asyncio.sleep(delay)

  print(f"--- {my_id} logging in ---")
  # Fetch the home page so we're issued a session cookie.

  req = tornado.httpclient.HTTPRequest(
    "http://snellen/",
    follow_redirects=False)

  try:
    response = await client.fetch(req)
    assert False
  except tornado.httpclient.HTTPClientError as e:
    assert e.code == 302
    cookie = e.response.headers["Set-Cookie"].split(";")[0]

  # Submit the login page.

  req = tornado.httpclient.HTTPRequest(
    "http://snellen/login_submit",
    method="POST",
    body=f"username={username}&password={password}",
    follow_redirects=False,
    headers={"Cookie": cookie})

  try:
    response = await client.fetch(req)
    assert False
  except tornado.httpclient.HTTPClientError as e:
    assert e.code == 302

    print(f"--- {my_id} logged in ---")

  tabs = tornado.gen.multi([simulate_tab(my_id, i, cookie, client) for i in range(options.tabs)])
  await tabs

async def simulate_tab(my_id, tab_num, cookie, client):
  #print(f"--- {my_id}.{tab_num} starting {cookie} ---")

  stats["LOGIN"] = stats.get("LOGIN", 0) + 1
  await LAUNCH.wait()

  await asyncio.sleep(tab_num * 1.0)

  # Now we can fetch the home page to get assigned a waiter_id.

  req = tornado.httpclient.HTTPRequest(
    "http://snellen/",
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
      f"http://snellen/wait/{wid}/{serial}",
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
  options = parser.parse_args()

  async def go():
    await main(options)

  ioloop = tornado.ioloop.IOLoop.current()
  ioloop.run_sync(go)
