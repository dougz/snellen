import re
import os
import tornado.web

import login

# Debug-only handlers that reread the source file each time.

class ClientJS(tornado.web.RequestHandler):
  def get(self):
    self.set_header("Content-Type", "text/javascript; charset=utf-8")
    base = os.path.join(os.getenv("HUNT2020_BASE"), "snellen")
    with open(f"{base}/src/client.js", "rb") as f:
      self.write(f.read())

class EventCSS(tornado.web.RequestHandler):
  def get(self):
    self.set_header("Content-Type", "text/css; charset=utf-8")
    static_dir = self.application.settings["static_dir"]
    base = os.path.join(os.getenv("HUNT2020_BASE"), "snellen")
    with open(f"{base}/static/event.css", "r") as f:
      text = f.read()
      def replacer(m):
        return static_dir.get(m.group(1), m.group(1))
      text = re.sub(r"@@STATIC:([^@]+)@@", replacer, text)
      self.write(text.encode("utf-8"))

class AdminJS(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.set_header("Content-Type", "text/javascript; charset=utf-8")
    base = os.path.join(os.getenv("HUNT2020_BASE"), "snellen")
    with open(f"{base}/src/admin.js", "rb") as f:
      self.write(f.read())

class AdminCSS(tornado.web.RequestHandler):
  @login.required("admin")
  def get(self):
    self.set_header("Content-Type", "text/css; charset=utf-8")
    static_dir = self.application.settings["static_dir"]
    base = os.path.join(os.getenv("HUNT2020_BASE"), "snellen")
    with open(f"{base}/static/admin.css", "r") as f:
      text = f.read()
      def replacer(m):
        return static_dir.get(m.group(1), m.group(1))
      text = re.sub(r"@@STATIC:([^@]+)@@", replacer, text)
      self.write(text.encode("utf-8"))

def GetHandlers():
  handlers = [
    (r"/client.js", ClientJS),
    (r"/event.css", EventCSS),
    (r"/admin.js", AdminJS),
    (r"/admin.css", AdminCSS),
    ]
  return handlers




