import re
import os
import tornado.web

import login

CONTENT_TYPES = {
  ".jpg": "image/jpeg",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".gif": "image/gif",

  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
  ".m4a": "audio/m4a",

  ".js": "text/javascript; charset=utf-8",
  ".json": "text/javascript; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",

  ".zip": "application/zip",
  ".pdf": "application/pdf",

  ".eot": "application/vnd.ms-fontobject",
  ".otf": "application/font-sfnt",
  ".ttf": "application/font-sfnt",
  ".woff": "application/font-woff",
  ".woff2": "font/woff2",

  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Debug-only handlers that reread the source file each time.

class DebugPathHandler(tornado.web.RequestHandler):
  @classmethod
  def set_static_content(cls, static_content):
    cls.static_content = static_content

  def get(self, path):
    base = os.getenv("HUNT2020_BASE")
    _, ext = os.path.splitext(path)
    mime = CONTENT_TYPES[ext]
    self.set_header("Content-Type", mime)
    print(f"DEBUG ACCESS: {base}/{path}")
    with open(f"{base}/{path}", "rb") as f:
      data = f.read()
    if ext == ".css":
      def replacer(m):
        return self.static_content[m.group(1)]
      data = re.sub(r"@@STATIC:([^@]+)@@", replacer, data.decode("utf-8")).encode("utf-8")
    self.write(data)

def GetHandlers():
  handlers = [
    (r"/debug/(.*)", DebugPathHandler),
    ]
  return handlers




