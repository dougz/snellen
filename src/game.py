import asyncio
import heapq
import html
import json
import os
import re
import time
import unicodedata

import login
from state import save_state
import wait_proxy

class PuzzleState:
  CLOSED = "closed"
  OPEN = "open"
  SOLVED = "solved"

  RECENT_TIME = 10.0  # seconds

  def __init__(self, team, puzzle):
    self.team = team
    self.puzzle = puzzle
    self.state = self.CLOSED
    self.submissions = []
    self.open_time = None
    self.solve_time = None
    self.answers_found = set()

  def recent_solve(self, now=None):
    if now is None:
      now = time.time()
    return (self.state == PuzzleState.SOLVED and
            0 <= now - self.solve_time <= PuzzleState.RECENT_TIME)


class Submission:
  PENDING = "pending"
  PARTIAL = "partial"
  INCORRECT = "incorrect"
  CORRECT = "correct"
  MOOT = "moot"
  CANCELLED = "cancelled"

  GLOBAL_SUBMIT_QUEUE = []

  def __init__(self, now, submit_id, team, puzzle, answer):
    self.state = self.PENDING
    self.submit_id = submit_id
    self.team = team
    self.puzzle = puzzle
    self.puzzle_state = team.get_puzzle_state(puzzle)
    self.answer = answer
    self.submit_time = now
    self.extra_response = None

  def __lt__(self, other):
    return self.submit_id < other.submit_id

  def check_or_queue(self):
    self.check_time = self.compute_check_time()
    if self.check_time <= self.submit_time:
      self.check_answer(self.submit_time)
    else:
      heapq.heappush(self.GLOBAL_SUBMIT_QUEUE, (self.check_time, self))

  def compute_check_time(self):
    # Note that self is already in the submissions list (at the end)
    # when this is called.
    count = sum(1 for i in self.puzzle_state.submissions
                if i.state in (self.PENDING, self.INCORRECT))
    return self.puzzle_state.open_time + (count-1) * 30

  def check_answer(self, now):
    answer = Puzzle.canonicalize_answer(self.answer)
    if answer in self.puzzle.answers:
      self.state = self.CORRECT
      self.extra_response = None
    elif answer in self.puzzle.incorrect_responses:
      self.state = self.PARTIAL
      self.extra_response = (
        self.puzzle.incorrect_responses[answer] or "Keep going\u2026")
    else:
      self.state = self.INCORRECT
    if self.state == self.CORRECT:
      self.puzzle_state.answers_found.add(answer)
      if self.puzzle_state.answers_found == self.puzzle.answers:
        self.team.solve_puzzle(self.puzzle, now)

  def json_dict(self):
    return {"submit_time": self.submit_time,
            "answer": self.answer,
            "check_time": self.check_time,
            "state": self.state,
            "response": self.extra_response,
            "submit_id": self.submit_id}

  @classmethod
  async def realtime_process_submit_queue(cls):
    while True:
      teams = cls.process_submit_queue(time.time())
      for team in teams:
        asyncio.create_task(team.flush_messages())
      await asyncio.sleep(1.0)

  @classmethod
  def process_submit_queue(cls, now):
    """Processes the global submit queue up through time 'now'.  Returns a
    set of teams it sent messages to."""
    teams = set()
    q = cls.GLOBAL_SUBMIT_QUEUE
    while q and q[0][0] <= now:
      ct, sub = heapq.heappop(q)
      if sub.state != cls.PENDING: continue
      # It's possible for sub's check_time to have changed.  If it's
      # doesn't match the queue time, just drop this event.
      if sub.check_time == ct:
        msgs = sub.check_answer(ct)
        sub.team.send_messages([{"method": "history_change", "puzzle_id": sub.puzzle.shortname}])
        teams.add(sub.team)
    return teams



class Team(login.LoginUser):
  BY_USERNAME = {}

  NEXT_SUBMIT_ID = 1

  @save_state
  def __init__(self,
               now,
               username,
               password_hash,
               team_name,
               location):
    assert username not in self.BY_USERNAME
    self.BY_USERNAME[username] = self

    self.active_sessions = set()

    self.username = username
    self.password_hash = password_hash.encode("ascii")
    self.team_name = team_name
    self.location = location

    # Create a PuzzleState object for all puzzles that exist.
    self.puzzle_state = {}
    for puzzle in Puzzle.all_puzzles():
      self.puzzle_state[puzzle] = PuzzleState(self, puzzle)

    self.open_lands = {}
    self.activity_log = []

    self.message_mu = asyncio.Lock()
    self.message_serial = 1
    self.pending_messages = []

    self.achievements = {}

  def __repr__(self):
    return f"<Team {self.username}>"
  __str__ = __repr__

  def attach_session(self, session):
    self.active_sessions.add(session)
  def detach_session(self, session):
    self.active_sessions.remove(session)

  def send_messages(self, objs):
    """Send a list of messages to all browsers for this team."""
    self.pending_messages.extend(objs)

  async def flush_messages(self):
    """Flush the pending message queue, actually sending them to the team."""
    if not self.pending_messages: return
    objs, self.pending_messages = self.pending_messages, []
    if isinstance(objs, list):
      strs = [json.dumps(o) for o in objs]
    async with self.message_mu:
      await wait_proxy.Server.send_message(self, self.message_serial, strs)
      self.message_serial += len(strs)

  def discard_messages(self):
    self.pending_messages = []

  def achieve(self, ach):
    if ach not in self.achievements:
      self.record_achievement(ach.name)

  def delayed_achieve(self, ach, delay=1.0):
    """Like achieve(), but delayed slightly.  Useful for achievements
    triggered by page load, so the loaded page gets the
    notification."""
    async def future():
      await asyncio.sleep(delay)
      self.achieve(ach)
      await self.flush_messages()
    asyncio.create_task(future())

  @save_state
  def record_achievement(self, now, aname):
    ach = Achievement.by_name(aname)
    self.achievements[ach] = now
    self.activity_log.append((now, f'Received the <b>{html.escape(ach.title)}</b> pin.'))
    self.send_messages([{"method": "achieve", "title": ach.title}])

  # This method is exported into the file that's used to create all
  # the teams.
  @classmethod
  def add_team(cls, username, password, team_name, location):
    if username not in cls.BY_USERNAME:
      print(f"  Adding team {username} \"{team_name}\"")
      t = Team(username, login.make_hash(password), team_name, location)

  @classmethod
  def get_by_username(cls, username):
    return cls.BY_USERNAME.get(username)

  @classmethod
  def next_submit_id(cls):
    cls.NEXT_SUBMIT_ID += 1
    return cls.NEXT_SUBMIT_ID - 1

  @save_state
  def submit_answer(self, now, submit_id, shortname, answer):
    self.NEXT_SUBMIT_ID = max(self.NEXT_SUBMIT_ID, submit_id+1)

    puzzle = Puzzle.get_by_shortname(shortname)
    if not puzzle:
      print(f"no puzzle {shortname}")
      return

    state = self.puzzle_state[puzzle]
    if state.state != state.OPEN:
      print(f"puzzle {shortname} {state.state} for {self.username}")
      return

    pending = sum(1 for s in state.submissions if s.state == s.PENDING)
    if pending >= state.puzzle.max_queued:
      print(f"puzzle {shortname} max pending for {self.username}")
      return

    sub = Submission(now, submit_id, self, puzzle, answer)
    state.submissions.append(sub)
    self.send_messages([{"method": "history_change", "puzzle_id": shortname}])
    sub.check_or_queue()

  @save_state
  def cancel_submission(self, now, submit_id, shortname):
    puzzle = Puzzle.get_by_shortname(shortname)
    if not puzzle:
      print(f"no puzzle {shortname}")
      return False

    state = self.puzzle_state[puzzle]
    if state.state != state.OPEN:
      print(f"puzzle {shortname} {state.state} for {self.username}")
      return False

    for i, sub in enumerate(state.submissions):
      if sub.submit_id == submit_id and sub.state == sub.PENDING:
        after = state.submissions[i+1:]
        sub.state = sub.CANCELLED
        del state.submissions[i:]

        for sub in after:
          state.submissions.append(sub)
          if sub.state == sub.PENDING:
            sub.check_or_queue()
        break
    else:
      print(f"failed to cancel submit {submit_id} puzzle {shortname} for {self.username}")
      return

  def open_puzzle(self, puzzle, now):
    state = self.puzzle_state[puzzle]
    if state.state == state.CLOSED:
      state.state = state.OPEN
      state.open_time = now
      self.activity_log.append((now, f'<a href="{puzzle.url}">{html.escape(puzzle.title)}</a> opened.'))

  def solve_puzzle(self, puzzle, now):
    state = self.puzzle_state[puzzle]
    msgs = []
    if state.state != state.SOLVED:
      state.state = state.SOLVED
      state.solve_time = now
      for sub in state.submissions:
        if sub.state == sub.PENDING:
          sub.state = sub.MOOT
      self.send_messages(
        [{"method": "solve",
          "title": html.escape(puzzle.title),
          "audio": "https://snellen.storage.googleapis.com/applause.mp3"}])
      self.activity_log.append((now, f'<a href="{puzzle.url}">{html.escape(puzzle.title)}</a> solved.'))
      self.achieve(Achievement.solve_puzzle)
      self.compute_puzzle_beam(now)

  def get_puzzle_state(self, puzzle):
    if isinstance(puzzle, str):
      puzzle = Puzzle.get_by_shortname(puzzle)
      if not puzzle: return None
    return self.puzzle_state[puzzle]

  def compute_puzzle_beam(self, now):
    # Always have two open puzzles in each land.
    for land in Land.BY_SHORTNAME.values():
      if not land.puzzles: continue
      open_count = 0
      locked = []
      for p in land.puzzles:
        if self.puzzle_state[p].state == PuzzleState.OPEN:
          open_count += 1
        elif self.puzzle_state[p].state == PuzzleState.CLOSED:
          locked.append(p)
      while open_count < 2 and locked:
        self.open_puzzle(locked.pop(0), now)
        open_count += 1

    for st in self.puzzle_state.values():
      if st.state != PuzzleState.CLOSED:
        if st.puzzle.land not in self.open_lands:
          if st.puzzle.land.shortname != "mainstreet":
            self.send_messages([{"method": "open", "title": html.escape(st.puzzle.land.title)}])
          self.open_lands[st.puzzle.land] = now

class Icon:
  def __init__(self, name, land, d):
    self.name = name
    self.land = land
    self.pos = tuple(d["pos"])
    self.size = tuple(d["size"])
    self.poly = d.get("poly", None)
    self.puzzle = None
    self.to_land = None
    self.thumb_size = d.get("thumb_size", self.size)

    self.images = {
      "locked": d.get("locked", None),
      "unlocked": d.get("unlocked", None),
      "solved": d.get("solved", None),
      "unlocked_thumb": d.get("unlocked_thumb", d.get("unlocked")),
      "solved_thumb": d.get("solved_thumb", d.get("solved")),
      }


class Land:
  BY_SHORTNAME = {}

  def __init__(self, shortname, cfg, event_dir):
    print(f"  Adding land \"{shortname}\"...")

    self.BY_SHORTNAME[shortname] = self
    self.shortname = shortname
    self.title = cfg["title"]

    self.base_img = cfg["base_img"]
    self.base_size = cfg["base_size"]

    if shortname == "inner_only":
      self.url = "/"
    else:
      self.url = "/land/" + shortname

    self.puzzles = []

    self.icons = {}
    for d in cfg.get("icons", ()):
      name = d["name"]
      i = Icon(name, self, d)
      self.icons[name] = i
      if "puzzle" in d:
        p = d["puzzle"]
        if p == "_":
          p = Puzzle.filler_puzzle()
        else:
          p = Puzzle.from_json(os.path.join(event_dir, "puzzles", p + ".json"))
        p.land = self
        p.icon = i
        self.puzzles.append(p)
        i.puzzle = p

  def __repr__(self):
    return f"<Land \"{self.title}\">"

  @classmethod
  def resolve_lands(cls):
    for land in cls.BY_SHORTNAME.values():
      for i in land.icons.values():
        if not i.puzzle:
          i.to_land = cls.BY_SHORTNAME[i.name]



class Puzzle:
  BY_SHORTNAME = {}

  DEFAULT_MAX_QUEUED = 3

  FILLER_COUNT = 0

  def __init__(self, shortname):
    if not re.match(r"^[a-z][a-z0-9_]*$", shortname):
      raise ValueError(f"\"{shortname}\" is not a legal puzzle shortname")
    if shortname in self.BY_SHORTNAME:
      raise ValueError(f"duplicate puzzle shortname \"{shortname}\"")

    print(f"    Adding puzzle \"{shortname}\"...")
    self.BY_SHORTNAME[shortname] = self
    self.shortname = shortname
    self.url = "/puzzle/" + shortname

  @classmethod
  def filler_puzzle(cls):
    cls.FILLER_COUNT += 1
    number = cls.FILLER_COUNT

    shortname = f"filler_{number}"
    self = cls(shortname)

    self.title = f"Filler #{number}"
    self.oncall = "nobody@example.org"
    self.puzzletron_id = -1
    self.version = 0

    self.max_queued = self.DEFAULT_MAX_QUEUED
    self.answers = {"FILLER"}
    self.display_answers = {"FILLER": "FILLER"}
    self.incorrect_responses = {}

    self.html_head = None
    self.html_body = "<p>The answer to this filler puzzle is <b>FILLER</b>.</p>"

    return self

  @classmethod
  def from_json(cls, path):
    shortname = os.path.splitext(os.path.basename(path))[0]
    with open(path) as f:
      j = json.load(f)

    assert shortname == j["shortname"]
    self = cls(shortname)

    self.title = j["title"]
    self.oncall = j["oncall"]
    self.puzzletron_id = j["puzzletron_id"]
    self.max_queued = j.get("max_queued", self.DEFAULT_MAX_QUEUED)

    self.answers = set()
    self.display_answers = {}
    for a in j["answers"]:
      disp = a.upper().strip()
      a = self.canonicalize_answer(a)
      self.display_answers[a] = disp
      self.answers.add(a)

    self.incorrect_responses = dict(
        (self.canonicalize_answer(k), self.respace_text(v))
        for (k, v) in j["incorrect_responses"].items())

    self.html_head = j.get("html_head")
    self.html_body = j["html_body"]

    return self


  @classmethod
  def get_by_shortname(cls, shortname):
    return cls.BY_SHORTNAME.get(shortname)

  @classmethod
  def all_puzzles(cls):
    return cls.BY_SHORTNAME.values()

  @staticmethod
  def canonicalize_answer(text):
    text = unicodedata.normalize("NFD", text.upper())
    out = []
    for k in text:
      cat = unicodedata.category(k)
      # Letters and "other symbols".
      if cat == "So" or cat[0] == "L":
        out.append(k)
    return "".join(out)

  @staticmethod
  def respace_text(text):
    if text is None: return None
    return " ".join(text.split()).strip()


class Global:
  STATE = None

  @save_state
  def __init__(self, now):
    self.event_start_time = None
    Global.STATE = self

  def set_static_dir(self, static_dir):
    self.static_dir = static_dir
    Achievement.define_achievements(static_dir)

  @save_state
  def start_event(self, now):
    if self.event_start_time: return

    self.event_start_time = now
    for team in Team.BY_USERNAME.values():
      team.compute_puzzle_beam(now)

    # TODO trigger team reload


class Achievement:
  ALL = []
  BY_NAME = {}

  def __init__(self, name, title, subtitle):
    self.name = name
    self.title = title
    self.subtitle = subtitle
    self.yes_url = Achievement.static_dir[name + "_yes.png"]
    self.no_url = Achievement.static_dir[name + "_no.png"]
    setattr(Achievement, name, self)
    Achievement.BY_NAME[name] = self
    Achievement.ALL.append(self)

  @classmethod
  def by_name(cls, aname):
    return cls.BY_NAME[aname]

  @classmethod
  def define_achievements(cls, static_dir):
    cls.static_dir = static_dir

    Achievement("solve_puzzle",
                "That's how this works",
                "Solve a puzzle.")

    Achievement("log_out",
                "Come back!",
                "Log out of the hunt server before the coin is found.")

    Achievement("visit_log",
                "Reminisce",
                "Visit the Activity Log page during the hunt.")
