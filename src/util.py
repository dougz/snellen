import asyncio
import game
import string
import time
import tornado.web

import wait_proxy

class TeamHandler(tornado.web.RequestHandler):
  def on_finish(self):
    if not hasattr(self, "team"): return
    asyncio.create_task(self.team.flush_messages())


class TeamPageHandler(TeamHandler):
  def prepare(self):
    self.set_header("Content-Type", "text/html; charset=utf-8")

  @classmethod
  def set_static_content(cls, static_content):
    cls.static_content = static_content

  def get_template_namespace(self):
    d = {"team": self.team}

    wid = wait_proxy.Server.new_waiter_id()
    serial = self.team.next_serial() - 1

    if hasattr(self, "puzzle"):
      d["puzzle"] = self.puzzle
      d["state"] = self.team.puzzle_state[self.puzzle]
      script = ("<script>\n"
                f'var puzzle_id = "{self.puzzle.shortname}";\n'
                "var puzzle_init = null;\n"
                f"var waiter_id = {wid}; var received_serial = {serial};\n"
                "</script>\n")
    else:
      d["puzzle"] = None
      script = ("<script>\n"
                "var puzzle_id = null;\n"
                f"var waiter_id = {wid}; var received_serial = {serial};\n"
                "</script>\n")

    if self.application.settings.get("debug"):
      script += ("""<script src="/closure/goog/base.js"></script>\n"""
                 """<script src="/debug/src/client.js"></script>""")
      d["css"] = ["/debug/static/event.css"]
    else:
      script += f"""<script src="{self.static_content["client-compiled.js"]}"></script>"""
      d["css"] = [self.static_content["event.css"]]

    d["script"] = script
    d["json_data"] = None
    d["park_open"] = (game.Global.STATE.event_start_time is not None)

    return d

class AdminPageHandler(tornado.web.RequestHandler):
  def prepare(self):
    self.set_header("Content-Type", "text/html; charset=utf-8")

  @classmethod
  def set_static_content(cls, static_content):
    cls.static_content = static_content

  def get_template_namespace(self):
    d = {"user": self.user,
         "format_timestamp": format_timestamp}

    wid = wait_proxy.Server.new_waiter_id()

    st = game.Global.STATE
    if st.event_start_time:
      d["launched"] = time.time() - st.event_start_time
    else:
      d["launched"] = None
      d["until_launch"] = st.expected_start_time - time.time()
    d["format_duration"] = format_duration

    if self.application.settings.get("debug"):
      d["script"] = ("""<script src="/closure/goog/base.js"></script>\n"""
                     """<script src="/debug/src/admin.js"></script>""")
      d["css"] = "/debug/static/admin.css"
    else:
      d["script"] = f"""<script src="{self.static_content["admin-compiled.js"]}"></script>"""
      d["css"] = self.static_content["admin.css"]

    d["script"] += f"<script>var waiter_id = {wid};</script>"
    return d

def format_duration(sec):
  out = []
  if sec < 0:
    out.append("-")
    sec = -sec

  sec = int(sec)
  hours = sec // 3600
  sec = sec % 3600
  mins = sec // 60
  sec = sec % 60

  if hours:
    out.append(f"{hours}h ")
  if hours or mins:
    out.append(f"{mins}m ")
  out.append(f"{sec}s")
  return "".join(out)

def make_sortkey(s):
  s = [k for k in s.lower() if k in string.ascii_lowercase + " "]
  s = "".join(s).split()
  while len(s) > 1 and s[0] in ("the", "a", "an"):
    s.pop(0)
  return "".join(s)

def format_timestamp(ts):
  if ts is None:
    return "\u2014"
  else:
    ref = game.Global.STATE.event_start_time
    if ref:
      return time.ctime(ts) + " (" + format_duration(ts-ref) + " into hunt)"
    else:
      return time.ctime(ts)
