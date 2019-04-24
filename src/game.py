import configparser
import heapq
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

  def advance(self):
    if self.state == self.OPEN:
      self.state = self.SOLVED
      self.team.send_message({"method": "solve", "title": self.puzzle.title})


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
    delay = self.check_delay()

    if delay is None:
      self.check_time = self.submit_time
      self.check_answer(self.submit_time)
    else:
      self.check_time = self.submit_time + delay
      heapq.heappush(self.GLOBAL_SUBMIT_QUEUE, (self.check_time, self))

  def check_delay(self):
    previous = len(self.puzzle_state.submissions)
    if previous < 3:
      return None
    else:
      last_check = self.submit_time
      for sub in self.puzzle_state.submissions:
        if sub.check_time > last_check:
          last_check = sub.check_time
      delay = last_check - self.submit_time + ((previous-2) * 10)
      if delay < 0: return None
      return delay

  def check_answer(self, now):
    answer = Puzzle.canonicalize_answer(self.answer)
    if answer in self.puzzle.correct_responses:
      self.state = self.CORRECT
      self.extra_response = self.puzzle.correct_responses[answer]
    elif answer in self.puzzle.incorrect_responses:
      self.state = self.PARTIAL
      self.extra_response = (
        self.puzzle.incorrect_responses[answer] or "Keep going\u2026")
    else:
      self.state = self.INCORRECT
    self.team.send_message({"method": "history_change", "puzzle_id": self.puzzle.shortname})
    if self.state == self.CORRECT:
      self.puzzle_state.advance()

  def to_json(self):
    return json.dumps({"submit_time": self.submit_time,
                       "answer": self.answer,
                       "check_time": self.check_time,
                       "state": self.state,
                       "response": self.extra_response,
                       "submit_id": self.submit_id})

  @classmethod
  def process_pending_submits(cls):
    now = time.time()
    q = cls.GLOBAL_SUBMIT_QUEUE
    while q and q[0][0] <= now:
      _, sub = heapq.heappop(q)
      if sub.state != cls.PENDING: continue
      # It's possible for sub's check_time to have changed.  If it's
      # been moved further into the future, just drop this event.
      if sub.check_time <= now:
        sub.check_answer(now)


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

    self.username = username
    self.password_hash = password_hash.encode("ascii")
    self.team_name = team_name
    self.location = location

    # Create a PuzzleState object for all puzzles that exist.
    self.puzzle_state = {}
    for puzzle in Puzzle.all_puzzles():
      self.puzzle_state[puzzle] = PuzzleState(self, puzzle)

    self.active_sessions = set()

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
      t.set_puzzle_state("sample", PuzzleState.OPEN)

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

  @save_state
  def set_puzzle_state(self, now, shortname, new_state):
    puzzle = Puzzle.get_by_shortname(shortname)
    if not puzzle:
      print(f"can't set state for {shortname}")
      return
    state = self.puzzle_state[puzzle]
    state.state = new_state

  def get_puzzle_state(self, puzzle):
    if isinstance(puzzle, str):
      puzzle = Puzzle.get_by_shortname(puzzle)
      if not puzzle: return None
    return self.puzzle_state[puzzle]


class Puzzle:
  BY_SHORTNAME = {}

  def __init__(self, path):
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

    self.shortname = shortname
    self.title = p["title"]
    self.oncall = p["oncall"]
    self.answer = p["answer"]
    self.puzzletron_id = int(p["puzzletron_id"])
    self.version = int(p["version"])

    if "INCORRECT_RESPONSES" in c:
      self.incorrect_responses = dict(
        (self.canonicalize_answer(k), self.respace_text(v))
        for (k, v) in c["INCORRECT_RESPONSES"].items())
    else:
      self.incorrect_responses = {}

    self.correct_responses = {self.canonicalize_answer(self.answer): None}
    if "CORRECT_RESPONSES" in c:
      for k, v in c["CORRECT_RESPONSES"].items():
        self.correct_responses[self.canonicalize_answer(k)] = self.respace_text(v)

    self.load_html(path)

  def load_html(self, path):
    with open(os.path.join(path, "puzzle.html")) as f:
      soup = bs4.BeautifulSoup(f, features="lxml")
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









