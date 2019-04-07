import base64
import bcrypt
import functools
import os
import time

import tornado.web

import state

class AdminRoles:
  CREATE_USERS = "create_users"


class AdminUser:
  def __init__(self, username, password_hash, fullname, roles):
    self.username = username
    self.password_hash = password_hash
    self.fullname = fullname
    self.roles = roles

  def CheckPassword(self, password):
    if bcrypt.checkpw(password.encode("utf-8"), self.password_hash):
      return True
    return False

  def HasRole(self, role):
    return role in self.roles

saver = state.Saver()

class AdminUserDB:
  BY_USERNAME = {}
  SAVER = saver

  @saver
  def add_user(self, now, username, password_hash, fullname, roles):
    r = set(roles)
    r.add("admin")
    user = AdminUser(username, password_hash.encode("ascii"), fullname, r)
    self.BY_USERNAME[username] = user
    return user

  def add_temp_user(self, username, password_hash, fullname, roles):
    r = set(roles)
    r.add("admin")
    user = AdminUser(username, password_hash.encode("ascii"), fullname, r)
    self.BY_USERNAME[username] = user
    return user

  @staticmethod
  def make_hash(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

  @classmethod
  def GetUser(self, username):
    return self.BY_USERNAME.get(username)




class Session:
  BY_KEY = {}
  SESSION_TIMEOUT = 3600   # seconds
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
  def initialize(self, admin_user_db=None):
    self.admin_user_db = admin_user_db

  def post(self):
    # Find the browser's existing session or create a new one.
    session = Session.from_request(self)
    if not session:
      session = Session(None)
      session.set_cookie(self)

    username = self.get_argument("username")
    password = self.get_argument("password")
    user = self.admin_user_db.GetUser(username)
    if user and user.CheckPassword(password):
      session.user = user
      session.capabilities = user.roles
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


def GetHandlers(admin_user_db):
  return [
    (r"/login", Login),
    (r"/login_submit", LoginSubmit, dict(admin_user_db=admin_user_db)),
    (r"/no_access", NoAccess),
    (r"/logout", Logout),
  ]

