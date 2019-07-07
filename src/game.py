import configparser
import heapq
import html
import json
import os
import re
import time
import unicodedata

import bs4

import login
from state import save_state

class PuzzleState:
  CLOSED = "closed"
  OPEN = "open"
  SOLVED = "solved"

  def __init__(self, team, puzzle):
    self.team = team
    self.puzzle = puzzle
    self.state = self.CLOSED
    self.submissions = []
    self.open_time = None
    self.solve_time = None
    self.answers_found = set()


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

    self.schedule_check()

  def __lt__(self, other):
    return self.submit_id < other.submit_id

  def schedule_check(self):
    self.check_time = self.compute_check_time()
    if self.check_time <= self.submit_time:
      self.check_answer(self.submit_time)
    else:
      heapq.heappush(self.GLOBAL_SUBMIT_QUEUE, (self.check_time, self))

  def compute_check_time(self):
    count = sum(1 for i in self.puzzle_state.submissions
                if i.state in (self.PENDING, self.INCORRECT))
    return self.puzzle_state.open_time + count * 60

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
    self.team.send_message({"method": "history_change", "puzzle_id": self.puzzle.shortname})
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
  def process_pending_submits(cls):
    now = time.time()
    q = cls.GLOBAL_SUBMIT_QUEUE
    while q and q[0][0] <= now:
      ct, sub = heapq.heappop(q)
      if sub.state != cls.PENDING: continue
      # It's possible for sub's check_time to have changed.  If it's
      # doesn't match the queue time, just drop this event.
      if sub.check_time == ct:
        sub.check_answer(ct)


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

    self.event_start = None

    # Create a PuzzleState object for all puzzles that exist.
    self.puzzle_state = {}
    for puzzle in Puzzle.all_puzzles():
      self.puzzle_state[puzzle] = PuzzleState(self, puzzle)

    self.open_lands = set()
    self.activity_log = []

  def attach_session(self, session):
    self.active_sessions.add(session)
  def detach_session(self, session):
    self.active_sessions.remove(session)

  def send_message(self, msg):
    msg = json.dumps(msg)
    for s in self.active_sessions:
      s.send_message(msg)

  # This method is exported into the file that's used to create all
  # the teams.
  @classmethod
  def add_team(cls, username, password, team_name, location):
    if username not in cls.BY_USERNAME:
      print(f"  Adding team {username} \"{team_name}\"")
      t = Team(username, login.make_hash(password), team_name, location)

  @save_state
  def start_event(self, now):
    self.event_start = now
    self.compute_puzzle_beam(now)

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
      return False

    state = self.puzzle_state[puzzle]
    if state.state != state.OPEN:
      print(f"puzzle {shortname} {state.state} for {self.username}")
      return False

    pending = sum(1 for s in state.submissions if s.state == s.PENDING)
    if pending >= state.puzzle.max_queued:
      print(f"puzzle {shortname} max pending for {self.username}")
      return False

    state.submissions.append(Submission(now, submit_id, self, puzzle, answer))
    self.send_message({"method": "history_change", "puzzle_id": shortname})
    return True

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
          if sub.state == sub.PENDING:
            sub.schedule_check()
          state.submissions.append(sub)
        break
    else:
      print(f"failed to cancel submit {submit_id} puzzle {shortname} for {self.username}")
      return

    self.send_message({"method": "history_change", "puzzle_id": shortname})

  def open_puzzle(self, puzzle, now):
    state = self.puzzle_state[puzzle]
    if state.state == state.CLOSED:
      state.state = state.OPEN
      state.open_time = now
      self.activity_log.append((now, f'<a href="{puzzle.url}">{html.escape(puzzle.title)}</a> opened.'))

  def solve_puzzle(self, puzzle, now):
    state = self.puzzle_state[puzzle]
    if state.state != state.SOLVED:
      state.state = state.SOLVED
      state.solve_time = now
      self.send_message({"method": "solve", "title": html.escape(puzzle.title)})
      self.activity_log.append((now, f'<a href="{puzzle.url}">{html.escape(puzzle.title)}</a> solved.'))
      self.compute_puzzle_beam(now)

  def get_puzzle_state(self, puzzle):
    if isinstance(puzzle, str):
      puzzle = Puzzle.get_by_shortname(puzzle)
      if not puzzle: return None
    return self.puzzle_state[puzzle]

  def compute_puzzle_beam(self, now):
    self.open_puzzle(Puzzle.get_by_shortname("sample"), now)
    if self.puzzle_state[Puzzle.get_by_shortname("sample")].state == PuzzleState.SOLVED:
      for n in ("sample_multi", "seven_dials", "capital_letters"):
        p = Puzzle.get_by_shortname(n)
        self.open_puzzle(p, now)

    if self.puzzle_state[Puzzle.get_by_shortname("sample_multi")].state == PuzzleState.SOLVED:
      for n in ("fab_four",):
        p = Puzzle.get_by_shortname(n)
        self.open_puzzle(p, now)

    if self.puzzle_state[Puzzle.get_by_shortname("fab_four")].state == PuzzleState.SOLVED:
      for n in ("flags",):
        p = Puzzle.get_by_shortname(n)
        self.open_puzzle(p, now)

    if self.puzzle_state[Puzzle.get_by_shortname("flags")].state == PuzzleState.SOLVED:
      for n in ("lazy",):
        p = Puzzle.get_by_shortname(n)
        self.open_puzzle(p, now)

    if self.puzzle_state[Puzzle.get_by_shortname("lazy")].state == PuzzleState.SOLVED:
      for n in ("bobby_tables",):
        p = Puzzle.get_by_shortname(n)
        self.open_puzzle(p, now)

    for st in self.puzzle_state.values():
      if st.state != PuzzleState.CLOSED:
        if st.puzzle.land not in self.open_lands:
          if st.puzzle.land.shortname != "mainstreet":
            self.send_message({"method": "open", "title": html.escape(st.puzzle.land.name)})
          self.open_lands.add(st.puzzle.land)

class Icon:
  def __init__(self, name, land, d):
    self.name = name
    self.land = land
    self.pos = tuple(d["pos"])
    self.size = tuple(d["size"])
    self.poly = d.get("poly", None)

    self.images = {
      "locked": f"/assets/land/{land.shortname}/{name}_locked.png",
      "unlocked": f"/assets/land/{land.shortname}/{name}_unlocked.png",
      "solved": f"/assets/land/{land.shortname}/{name}_solved.png",
      }

class Land:
  BY_SHORTNAME = {}

  def __init__(self, shortname, cfg):
    self.BY_SHORTNAME[shortname] = self
    self.shortname = shortname
    self.name = cfg["name"]
    self.pos = tuple(cfg["pos"])
    self.size = tuple(cfg["size"])
    self.poly = cfg["poly"]

    self.locked_image = f"/assets/map/{shortname}_locked.png"
    self.unlocked_image = f"/assets/map/{shortname}_unlocked.png"
    self.url = "/land/" + shortname
    self.base_image = "/assets/land/" + shortname + "/land_base.png"

    self.icons = {}
    for n, d in cfg.get("icons", {}).items():
      self.icons[n] = Icon(n, self, d)

    self.puzzles = []

class Puzzle:
  BY_SHORTNAME = {}

  DEFAULT_MAX_QUEUED = 3

  def __init__(self, path, initial_open):
    shortname = os.path.basename(path)
    if not re.match(r"^[a-z][a-z0-9_]*$", shortname):
      raise ValueError(f"\"{shortname}\" is not a legal puzzle shortname")
    if shortname in self.BY_SHORTNAME:
      raise ValueError(f"duplicate puzzle shortname \"{shortname}\"")

    print(f"  Adding puzzle {shortname}")
    self.BY_SHORTNAME[shortname] = self

    c = configparser.ConfigParser()
    c.read(os.path.join(path, "metadata.cfg"))

    p = c["PUZZLE"]
    assert shortname == p["shortname"]

    self.initial_open = initial_open
    self.shortname = shortname
    self.title = p["title"]
    self.oncall = p["oncall"]
    self.puzzletron_id = int(p["puzzletron_id"])
    self.version = int(p["version"])
    self.url = "/puzzle/" + shortname + "/"

    self.land = Land.BY_SHORTNAME[p["land"]]
    self.land.puzzles.append(self)

    if "icon" in p:
      self.icon = self.land.icons[p["icon"]]
    else:
      self.icon = None

    self.max_queued = p.get("max_queued", self.DEFAULT_MAX_QUEUED)

    self.answers = set(self.canonicalize_answer(a) for a in c["ANSWER"].values())

    if "INCORRECT_RESPONSES" in c:
      self.incorrect_responses = dict(
        (self.canonicalize_answer(k), self.respace_text(v))
        for (k, v) in c["INCORRECT_RESPONSES"].items())
    else:
      self.incorrect_responses = {}

    self.load_html(path)

  def load_html(self, path):
    with open(os.path.join(path, "puzzle.html")) as f:
      soup = bs4.BeautifulSoup(f, features="lxml")
      if soup.head:
        self.html_head = "".join(str(i) for i in soup.head.contents)
      else:
        self.html_head = None
      self.html_body = "".join(str(i) for i in soup.body.contents)

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
    return " ".join(text.split()).strip()









