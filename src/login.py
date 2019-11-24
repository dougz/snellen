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
  EDIT_PUZZLES = "edit_puzzles"

  ROLES = [CREATE_USERS, CONTROL_EVENT, EDIT_PUZZLES]


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
  pending_updates = {}

  @save_state
  def __init__(self, now, username, password_hash, fullname, roles):
    self.username = username.lower()
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

  @save_state
  def update_pwhash(self, now, pwhash):
    self.password_hash = pwhash.encode("ascii")

  @classmethod
  def all_users(cls):
    return cls.BY_USERNAME.values()

  @classmethod
  def notify_update(cls, team, puzzle=None, flush=False):
    cls.pending_updates.setdefault(team, set()).add(puzzle)
    if flush:
      asyncio.create_task(cls.flush_messages())

  @classmethod
  def send_messages(cls, objs, flush=False):
    cls.pending_messages.extend(objs)
    if flush:
      asyncio.create_task(cls.flush_messages())

  @classmethod
  async def flush_messages(cls):
    if not cls.pending_messages and not cls.pending_updates: return
    objs, cls.pending_messages = cls.pending_messages, []
    for t, pp in cls.pending_updates.items():
      if len(pp) > 1: pp.discard(None)
      for p in pp:
        d = {"method": "update", "team_username": t.username}
        if p:
          d["puzzle_id"] = p.shortname
        objs.append(d)
    cls.pending_updates = {}
    if isinstance(objs, list):
      strs = [json.dumps(o) for o in objs]
    async with cls.message_mu:
      await wait_proxy.Server.send_message("__ADMIN", cls.message_serial, strs)
      cls.message_serial += len(strs)




class Session:
  BY_KEY = {}
  SESSION_TIMEOUT = 3600   # seconds
  ADMIN_COOKIE_NAME = "ADMINSESSION"
  PLAYER_COOKIE_NAME = "SESSION"

  VARZ = {
    }

  def __init__(self, cookie_name, *caps):
    self.cookie_name = cookie_name
    self.key = base64.urlsafe_b64encode(os.urandom(18))
    self.BY_KEY[self.key] = self
    self.user = None
    self.pending_become = None
    self.team = None
    self.capabilities = set(caps)
    self.expires = int(time.time()) + self.SESSION_TIMEOUT
    self.pages_visited = set()

    self.next_msg_serial = 1
    self.msg_cv = asyncio.Condition()

  def set_cookie(self, req, domain):
    req.set_secure_cookie(self.cookie_name, self.key, domain=domain)

  def visit_page(self, page):
    self.pages_visited.add(page)
    if self.team and self.pages_visited == {
        "pins", "activity", "health_safety", "guest_services",
        "videos", "events", "all_puzzles"}:
      self.team.achieve_now(game.Achievement.digital_explorer, delay=1.5)

  @classmethod
  def from_request(cls, req, cookie_name):
    key = req.get_secure_cookie(cookie_name)
    if not key: return None
    return cls.BY_KEY.get(key)

  @classmethod
  def from_key(cls, key):
    x = cls.BY_KEY.get(key)
    return x

  @classmethod
  def delete_from_request(cls, req, cookie_name):
    key = req.get_secure_cookie(cookie_name)
    if key:
      req.clear_cookie(cookie_name)
      session = cls.BY_KEY.pop(key, None)
      if session:
        if session.team: session.team.detach_session(session)


# A decorator that can be applied to a request handler's get() or
# post() methods to require the request come while logged in with an
# account with a given capability.  The browser is redirected to the
# login or access-denied page as appropriate.
class required:
  def __init__(self, cap=None, on_fail=None, require_start=True, clear_become=True):
    self.cap = cap
    self.on_fail = on_fail
    self.require_start = require_start
    self.clear_become = clear_become

  def bounce(self, req):
    if self.on_fail is not None:
      raise tornado.web.HTTPError(self.on_fail)
    if req.request.uri == "/":
      req.redirect("/login")
    else:
      req.redirect("/login?" + urllib.parse.urlencode({"redirect_to": req.request.uri}))

  def __call__(self, func):
    @functools.wraps(func)
    def wrapped_func(req, *args, **kwargs):
      cookie_name = Session.PLAYER_COOKIE_NAME if self.cap == "team" else Session.ADMIN_COOKIE_NAME
      session = Session.from_request(req, cookie_name)
      if not session:
        return self.bounce(req)
      now = time.time()
      if now > session.expires:
        print(f"session {session.key} has expired")
        Session.delete_from_request(req, cookie_name)
        return self.bounce(req)
      if self.clear_become: session.pending_become = None
      if self.cap and self.cap not in session.capabilities:
        if AdminRoles.ADMIN in session.capabilities:
          req.redirect("/no_access")
          return
        else:
          # If teams try to access an admin page, return 404.
          raise tornado.web.HTTPError(http.client.NOT_FOUND)

      if self.cap == "team" and self.require_start and not game.Global.STATE.event_start_time:
        req.redirect("/")
        return

      session.expires = int(now) + session.SESSION_TIMEOUT
      req.session = session
      req.user = session.user
      req.team = session.team
      return func(req, *args, **kwargs)
    return wrapped_func


class Login(tornado.web.RequestHandler):
  @classmethod
  def set_static_content(cls, static_content):
    cls.static_content = static_content

  def get(self):
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
                target=target,
                c=self.static_content["login.css"],
                logo=self.static_content["logo.png"])


class LoginSubmit(tornado.web.RequestHandler):
  async def post(self):
    username = self.get_argument("username", None)
    password = self.get_argument("password", None)
    target = self.get_argument("target", None)

    domain = self.request.headers.get("host", None)
    if not domain:
      print(f"Missing host header")
      domain = "pennypark.fun"

    if username: username = username.lower()

    err_d = {"bad_login": 1}
    if target:
      err_d["redirect_to"] = target

    team = game.Team.get_by_username(username)
    if team:
      allowed = await team.check_password(password)
      if allowed:
        session = Session(Session.PLAYER_COOKIE_NAME)
        session.set_cookie(self, domain)

        session.team = team
        session.capabilities = {"team"}
        session.was_admin = False
        team.attach_session(session)
        self.redirect(target or "/")
        return
    else:
      user = AdminUser.get_by_username(username)
      if user:
        allowed = await user.check_password(password)
        if allowed:
          session = Session(Session.ADMIN_COOKIE_NAME)
          session.set_cookie(self, domain)

          session.user = user
          session.capabilities = user.roles
          session.was_admin = True
          self.redirect(target or "/admin")
          return

    self.redirect("/login?" + urllib.parse.urlencode(err_d))


class Logout(tornado.web.RequestHandler):
  def get(self, admin):
    cookie_name = Session.ADMIN_COOKIE_NAME if admin else Session.PLAYER_COOKIE_NAME
    session = Session.from_request(self, cookie_name)
    if (session and session.team and
        game.Global.STATE.event_start_time and
        not session.was_admin):
      session.team.achieve_now(game.Achievement.come_back, delay=1.0)

    # Uncookie the browser, delete the session, send them back to the
    # login page.
    Session.delete_from_request(self, cookie_name)
    self.redirect("/login")


class NoAccess(tornado.web.RequestHandler):
  def get(self):
    self.render("no_access.html")


def GetHandlers():
  return [
    (r"/login", Login),
    (r"/login_submit", LoginSubmit),
    (r"/no_access", NoAccess),
    (r"/(admin/)?logout", Logout),
  ]

