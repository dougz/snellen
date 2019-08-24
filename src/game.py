import asyncio
import datetime
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
      self.team.achieve(Achievement.scattershot)

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
      self.team.streak = []
      self.team.last_incorrect_answer = now

      same_answer = self.puzzle.incorrect_answers.setdefault(answer, set())
      same_answer.add(self.team)
      if len(same_answer) > 10:
        for t in same_answer:
          if t.achieve(Achievement.youre_all_wrong):
            if t is not self.team:
              asyncio.create_task(t.flush_messages())

    if self.state == self.CORRECT:
      self.puzzle_state.answers_found.add(answer)
      if self.puzzle_state.answers_found == self.puzzle.answers:
        try:
          self.team.solve_puzzle(self.puzzle, now)
        except Exception as e:
          print(e)

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

  def __init__(self, username, info):
    assert username not in self.BY_USERNAME
    self.BY_USERNAME[username] = self

    self.active_sessions = set()

    self.username = username
    self.password_hash = info["pwhash"].encode("ascii")
    self.name = info["name"]
    self.size = info["size"]
    self.attrs = info.get("attrs", {})

    save_state.add_instance("Team:" + username, self)

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
    self.streak = []
    self.solve_days = set()
    self.last_incorrect_answer = None
    self.pages_visited = set()

  def __repr__(self):
    return f"<Team {self.username}>"
  __str__ = __repr__

  def attach_session(self, session):
    self.active_sessions.add(session)
  def detach_session(self, session):
    self.active_sessions.remove(session)

  @classmethod
  def all_teams(cls):
    return cls.BY_USERNAME.values()

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

  def visit_page(self, page):
    self.pages_visited.add(page)
    if self.pages_visited == {"pins", "activity"}:
      self.delayed_achieve(Achievement.digital_explorer)

  def achieve(self, ach):
    if save_state.REPLAYING: return
    if ach not in self.achievements:
      self.record_achievement(ach.name)
      return True

  def delayed_achieve(self, ach, delay=1.0):
    """Like achieve(), but delayed slightly.  Useful for achievements
    triggered by page load, so the loaded page gets the
    notification."""
    if save_state.REPLAYING: return
    if ach in self.achievements: return
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

      solve_duration = state.solve_time - state.open_time
      puzzle.solve_durations[self] = solve_duration
      if (puzzle.fastest_solver is None or
          puzzle.solve_durations[puzzle.fastest_solver] > solve_duration):
        # a new record
        if puzzle.fastest_solver:
          puzzle.fastest_solver.achieve(Achievement.ex_champion)
          asyncio.create_task(puzzle.fastest_solver.flush_messages())
        puzzle.fastest_solver = self
        self.achieve(Achievement.champion)

      if solve_duration < 60:
        self.achieve(Achievement.speed_demon)
      if solve_duration >= 24*60*60:
        self.achieve(Achievement.better_late_than_never)
      st = datetime.datetime.fromtimestamp(now)
      if 0 <= st.hour < 3:
        self.achieve(Achievement.night_owl)
      elif 3 <= st.hour < 6:
        self.achieve(Achievement.early_bird)
      self.solve_days.add(st.weekday())
      if self.solve_days.issuperset({4,5,6}):
        self.achieve(Achievement.weekend_pass)
      self.streak.append(now)
      if len(self.streak) >= 3 and now - self.streak[-3] <= 600:
        self.achieve(Achievement.hot_streak)

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

class Subicon:
  def __init__(self, d):
    if d:
      self.pos = tuple(d["pos"])
      self.size = tuple(d["size"])
      self.poly = d["poly"]
      self.url = d["url"]
    else:
      self.pos = None
      self.size = None
      self.poly = None
      self.url = None

  def __repr__(self):
    return f"<{self.size[0]}x{self.size[1]} @ {self.pos[0]}x{self.pos[1]}>"

class Icon:
  def __init__(self, name, land, d):
    self.name = name
    self.land = land
    self.puzzle = None
    self.to_land = None
    #self.thumb_size = d.get("thumb_size", self.size)

    self.locked = Subicon(d.get("locked"))
    self.unlocked = Subicon(d.get("unlocked"))
    self.solved = Subicon(d.get("solved"))
    self.unlocked_thumb = Subicon(d.get("unlocked_thumb"))
    self.solved_thumb = Subicon(d.get("solved_thumb"))


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

    self.solve_durations = {}
    self.fastest_solver = None
    self.incorrect_answers = {}

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
    self.authors = ["A. Computer"]

    self.max_queued = self.DEFAULT_MAX_QUEUED
    self.answers = {"FILLER"}
    self.display_answers = {"FILLER": "FILLER"}
    self.incorrect_responses = {}

    self.html_head = None
    self.html_body = "<p>The answer to this filler puzzle is <b>FILLER</b>.</p>"
    self.for_ops_head = None
    self.for_ops_body = "<p>Teams should not need hints on this one.</p>"

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
    self.authors = j["authors"]
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
    self.for_ops_head = j.get("for_ops_head")
    self.for_ops_body = j.get("for_ops_body")

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
    self.expected_start_time = int(now + 30)
    Global.STATE = self
    asyncio.create_task(self.future_start())

    self.stopping = False
    self.stop_cv = asyncio.Condition()

  async def stop_server(self):
    async with self.stop_cv:
      self.stopping = True
      self.stop_cv.notify_all()

  @save_state
  def update_event_start(self, now, when):
    if self.event_start_time: return
    self.expected_start_time = when
    asyncio.create_task(self.future_start())
    asyncio.create_task(self.update_event_start_teams())

  async def future_start(self):
    delay = self.expected_start_time - time.time()
    if delay > 0:
      await asyncio.sleep(delay)
    now = time.time()
    if not self.event_start_time and now >= self.expected_start_time:
      self.start_event()

  @save_state
  def start_event(self, now):
    if self.event_start_time is not None: return
    self.event_start_time = now
    asyncio.create_task(self.notify_event_start())

  async def notify_event_start(self):
    for team in Team.BY_USERNAME.values():
      team.compute_puzzle_beam(self.event_start_time)
      team.send_messages([{"method": "to_page", "url": "/"}])
      await team.flush_messages()

  async def update_event_start_teams(self):
    for team in Team.BY_USERNAME.values():
      team.send_messages([{"method": "update_start", "new_start": self.expected_start_time}])
      await team.flush_messages()

  async def flawless_check(self):
    while True:
      now = time.time()
      for team in Team.all_teams():
        if team.last_incorrect_answer:
          start = team.last_incorrect_answer
        elif self.event_start_time:
          start = self.event_start_time
        else:
          continue
        if now - start >= 6 * 60 * 60:
          if team.achieve(Achievement.flawless):
            asyncio.create_task(team.flush_messages())
      await asyncio.sleep(15)


class Achievement:
  ALL = []
  BY_NAME = {}

  def __init__(self, name, title, subtitle):
    self.name = name
    self.title = title
    self.subtitle = subtitle
    self.url = Achievement.static_dir["achievements/" + name + ".png"]
    setattr(Achievement, name, self)
    Achievement.BY_NAME[name] = self
    Achievement.ALL.append(self)

  def __repr__(self):
    return f"<Achievement {self.name}>"

  @classmethod
  def by_name(cls, aname):
    return cls.BY_NAME[aname]

  @classmethod
  def define_achievements(cls, static_dir):
    cls.static_dir = static_dir

    Achievement("solve_puzzle",
                "That's how this works",
                "Solve a puzzle.")

    Achievement("speed_demon",
                "Speed Demon",
                "Solve a puzzle in under a minute.")

    Achievement("flawless",
                "Flawless",
                "Submit no incorrect answers for six hours.")

    Achievement("hot_streak",
                "Hot streak",
                "Submit three correct answers in a row within ten minutes.")

    Achievement("better_late_than_never",
                "Better late than never",
                "Solve a puzzle 24 hours after opening it.")

    Achievement("night_owl",
                "Night owl",
                "Solve a puzzle between midnight and 3am.")

    Achievement("early_bird",
                "Early bird",
                "Solve a puzzle between 3am and 6am.")

    Achievement("champion",
                "Champion!",
                "Set a new record time in solving a puzzle.")

    Achievement("ex_champion",
                "Ex-champion!",
                "Lose the record time for solving a puzzle.")

    Achievement("influencer",
                "Influencer",
                "Create enough buzz to save the park.")

    Achievement("take_a_shortcut",
                "Take a shortcut",
                "Solve a meta before solving all feeders.")

    Achievement("completionist",
                "Completionist",
                "Solve every single puzzle.")

    Achievement("weekend_pass",
                "Weekend pass",
                "Solve a puzzle on each of Friday, Saturday, and Sunday.")

    Achievement("digital_explorer",
                "Digital explorer",
                "Navigate to every page on the website.")

    Achievement("scattershot",
                "Scattershot",
                "Trigger answer throttling with incorrect gueses.")

    Achievement("youre_all_wrong",
                "You're all wrong!",
                "Submit the same wrong answer as ten other teams.")

    Achievement("mea_culpa",
                "Mea culpa",
                "View the errata page.")

    Achievement("bug_catcher",
                "Bug catcher",
                "Submit a valid errata entry to HQ.  Thanks!")

    Achievement("penny_pincher",
                "Penny pincher",
                "Collect your first pressed penny.")

    Achievement("parade_goer",
                "Parade-goer",
                "Attend a parade")

    Achievement("come_back",
                "Come back!",
                "Log out of the hunt server before the coin is found.")

