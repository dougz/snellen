import asyncio
import base64
import bcrypt
import functools
import http.client
import json
import os
import time
from collections import deque

import tornado.web

import game
from state import save_state

def make_hash(password):
  return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

class AdminRoles:
  ADMIN = "admin"
  CREATE_USERS = "create_users"
  CONTROL_EVENT = "control_event"

  ROLES = [CREATE_USERS, CONTROL_EVENT]


class LoginUser:
  def check_password(self, password):
    if bcrypt.checkpw(password.encode("utf-8"), self.password_hash):
      return True
    return False


class AdminUser(LoginUser):
  BY_USERNAME = {}

  @save_state
  def __init__(self, now, username, password_hash, fullname, roles):
    self.username = username
    self.password_hash = password_hash.encode("ascii")
    self.fullname = fullname
    self.roles = set(roles)
    self.roles.add(AdminRoles.ADMIN)
    self.BY_USERNAME[username] = self

  @classmethod
  def get_by_username(cls, username):
    return cls.BY_USERNAME.get(username)

  @classmethod
  def enable_root(cls, password_hash):
    obj = AdminUser.__new__(AdminUser)
    obj.username = "root"
    obj.password_hash = password_hash.encode("ascii")
    obj.fullname = "Root"
    obj.roles = set((AdminRoles.ADMIN, AdminRoles.CREATE_USERS))
    cls.BY_USERNAME["root"] = obj

  def has_role(self, role):
    return role in self.roles

  @save_state
  def update_role(self, now, role, wanted):
    if wanted:
      self.roles.add(role)
    else:
      self.roles.discard(role)

  @classmethod
  def all_users(cls):
    return cls.BY_USERNAME.values()


class Session:
  BY_KEY = {}
  SESSION_TIMEOUT = 3600   # seconds
  COOKIE_NAME = "SESSION"

  def __init__(self, user=None, *caps):
    self.key = base64.urlsafe_b64encode(os.urandom(18))
    self.BY_KEY[self.key] = self
    self.user = user
    self.team = None
    self.capabilities = set(caps)
    self.bad_login = False
    self.expires = time.time() + self.SESSION_TIMEOUT
    self.original_target = None

    self.wait_queue = deque()
    self.wait_serial = 1
    self.wait_event = asyncio.Event()

  def set_cookie(self, req):
    req.set_secure_cookie(self.COOKIE_NAME, self.key)

  def send_message(self, obj):
    if not isinstance(obj, str):
      obj = json.dumps(obj)
    self.wait_queue.append((self.wait_serial, obj))
    self.wait_serial += 1
    self.wait_event.set()

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
      session = cls.BY_KEY.pop(key, None)
      if session:
        if session.team: session.team.detach_session(session)


# A decorator that can be applied to a request handler's get() or
# post() methods to require the request come while logged in with an
# account with a given capability.  The browser is redirected to the
# login or access-denied page as appropriate.
class required:
  def __init__(self, cap=None, on_fail=None):
    self.cap = cap
    self.on_fail = on_fail

  def bounce(self, req):
    if self.on_fail is not None:
      raise tornado.web.HTTPError(self.on_fail)
    session = Session(None)
    session.set_cookie(req)
    session.original_target = req.request.uri
    req.redirect("/login")

  def __call__(self, func):
    @functools.wraps(func)
    def wrapped_func(req, *args, **kwargs):
      session = Session.from_request(req)
      if not session:
        return self.bounce(req)
      now = time.time()
      if now > session.expires:
        Session.delete_from_request(req)
        return self.bounce(req)
      if self.cap not in session.capabilities:
        if AdminRoles.ADMIN in session.capabilities:
          req.redirect("/no_access")
          return
        else:
          # If teams try to access an admin page, return 404.
          raise tornado.web.HTTPError(http.client.NOT_FOUND)
      session.expires = now + session.SESSION_TIMEOUT
      session.original_target = None
      req.session = session
      req.user = session.user
      req.team = session.team
      return func(req, *args, **kwargs)
    return wrapped_func


class Login(tornado.web.RequestHandler):
  def get(self):
    session = Session.from_request(self)
    self.render("login.html",
                bad_login=session and session.bad_login,
                default_username=self.application.settings["default_username"],
                default_password=self.application.settings["default_password"],
                )


class LoginSubmit(tornado.web.RequestHandler):
  def post(self):
    # Find the browser's existing session or create a new one.
    session = Session.from_request(self)
    if not session:
      session = Session(None)
      session.set_cookie(self)

    username = self.get_argument("username")
    password = self.get_argument("password")

    team = game.Team.get_by_username(username)
    if team:
      if team.check_password(password):
        session.team = team
        session.capabilities = {"team"}
        session.bad_login = False
        team.attach_session(session)
        self.redirect(session.original_target or "/")
      else:
        session.bad_login = True
        self.redirect("/login")
      return

    user = AdminUser.get_by_username(username)
    if user and user.check_password(password):
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


def GetHandlers():
  return [
    (r"/login", Login),
    (r"/login_submit", LoginSubmit),
    (r"/no_access", NoAccess),
    (r"/logout", Logout),
  ]

