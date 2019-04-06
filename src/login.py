import base64
import functools
import os
import time

import tornado.web

class AdminUser:
  BY_USERNAME = {}

  def __init__(self, username, password, fullname, roles):
    self.username = username
    self.password = password
    self.fullname = fullname
    self.roles = set(roles)

    self.BY_USERNAME[username] = self

  @classmethod
  def GetUser(self, username):
    return self.BY_USERNAME.get(username)

  def CheckPassword(self, password):
    if self.password == password:
      return True
    return False


AdminUser("root", "joshua", "He<b>ll</b>o", ["create_users"])


class Session:
  BY_KEY = {}
  SESSION_TIMEOUT = 5   # seconds
  COOKIE_NAME = "SESSION"

  def __init__(self, user=None, *caps):
    self.key = base64.urlsafe_b64encode(os.urandom(16))
    self.BY_KEY[self.key] = self
    self.user = user
    self.team = None
    self.capabilities = set(caps)
    self.bad_login = False
    self.expires = time.time() + self.SESSION_TIMEOUT

  def set_cookie(self, req):
    req.set_secure_cookie(self.COOKIE_NAME, self.key)

  @classmethod
  def from_request(cls, req):
    key = req.get_secure_cookie(cls.COOKIE_NAME)
    if not key: return None
    return cls.BY_KEY.get(key)

  @classmethod
  def delete_from_request(cls, req):
    key = req.get_secure_cookie(cls.COOKIE_NAME)
    if key:
      req.clear_cookie(cls.COOKIE_NAME)
      cls.BY_KEY.pop(key, None)


# A decorator that can be applied to a request handler's get() or
# post() methods to require the request come while logged in with an
# account with a given capability.  The browser is redirected to the
# login or access-denied page as appropriate.
class required:
  def __init__(self, cap=None):
    self.cap = cap
  def __call__(self, func):
    @functools.wraps(func)
    def wrapped_func(req):
      session = Session.from_request(req)
      if not session:
        req.redirect("/login")
        return
      now = time.time()
      if now > session.expires:
        Session.delete_from_request(req)
        req.redirect("/login")
        return
      if self.cap not in session.capabilities:
        print("bad cap")
        req.redirect("/no_access")
        return
      session.expires = now + session.SESSION_TIMEOUT
      req.session = session
      req.user = session.user
      req.team = session.team
      return func(req)
    return wrapped_func


class Login(tornado.web.RequestHandler):
  def get(self):
    session = Session.from_request(self)
    self.render("login.html", bad_login=session and session.bad_login)


class LoginSubmit(tornado.web.RequestHandler):
  def post(self):
    # Find the browser's existing session or create a new one.
    session = Session.from_request(self)
    if not session:
      session = Session(None)
      session.set_cookie(self)

    username = self.get_argument("username")
    password = self.get_argument("password")
    user = AdminUser.GetUser(username)
    if user and user.CheckPassword(password):
      session.user = user
      session.capabilities = set(["admin"])
      session.bad_login = False
      self.redirect("/admin")
    else:
      session.bad_login = True
      self.redirect("/login")


class Logout(tornado.web.RequestHandler):
  def get(self):
    # Uncookie the browser, delete the session, send them back to the
    # login page.
    Session.delete_from_request(self)
    self.redirect("/login")


class NoAccess(tornado.web.RequestHandler):
  def get(self):
    self.render("no_access.html")

HANDLERS = [
  (r"/login", Login),
  (r"/login_submit", LoginSubmit),
  (r"/no_access", NoAccess),
  (r"/logout", Logout),
  ]

