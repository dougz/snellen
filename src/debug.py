import re
import os
import tornado.web

import login

# Debug-only handlers that reread the source file each time.

class DebugPathHandler(tornado.web.RequestHandler):
  def get(self, path):
    static_dir = self.application.settings["static_dir"]
    base = os.path.join(os.getenv("HUNT2020_BASE"), "snellen")
    _, ext = os.path.splitext(path)
    mime = {".css": "text/css; charset=utf-8",
            ".json": "text/javascript; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            }[ext]
    self.set_header("Content-Type", mime)
    print(f"DEBUG ACCESS: {base}/{path}")
    with open(f"{base}/{path}", "r") as f:
      text = f.read()
    if ext == ".css":
      def replacer(m):
        return static_dir.get(m.group(1), m.group(1))
      text = re.sub(r"@@STATIC:([^@]+)@@", replacer, text)
    self.write(text.encode("utf-8"))

def GetHandlers():
  handlers = [
    (r"/debug/(.*)", DebugPathHandler),
    ]
  return handlers




