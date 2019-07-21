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

  def __lt__(self, other):
    return self.submit_id < other.submit_id

  def check_or_queue(self):
    self.check_time = self.compute_check_time()
    if self.check_time <= self.submit_time:
      return self.check_answer(self.submit_time)
    else:
      heapq.heappush(self.GLOBAL_SUBMIT_QUEUE, (self.check_time, self))
      return []

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
        return self.team.solve_puzzle(self.puzzle, now)
    return []

  def json_dict(self):
    return {"submit_time": self.submit_time,
            "answer": self.answer,
            "check_time": self.check_time,
            "state": self.state,
            "response": self.extra_response,
            "submit_id": self.submit_id}

  @classmethod
  async def realtime_process_submit_queue(cls):
    messages = cls.process_submit_queue(time.time())
    for team, msgs in messages.items():
      await team.send_message(msgs)

  @classmethod
  def process_submit_queue(cls, now):
    """Processes the global submit queue up through time 'now'.  Returns a dict of {team: messages}."""
    messages = {}
    q = cls.GLOBAL_SUBMIT_QUEUE
    while q and q[0][0] <= now:
      ct, sub = heapq.heappop(q)
      if sub.state != cls.PENDING: continue
      # It's possible for sub's check_time to have changed.  If it's
      # doesn't match the queue time, just drop this event.
      if sub.check_time == ct:
        msgs = sub.check_answer(ct)
        msgs.append({"method": "history_change", "puzzle_id": sub.puzzle.shortname})

        if sub.team in messages:
          messages[sub.team].extend(msgs)
        else:
          messages[sub.team] = msgs
    return messages



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

    self.open_lands = {}
    self.activity_log = []

  def attach_session(self, session):
    self.active_sessions.add(session)
  def detach_session(self, session):
    self.active_sessions.remove(session)

  async def send_message(self, objs):
    """Send a message or list of messages to all sessions for this team."""
    if not objs: return
    if isinstance(objs, list):
      strs = [json.dumps(o) for o in objs]
    else:
      strs = [json.dumps(objs)]
    for s in self.active_sessions:
      await s.send_message_strings(strs)

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
    return sub.check_or_queue()

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
      msgs.append({"method": "solve",
                   "title": html.escape(puzzle.title),
                   "audio": "https://snellen.storage.googleapis.com/applause.mp3",
                   "frompage": puzzle.url,
                   "topage": puzzle.land.url})
      self.activity_log.append((now, f'<a href="{puzzle.url}">{html.escape(puzzle.title)}</a> solved.'))
      msgs.extend(self.compute_puzzle_beam(now))
    return msgs

  def get_puzzle_state(self, puzzle):
    if isinstance(puzzle, str):
      puzzle = Puzzle.get_by_shortname(puzzle)
      if not puzzle: return None
    return self.puzzle_state[puzzle]

  def compute_puzzle_beam(self, now):
    msgs = []

    # Always have two open puzzles in each land.
    for land in Land.BY_SHORTNAME.values():
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
            msgs.append({"method": "open", "title": html.escape(st.puzzle.land.name)})
          self.open_lands[st.puzzle.land] = now

    return msgs

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

  def __init__(self, shortname, cfg, event_dir):
    self.BY_SHORTNAME[shortname] = self
    self.shortname = shortname
    self.name = cfg["name"]
    self.pos = tuple(cfg["pos"])
    self.size = tuple(cfg["size"])
    self.poly = cfg["poly"]

    self.map_size = tuple(cfg["map_size"])

    print(f"  Adding land \"{shortname}\"...")

    self.locked_image = f"/assets/map/{shortname}_locked.png"
    self.unlocked_image = f"/assets/map/{shortname}_unlocked.png"
    self.url = "/land/" + shortname
    self.base_image = "/assets/land/" + shortname + "/land_base.png"

    self.puzzles = []

    self.icons = {}
    for d in cfg.get("icons", ()):
      name = d["name"]
      i = Icon(name, self, d)
      self.icons[name] = i
      p = d["puzzle"]
      if p == "_":
        p = Puzzle.filler_puzzle()
      else:
        p = Puzzle.from_json(os.path.join(event_dir, "puzzles", p + ".json"))
      p.land = self
      p.icon = i
      self.puzzles.append(p)


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
    self.url = "/puzzle/" + shortname + "/"

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
  def from_zip(cls, path):
    shortname = os.path.basename(path)
    self = cls(shortname)

    c = configparser.ConfigParser()
    c.read(os.path.join(path, "metadata.cfg"))

    p = c["PUZZLE"]
    assert shortname == p["shortname"]

    self.shortname = shortname
    self.title = p["title"]
    self.oncall = p["oncall"]
    self.puzzletron_id = int(p["puzzletron_id"])
    self.version = int(p["version"])

    self.max_queued = p.get("max_queued", self.DEFAULT_MAX_QUEUED)

    self.answers = set()
    self.display_answers = {}
    for a in c["ANSWER"].values():
      disp = a.upper().strip()
      a = self.canonicalize_answer(a)
      self.display_answers[a] = disp
      self.answers.add(a)

    if "INCORRECT_RESPONSES" in c:
      self.incorrect_responses = dict(
        (self.canonicalize_answer(k), self.respace_text(v))
        for (k, v) in c["INCORRECT_RESPONSES"].items())
    else:
      self.incorrect_responses = {}

    self.load_html(path)

    return self

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
    if text is None: return None
    return " ".join(text.split()).strip()









