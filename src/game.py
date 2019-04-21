import configparser
import heapq
import json
import os
import re
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


class Submission:
  PENDING = "pending"
  PARTIAL = "partial"
  INCORRECT = "incorrect"
  CORRECT = "correct"

  GLOBAL_SUBMIT_QUEUE = []

  def __init__(self, now, team, puzzle, answer):
    self.state = self.PENDING
    self.team = team
    self.puzzle = puzzle
    self.puzzle_state = team.get_puzzle_state(puzzle)
    self.answer = answer
    self.submit_time = now
    self.extra_response = None

    delay = self.check_delay()
    if delay is None:
      self.check_time = now
      self.check_answer(now)
    else:
      self.check_time = now + delay
      heapq.heappush(self.GLOBAL_SUBMIT_QUEUE, (self.check_time, self))
      self.team.send_message({"method": "history_change", "puzzle_id": self.puzzle.shortname})

  def check_delay(self):
    previous = len(self.puzzle_state.submissions)
    if previous < 3:
      return None
    else:
      return (previous-2) * 10

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

  def to_json(self):
    return json.dumps({"submit_time": self.submit_time,
                       "answer": self.answer,
                       "check_time": self.check_time,
                       "state": self.state,
                       "response": self.extra_response})



class Team(login.LoginUser):
  BY_USERNAME = {}

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

  @save_state
  def submit_answer(self, now, shortname, answer):
    puzzle = Puzzle.get_by_shortname(shortname)
    if not puzzle:
      print(f"no puzzle {shortname}")
      return False

    state = self.puzzle_state[puzzle]
    if state.state != state.OPEN:
      print(f"puzzle {shortname} {state.state} for {self.username}")
      return False

    state.submissions.append(Submission(now, self, puzzle, answer))
    return True

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







