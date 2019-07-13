import tornado.web

class TeamPageHandler(tornado.web.RequestHandler):
  def get_template_namespace(self):
    d = {"team": self.team}

    if hasattr(self, "puzzle"):
      d["puzzle"] = self.puzzle
      d["state"] = self.team.puzzle_state[self.puzzle]
      script = ("<script>\n"
                f'var puzzle_id = "{self.puzzle.shortname}";\n'
                "var puzzle_init = null;\n"
                "</script>\n")
    else:
      d["puzzle"] = None
      script = ("<script>\n"
                "var puzzle_id = null;\n"
                "</script>\n")

    if self.application.settings.get("debug"):
      script += ("""<script src="/closure/goog/base.js"></script>\n"""
                        """<script src="/client-debug.js"></script>""")
    else:
      script += """<script src="/client.js"></script>"""

    d["script"] = script

    return d
