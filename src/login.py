import asyncio
import base64
import bcrypt
import functools
import http.client
import json
import os
import time
import threading
import urllib.parse
from collections import deque

import tornado.web
import tornado.ioloop

import game
from state import save_state
import wait_proxy

def make_hash(password):
  return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

class AdminRoles:
  ADMIN = "admin"
  CREATE_USERS = "create_users"
  CONTROL_EVENT = "control_event"

  ROLES = [CREATE_USERS, CONTROL_EVENT]


class LoginUser:
  async def check_password(self, password):
    def check():
      if bcrypt.checkpw(password.encode("utf-8"), self.password_hash):
        return True
      return False
    return await asyncio.get_running_loop().run_in_executor(None, check)

  @classmethod
  async def hash_password(cls, password):
    return await asyncio.get_running_loop().run_in_executor(None, make_hash, password)


class AdminUser(LoginUser):
  BY_USERNAME = {}

  message_mu = asyncio.Lock()
  message_serial = 1
  pending_messages = []

  def __init__(self, username, password_hash, fullname, roles):
    self.username = username
    self.password_hash = password_hash.encode("ascii")
    self.fullname = fullname
    self.roles = set(roles)
    self.roles.add(AdminRoles.ADMIN)
    self.BY_USERNAME[username] = self

    save_state.add_instance("AdminUser:" + username, self)

  @classmethod
  def create_new_user(cls, username, password_hash, fullname):
    cls(username, password_hash, fullname, ())

  @classmethod
  def get_by_username(cls, username):
    return cls.BY_USERNAME.get(username)

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

  @classmethod
  def send_messages(cls, objs):
    cls.pending_messages.extend(objs)

  @classmethod
  async def flush_messages(cls):
    if not cls.pending_messages: return
    objs, cls.pending_messages = cls.pending_messages, []
    if isinstance(objs, list):
      strs = [json.dumps(o) for o in objs]
    async with cls.message_mu:
      await wait_proxy.Server.send_message("__ADMIN", cls.message_serial, strs)
      cls.message_serial += len(strs)




class Session:
  BY_KEY = {}
  SESSION_TIMEOUT = 3600   # seconds
  COOKIE_NAME = "SESSION"

  VARZ = {
    }

  def __init__(self, user=None, *caps):
    self.key = base64.urlsafe_b64encode(os.urandom(18))
    self.BY_KEY[self.key] = self
    self.user = user
    self.team = None
    self.capabilities = set(caps)
    self.expires = time.time() + self.SESSION_TIMEOUT

    self.next_msg_serial = 1
    self.msg_cv = asyncio.Condition()

  def set_cookie(self, req):
    req.set_secure_cookie(self.COOKIE_NAME, self.key)

  @classmethod
  def from_request(cls, req):
    key = req.get_secure_cookie(cls.COOKIE_NAME)
    if not key: return None
    return cls.BY_KEY.get(key)

  @classmethod
  def from_key(cls, key):
    x = cls.BY_KEY.get(key)
    return x

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
  def __init__(self, cap=None, on_fail=None, require_start=True):
    self.cap = cap
    self.on_fail = on_fail
    self.require_start = require_start

  def bounce(self, req):
    if self.on_fail is not None:
      raise tornado.web.HTTPError(self.on_fail)
    session = Session(None)
    session.set_cookie(req)
    if req.request.uri == "/":
      req.redirect("/login")
    else:
      req.redirect("/login?" + urllib.parse.urlencode({"redirect_to": req.request.uri}))

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

      if self.cap == "team" and self.require_start and not game.Global.STATE.event_start_time:
        req.redirect("/")
        return

      session.expires = now + session.SESSION_TIMEOUT
      req.session = session
      req.user = session.user
      req.team = session.team
      return func(req, *args, **kwargs)
    return wrapped_func


class Login(tornado.web.RequestHandler):
  def get(self):
    session = Session.from_request(self)
    target = self.get_argument("redirect_to", None)
    bad_login = self.get_argument("bad_login", None)

    options = self.application.settings["options"]
    if options.default_credentials:
      default_username, default_password = options.default_credentials.split(":", 1)
    else:
      default_username = None
      default_password = None

    self.render("login.html",
                bad_login=bad_login,
                default_username=default_username,
                default_password=default_password,
                target=target)


class LoginSubmit(tornado.web.RequestHandler):
  async def post(self):
    # Find the browser's existing session or create a new one.
    session = Session.from_request(self)
    if not session:
      session = Session(None)
      session.set_cookie(self)

    username = self.get_argument("username", None)
    password = self.get_argument("password", None)
    target = self.get_argument("target", None)

    err_d = {"bad_login": 1}
    if target:
      err_d["redirect_to"] = target

    team = game.Team.get_by_username(username)
    if team:
      allowed = await team.check_password(password)
      if allowed:
        session.team = team
        session.capabilities = {"team"}
        team.attach_session(session)
        self.redirect(target or "/")
      else:
        self.redirect("/login?" + urllib.parse.urlencode(err_d))
      return

    user = AdminUser.get_by_username(username)
    if user:
      allowed = await user.check_password(password)
      if allowed:
        session.user = user
        session.capabilities = user.roles
        self.redirect("/admin")
        return
    self.redirect("/login?" + urllib.parse.urlencode(err_d))


class Logout(tornado.web.RequestHandler):
  def get(self):
    session = Session.from_request(self)
    if session and session.team:
      session.team.achieve_now(game.Achievement.come_back, delay=1.0)

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

