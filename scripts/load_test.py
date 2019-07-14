#!/usr/bin/python3

import asyncio
import json
import pprint
import random
import re
import resource

import tornado.gen
import tornado.ioloop
import tornado.httpclient


stats = {}

async def show_stats():
  while True:
    pprint.pprint(stats)
    await asyncio.sleep(1.0)


async def main():
  soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
  resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))



  client = tornado.httpclient.AsyncHTTPClient.configure(
    "tornado.curl_httpclient.CurlAsyncHTTPClient", max_clients=10000)
  client = tornado.httpclient.AsyncHTTPClient()

  browsers = tornado.gen.multi([simulate_browser(i, client, "leftout", "thou") for i in range(300)])
  await asyncio.gather(browsers,
                       show_stats())

  print(f"main is returning")


async def simulate_browser(my_id, client, username, password):
  await asyncio.sleep(my_id * 0.1)

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
    body="username=leftout&password=thou",
    follow_redirects=False,
    headers={"Cookie": cookie})

  try:
    response = await client.fetch(req)
    assert False
  except tornado.httpclient.HTTPClientError as e:
    assert e.code == 302

    #print(f"--- {my_id} logged in ---")

  tabs = tornado.gen.multi([simulate_tab(my_id, i, cookie, client) for i in range(10)])
  await tabs

async def simulate_tab(my_id, tab_num, cookie, client):
  #print(f"--- {my_id}.{tab_num} starting {cookie} ---")


  # Now we can fetch the home page to get assigned a waiter_id.

  req = tornado.httpclient.HTTPRequest(
    "http://snellen/",
    connect_timeout=5.0,
    request_timeout=10.0,
    follow_redirects=False,
    headers={"Cookie": cookie})

  #print(f"--- {my_id}.{tab_num} fetching ---")
  response = await client.fetch(req)
  #print(f"--- {my_id}.{tab_num} fetched ---")

  m = re.search(rb"waiter_id = (\d+)", response.body)
  wid = int(m.group(1))

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
  ioloop = tornado.ioloop.IOLoop.current()
  ioloop.run_sync(main)
