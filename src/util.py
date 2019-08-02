import asyncio
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

    if hasattr(self, "puzzle"):
      d["puzzle"] = self.puzzle
      d["state"] = self.team.puzzle_state[self.puzzle]
      script = ("<script>\n"
                f'var puzzle_id = "{self.puzzle.shortname}";\n'
                "var puzzle_init = null;\n"
                f"var waiter_id = {wid};\n"
                "</script>\n")
    else:
      d["puzzle"] = None
      script = ("<script>\n"
                "var puzzle_id = null;\n"
                f"var waiter_id = {wid};\n"
                "</script>\n")

    if self.application.settings.get("debug"):
      script += ("""<script src="/closure/goog/base.js"></script>\n"""
                        """<script src="/client.js"></script>""")
      d["css"] = "/event.css"
    else:
      script += f"""<script src="{self.static_content["client-compiled.js"]}"></script>"""
      d["css"] = self.static_content["event.css"]

    d["script"] = script
    d["json_data"] = None

    return d

class AdminPageHandler(tornado.web.RequestHandler):
  def prepare(self):
    self.set_header("Content-Type", "text/html; charset=utf-8")

  @classmethod
  def set_static_content(cls, static_content):
    cls.static_content = static_content

  def get_template_namespace(self):
    d = {}

    if self.application.settings.get("debug"):
      d["script"] = ("""<script src="/closure/goog/base.js"></script>\n"""
                     """<script src="/admin.js"></script>""")
      d["css"] = "/admin.css"
    else:
      d["script"] = f"""<script src="{self.static_content["admin-compiled.js"]}"></script>"""
      d["css"] = self.static_content["admin.css"]

    return d

