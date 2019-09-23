import re
import os
import tornado.web

import login

# Debug-only handlers that reread the source file each time.

class DebugPathHandler(tornado.web.RequestHandler):
  def get(self, event, path):
    static_dir = self.application.settings["static_dir"]
    if event:
      base = os.path.join(os.getenv("HUNT2020_BASE"), "bts_src")
    else:
      base = os.path.join(os.getenv("HUNT2020_BASE"), "snellen")
    _, ext = os.path.splitext(path)
    mime = {".css": "text/css; charset=utf-8",
            ".json": "text/javascript; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".png": "image/png",
            }[ext]
    self.set_header("Content-Type", mime)
    print(f"DEBUG ACCESS: {base}/{path}")
    with open(f"{base}/{path}", "rb") as f:
      data = f.read()
    if ext == ".css":
      def replacer(m):
        src = m.group(1)
        if src.startswith("static/") or src.startswith("src/"):
          dst = "/debug/" + src
        else:
          dst = "/debugevt/" + src
        print(f"replacing {src} with {dst}")
        return dst
      data = re.sub(r"@@STATIC:([^@]+)@@", replacer, data.decode("utf-8")).encode("utf-8")
    self.write(data)

def GetHandlers():
  handlers = [
    (r"/debug(event)?/(.*)", DebugPathHandler),
    ]
  return handlers




