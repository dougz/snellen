import asyncio
import game
import http
import json
import string
import time
import tornado.web
import unicodedata

import login
import wait_proxy

class TeamHandler(tornado.web.RequestHandler):
  def on_finish(self):
    if not hasattr(self, "team"): return
    if self.team:
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

    script = ["<script>"]

    if hasattr(self, "puzzle"):
      d["puzzle"] = self.puzzle
      d["state"] = self.team.puzzle_state[self.puzzle]
      script.append(
        f'var puzzle_id = "{self.puzzle.shortname}";\n'
        "var puzzle_init = null;\n"
      )
    else:
      d["puzzle"] = None
      script.append("var puzzle_id = null;\n")

    script.append(f"""var wid = {wid}; var received_serial = {serial};\n""")
    script.append(f"""var initial_header = {json.dumps(self.team.get_header_data())};\n""")
    script.append(f"""var eurl = "{self.static_content["emoji"]}";\n""")
    script.append(f"""var edb = "{self.static_content["emoji.json"]}";\n""")
    script.append("</script>")

    if self.application.settings.get("debug"):
      script.append("""<script src="/closure/goog/base.js"></script>\n"""
                    """<script src="/debug/snellen/src/common.js"></script>"""
                    """<script src="/debug/snellen/src/twemoji.js"></script>"""
                    """<script src="/debug/snellen/src/client.js"></script>""")
    else:
      script.append(f"""<script src="{self.static_content["client-compiled.js"]}"></script>""")

    d["css"] = [self.static_content["event.css"]]

    d["script"] = "".join(script)
    d["json_data"] = None
    d["park_open"] = (game.Global.STATE.event_start_time is not None)
    d["logo_nav"] = self.static_content["logo-nav.png"]

    return d

class AdminHandler(tornado.web.RequestHandler):
  def get_team(self, username):
    team = game.Team.get_by_username(username)
    if not team:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    self.pageteam = team
    return team

  def get_puzzle(self, shortname):
    puzzle = game.Puzzle.get_by_shortname(shortname)
    if not puzzle:
      raise tornado.web.HTTPError(http.client.NOT_FOUND)
    self.pagepuzzle = puzzle
    return puzzle


class AdminPageHandler(AdminHandler):
  @classmethod
  def set_attribute(cls, attr, value):
    setattr(cls, attr, value)

  def prepare(self):
    self.set_header("Content-Type", "text/html; charset=utf-8")
    self.pageteam = None
    self.pagepuzzle = None

  @classmethod
  def set_static_content(cls, static_content):
    cls.static_content = static_content

  def get_template_namespace(self):
    d = {"user": self.user,
         "format_timestamp": format_timestamp,
         "puzzle_json_url": self.puzzle_json_url,
         "team_json_url": self.team_json_url}

    wid = wait_proxy.Server.new_waiter_id()
    serial = login.AdminUser.message_serial - 1

    st = game.Global.STATE
    if st.event_start_time:
      d["launch"] = st.event_start_time
    else:
      d["launch"] = None
      d["expected_launch"] = st.expected_start_time
    d["format_duration"] = format_duration

    script = ["<script>"]
    script.append(f"""var wid = {wid};\n""")
    script.append(f"""var received_serial = {serial};""")
    script.append(f"""var eurl = "{self.static_content["emoji"]}";\n""")
    script.append(f"""var edb = "{self.static_content["emoji.json"]}";\n""")
    script.append("</script>")


    if self.application.settings.get("debug"):
      script.append("""<script src="/closure/goog/base.js"></script>\n"""
                    """<script src="/debug/snellen/src/common.js"></script>"""
                    """<script src="/debug/snellen/src/twemoji.js"></script>"""
                    """<script src="/debug/snellen/src/admin.js"></script>""")
    else:
      script.append(f"""<script src="{self.static_content["admin-compiled.js"]}"></script>""")

    d["css"] = self.static_content["admin.css"]
    d["home"] = self.static_content["home.svg"]

    d["script"] = "".join(script)

    d["json_data"] = None
    d["team_username"] = (f'"{self.pageteam.username}"') if self.pageteam else "null"
    d["puzzle_id"] = (f'"{self.pagepuzzle.shortname}"') if self.pagepuzzle else "null"
    if self.pageteam: d["team"] = self.pageteam
    if self.pagepuzzle: d["puzzle"] = self.pagepuzzle

    bbdata = st.task_queue.get_bb_data()
    color = "green"
    if bbdata["size"] > 0:
      if bbdata["claimed"] < bbdata["size"]:
        color = "red"
      else:
        color = "amber"

    d["favicon32"] = self.static_content[f"admin_fav_{color}/favicon-32x32.png"]
    d["favicon16"] = self.static_content[f"admin_fav_{color}/favicon-16x16.png"]

    return d

def format_duration(sec):
  out = []
  sec = int(sec)
  if sec < 0:
    out.append("-")
    sec = -sec

  if sec < 60:
    out.append(f"0:{sec:02d}")
    return "".join(out)

  hours = sec // 3600
  sec = sec % 3600
  mins = sec // 60
  sec = sec % 60

  out = f"{hours:02d}:{mins:02d}:{sec:02d}".lstrip("0:")
  return out

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
    t = time.strftime("%a %-I:%M:%S%p", time.localtime(ts))
    t = t[:-2] + t[-2:].lower()
    if ref:
      return t + " (" + format_duration(ts-ref) + " into hunt)"
    else:
      return t

def explain_unicode(s):
  out = []
  ascii = True
  for k in s:
    if ord(k) < 128: continue
    ascii = False
    out.append(" ")
    out.append(hex(ord(k)))
    out.append("\u00a0(")
    out.append(unicodedata.name(k, "??"))
    out.append(")")
  if ascii: return None
  return "".join(out[1:])
