import asyncio
import collections
import copy
import datetime
import hashlib
import heapq
import html
import json
import os
import re
import statistics
import string
import time
import unicodedata

import login
from state import save_state
import util
import wait_proxy

OPTIONS = None

class Log:
  Entry = collections.namedtuple("Entry", ("when", "htmls"))

  def __init__(self):
    self.entries = []
    self.data = []

  def add(self, when, html):
    if self.entries and when == self.entries[0].when:
      self.entries[0].htmls.append(html)
    else:
      self.entries.insert(0, Log.Entry(when, [html]))
      self.data.insert(0, self.entries[0]._asdict())

  def get_data(self):
    return self.data


class HintMessage:
  def __init__(self, parent, when, sender, text, admin_only):
    self.parent = parent  # PuzzleState
    self.when = when
    # sender is either a Team or an AdminUser
    self.sender = sender
    self.text = text
    self.admin_only = admin_only

  def json_dict(self, for_admin=False):
    d = {"when": self.when, "text": self.text}
    if isinstance(self.sender, login.AdminUser):
      if for_admin:
        d["sender"] = self.sender.fullname
      else:
        d["sender"] = "Hunt HQ"
    else:
      d["sender"] = self.parent.team.name
    if for_admin and self.admin_only:
      d["admin_only"] = True
    return d

class Task:
  def __init__(self, when, team, taskname, text, url, oncomplete):
    self.when = int(when)
    self.team = team
    self.taskname = taskname
    self.text = text
    self.url = url
    self.oncomplete = oncomplete
    self.key = "t-" + team.username + "-" + taskname
    self.claim = None

class TaskQueue:
  def __init__(self):
    # PuzzleStates with outstanding hint requests
    self.states = set()
    self.tasks = {}

    self.pending_removal = {}

    self.cached_json = None
    self.cached_bbdata = None
    self.cached_favicon = None

  def get_by_key(self, task_key):
    return self.tasks.get(task_key)

  def remove_by_key(self, task_key):
    if self.tasks.pop(task_key, None):
      self.change()

  async def purge(self, after):
    if after is not None:
      await asyncio.sleep(after+.1)
    now = time.time()
    to_delete = []
    for key, when in self.pending_removal.items():
      if when <= now:
        to_delete.append((when, key))
    if to_delete:
      to_delete.sort()
      for when, key in to_delete:
        self.pending_removal.pop(key, None)
        task = self.tasks.pop(key, None)
        if task and task.oncomplete:
          await task.oncomplete(task, when)

      self.change()

  def build(self):
    for t in Team.all_teams():
      for ps in t.puzzle_state.values():
        if ps.hints and ps.hints[-1].sender == t:
          self.states.add(ps)
    self.ordered = None

  def add(self, puzzle_state):
    self.states.add(puzzle_state)
    self.change()

  def remove(self, puzzle_state):
    self.states.discard(puzzle_state)
    self.change()

  def add_task(self, when, team, taskname, text, url, oncomplete):
    task = Task(when, team, taskname, text, url, oncomplete)
    if task.key in self.tasks: return  # dups
    self.tasks[task.key] = task
    self.change()

  def change(self):
    self.cached_json = None
    self.cached_bbdata = None
    self.cached_favicon = None
    if not save_state.REPLAYING:
      self.to_json()
      login.AdminUser.send_messages([
        {"method": "task_queue",
         "favicon": {
           "s32x32": OPTIONS.static_content[f"admin_fav_{self.cached_favicon}/favicon-32x32.png"],
           "s16x16": OPTIONS.static_content[f"admin_fav_{self.cached_favicon}/favicon-16x16.png"]
         }}], flush=True)

  def get_bb_data(self):
    if self.cached_bbdata is None:
      self.to_json()
    return self.cached_bbdata

  def to_json(self):
    if self.cached_json is not None: return self.cached_json

    total = 0
    claimed = 0

    q = []
    for ps in self.states:
      ts = 0
      for h in reversed(ps.hints):
        if h.sender == ps.team:
          ts = h.when
        else:
          break
      q.append({"team": ps.team.name,
                "what": "Hint: " + ps.puzzle.title,
                "when": ts,
                "claimant": ps.claim.fullname if ps.claim else None,
                "last_sender": ps.last_hq_sender.fullname if ps.last_hq_sender else None,
                "key": "h-" + ps.team.username + "-" + ps.puzzle.shortname,
                "target": f"/admin/team/{ps.team.username}/puzzle/{ps.puzzle.shortname}"})
      total += 1
      if ps.claim: claimed += 1
    for task in self.tasks.values():
      d = {"team": task.team.name,
           "what": task.text,
           "target": task.url,
           "when": task.when,
           "claimant": task.claim.fullname if task.claim else None,
           "key": task.key,
      }
      w = self.pending_removal.get(task.key)
      if w: d["done_pending"] = w
      q.append(d)
      total += 1
      if task.claim: claimed += 1

    q.sort(key=lambda d: (d["when"], d["team"]))

    self.cached_json = json.dumps({"queue": q})
    self.cached_bbdata = {"size": total, "claimed": claimed}

    if total > 0:
      if claimed < total:
        self.cached_favicon = "red"
      else:
        self.cached_favicon = "amber"
    else:
      self.cached_favicon = "green"

    return self.cached_json


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
    self.hints_available = False
    self.hints = []
    self.last_hq_sender = None # AdminUser of most recent reply
    self.claim = None          # AdminUser claiming hint response
    self.keeper_answers = 0

    self.admin_url = f"/admin/team/{team.username}/puzzle/{puzzle.shortname}"
    self.admin_html_puzzle = (
      f'<a href="{self.admin_url}">{html.escape(puzzle.title)}</a> '
      f'<span class="landtag" style="background-color: {puzzle.land.color};">{puzzle.land.symbol}</span>')


    self.admin_html_team = f'<a href="{self.admin_url}">{html.escape(team.name)}</a>'


  def recent_solve(self, now=None):
    if now is None:
      now = time.time()
    return (self.state == PuzzleState.SOLVED and
            0 <= now - self.solve_time <= PuzzleState.RECENT_TIME)

  def requeue_pending(self, now):
    for count, sub in enumerate(reversed(self.submissions)):
      if sub.state != sub.PENDING:
        break
    if not count: return

    after = self.submissions[-count:]
    del self.submissions[-count:]
    for sub in after:
      sub.check_time = None
      self.submissions.append(sub)
      sub.check_or_queue(now)


class Submission:
  PENDING = "pending"
  PARTIAL = "partial"
  INCORRECT = "incorrect"
  CORRECT = "correct"
  MOOT = "moot"
  CANCELLED = "cancelled"
  REQUESTED = "requested"

  GLOBAL_SUBMIT_QUEUE = []

  PER_ANSWER_DELAY = 20
  MAX_ACCUM = 4

  def __init__(self, now, submit_id, team, puzzle, answer):
    self.state = self.PENDING
    self.submit_id = submit_id
    self.team = team
    self.puzzle = puzzle
    self.puzzle_state = team.get_puzzle_state(puzzle)
    self.answer = Puzzle.canonicalize_answer(answer)
    self.raw_answer = answer
    self.sent_time = now
    self.submit_time = None
    self.check_time = None
    self.extra_response = None
    self.wrong_but_reasonable = None

  def __lt__(self, other):
    return self.submit_id < other.submit_id

  def check_or_queue(self, now):
    self.check_time = self.compute_check_time()
    if self.check_time <= self.sent_time:
      self.check_answer(self.sent_time)
    else:
      heapq.heappush(self.GLOBAL_SUBMIT_QUEUE, (self.check_time, self))
      self.team.achieve(Achievement.scattershot, now)
      self.team.invalidate(self.puzzle)

  def compute_check_time(self):
    # Note that self is already in the submissions list (at the end)
    # when this is called.

    guess_interval = self.puzzle.land.guess_interval
    guess_max = self.puzzle.land.guess_max

    guesses = 0
    last_ding = self.puzzle_state.open_time - guess_interval
    for sub in self.puzzle_state.submissions[:-1]:
      if not (sub.state in (self.PENDING, self.INCORRECT) and not sub.wrong_but_reasonable):
        continue

      interval = sub.check_time - last_ding
      gotten = int(interval / guess_interval)
      guesses += gotten
      if guesses > guess_max: guesses = guess_max
      #print(f"{sub.answer} {sub.check_time - sub.puzzle_state.open_time} {guesses}")
      guesses -= 1
      last_ding = sub.check_time

    sub = self.puzzle_state.submissions[-1]
    assert sub.check_time is None
    interval = max(sub.sent_time - last_ding, 0)
    gotten = int(interval / guess_interval)
    guesses += gotten
    if guesses > guess_max: guesses = guess_max
    #print(f"** {sub.answer} {sub.sent_time - sub.puzzle_state.open_time:.3f}   {interval:.3f}: +{gotten} = {guesses}")

    if guesses > 0:
      return self.sent_time

    return last_ding + (gotten+1) * guess_interval


  def check_answer(self, now):
    self.submit_time = now
    answer = self.answer
    if answer in self.puzzle.answers:
      self.state = self.CORRECT
      self.extra_response = None

    elif answer in self.puzzle.responses:
      response = self.puzzle.responses[answer]
      if response is True:
        # alternate correct answer
        self.state = self.CORRECT
        self.extra_response = None
        answer = self.puzzle.answers[0]
      elif isinstance(response, str):
        # partial-progress response
        self.state = self.PARTIAL
        self.extra_response = response
      elif isinstance(response, (list, tuple)):
        # task for HQ
        self.state = self.REQUESTED
        self.extra_response = response[0]
        Global.STATE.add_task(now, self.team.username, answer.lower(),
                              response[1], response[2])
      elif response is None:
        # incorrect but "honest guess"
        self.state = self.INCORRECT
        self.team.streak = []
        self.team.last_incorrect_answer = now
        self.wrong_but_reasonable = True
    else:
      self.state = self.INCORRECT
      self.team.streak = []
      self.team.last_incorrect_answer = now

    self.puzzle.submitted_teams.add(self.team)
    if self.state == self.INCORRECT:
      same_answer = self.puzzle.incorrect_answers.setdefault(answer, set())
      same_answer.add(self.team)
      if len(same_answer) > 10:
        for t in same_answer:
          if t.achieve(Achievement.youre_all_wrong, now):
            if t is not self.team:
              asyncio.create_task(t.flush_messages())
      self.puzzle.incorrect_counts = [(len(v), k) for (k, v) in self.puzzle.incorrect_answers.items()]
      self.puzzle.incorrect_counts.sort(key=lambda x: (-x[0], x[1]))

    self.puzzle_state.requeue_pending(now)

    msg = (f'{self.puzzle_state.admin_html_team} submitted <b>{html.escape(self.raw_answer)}</b>: '
           f'<span class="submission-{self.state}">{self.state}</span>.')
    explain = util.explain_unicode(self.raw_answer)
    if explain:
      msg += "<br><span class=explain>" + html.escape(explain) + "</span>"
    self.puzzle.puzzle_log.add(now, msg)

    if self.state == self.CORRECT:
      if len(self.puzzle.answers) > 1:
        self.team.activity_log.add(now, f"Got answer <b>{html.escape(answer)}</b> for {self.puzzle.html}.")
        self.team.admin_log.add(now, f"Got answer <b>{html.escape(answer)}</b> for {self.puzzle_state.admin_html_puzzle}.")
      self.puzzle_state.answers_found.add(answer)
      fn = getattr(self.puzzle, "on_correct_answer", None)
      self.team.cached_all_puzzles_data = None
      if fn: fn(now, self.team)
      if self.puzzle_state.answers_found == self.puzzle.answers:
        if not self.team.remote_only and self.puzzle in Workshop.PENNY_PUZZLES:
          if self.team.puzzle_state[Workshop.PUZZLE].state == PuzzleState.CLOSED:
            self.extra_response = Workshop.pre_response
          else:
            self.extra_response = Workshop.post_response
        self.team.solve_puzzle(self.puzzle, now)
      else:
        self.team.dirty_lands.add(self.puzzle.land.shortname)
        self.team.cached_mapdata.pop(self.puzzle.land, None)
        self.team.compute_puzzle_beam(now)

    self.team.invalidate(self.puzzle)

  def json_dict(self):
    return {"submit_time": self.submit_time,
            "answer": self.answer,
            "check_time": self.check_time,
            "state": self.state,
            "response": self.extra_response,
            "submit_id": self.submit_id}

  @classmethod
  async def realtime_process_submit_queue(cls):
    land_times = []
    for land in Land.BY_SHORTNAME.values():
      if land.open_at_time:
        land_times.append(land.open_at_time)
    land_times.sort(reverse=True)

    while True:
      now = time.time()
      teams = cls.process_submit_queue(now)
      for team in teams:
        asyncio.create_task(team.flush_messages())

      if Global.STATE.event_start_time:
        rel = now - Global.STATE.event_start_time
        beam = False
        while land_times and rel > land_times[-1]:
          beam = True
          land_times.pop()
        if beam:
          print("recomputing all beams")
          for team in Team.all_teams():
            team.compute_puzzle_beam(now)
            team.invalidate()
            await team.flush_messages()

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

  # If a puzzle was opened less than this long ago, it gets a "new!" tag.
  NEW_PUZZLE_SECONDS = 120  # 2 minutes

  GLOBAL_FASTPASS_QUEUE = []

  VIDEOS_BY_SCORE = {0: 1, 16: 2, 31: 3, 46: 4, 62: 5}
  OUTER_LANDS_SCORE = 2  # 62

  cached_bb_label_info = None

  def __init__(self, username, info):
    username = username.lower()

    assert username not in self.BY_USERNAME
    self.BY_USERNAME[username] = self

    self.active_sessions = set()

    self.username = username
    self.password_hash = info["pwhash"].encode("ascii")
    self.name = info["name"]
    self.size = info["size"]
    self.remote_only = info["remote_only"]
    self.attrs = info.get("attrs", {})

    save_state.add_instance("Team:" + username, self)

    self.map_mode = "inner_only"
    self.open_lands = {}
    self.sorted_open_lands = []
    self.open_puzzles = set()    # PuzzleState objects
    self.activity_log = Log()    # visible to team
    self.admin_log = Log()       # visible only to GC
    self.score = 0
    self.last_score_change = 0
    self.score_to_go = None
    self.videos = 1
    self.hints_open = set()
    self.current_hint_puzzlestate = None
    self.outer_lands_state = "closed"

    self.message_mu = asyncio.Lock()
    self.message_serial = 1
    self.pending_messages = []
    self.dirty_lands = set()
    self.dirty_header = False

    self.achievements = {}
    self.streak = []
    self.solve_days = set()
    self.last_incorrect_answer = None

    self.fastpasses_available = []
    self.fastpasses_used = {}

    self.pennies_earned = []
    self.pennies_collected = []

    self.cached_bb_data = None
    self.cached_mapdata = {}
    self.cached_open_hints_data = None
    self.cached_errata_data = None

    self.admin_url = f"/admin/team/{username}"
    self.admin_html = f'<a href="{self.admin_url}">{html.escape(self.name)}</a>'

  def post_init(self):
    # Create a PuzzleState object for all puzzles that exist.
    self.puzzle_state = {}
    for puzzle in Puzzle.all_puzzles():
      self.puzzle_state[puzzle] = PuzzleState(self, puzzle)


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
    if self.dirty_lands:
      self.pending_messages.append({"method": "update_map",
                                    "maps": list(self.dirty_lands)})
      self.dirty_lands.clear()
    if self.dirty_header:
      d = copy.copy(self.get_header_data())
      d["method"] = "update_header"
      self.pending_messages.append(d)
      self.dirty_header = False

    if not self.pending_messages: return
    objs, self.pending_messages = self.pending_messages, []
    if isinstance(objs, list):
      strs = [json.dumps(o) for o in objs]
    async with self.message_mu:
      await wait_proxy.Server.send_message(self, self.message_serial, strs)
      self.message_serial += len(strs)

  def discard_messages(self):
    self.pending_messages = []

  def next_serial(self):
    return self.message_serial

  def achieve_now(self, ach, delay=None):
    if ach not in self.achievements:
      self.record_achievement(ach.name, delay)
      return True

  def get_errata_data(self):
    if self.cached_errata_data: return self.cached_errata_data

    ours = []
    for e in Global.STATE.errata:
      if self.puzzle_state[e.puzzle].state != PuzzleState.CLOSED:
        ours.append({"url": e.puzzle.url,
                     "title": e.puzzle.title,
                     "when": e.when,
                     "text": e.text})

    self.cached_errata_data = ours
    return ours

  @save_state
  def add_admin_note(self, now, user_fullname, text):
    self.admin_log.add(now, f"<b>{user_fullname}</b> noted: {text}")
    self.invalidate()

  def get_all_puzzles_data(self):
    if self.cached_all_puzzles_data: return self.cached_all_puzzles_data

    out = []

    # "Penny Park": events, workshop, runaround
    plist = []
    outland = {"title": "Penny Park",
               "url": "/",
               "puzzles": plist}
    out.append(outland)
    for p in (Event.PUZZLE, Workshop.PUZZLE, Runaround.PUZZLE):
      ps = self.puzzle_state[p]
      if ps.state == PuzzleState.CLOSED: continue
      d = {"title": p.title, "url": p.url, "spacebefore": True}
      if ps.answers_found:
        d["answer"] = ", ".join(sorted(p.display_answers[a] for a in ps.answers_found))
        if ps.state == PuzzleState.OPEN:
          d["answer"] += ", \u2026"
      plist.append(d)

    for land in Land.ordered_lands:
      if land not in self.open_lands: continue
      plist = []
      outland = {"title": land.title,
                 "url": land.url}
      out.append(outland)
      for p in land.all_puzzles:
        ps = self.puzzle_state[p]
        if ps.state == PuzzleState.CLOSED: continue
        d = {"title": p.title, "url": p.url}
        if ps.answers_found:
          d["answer"] = ", ".join(sorted(p.display_answers[a] for a in ps.answers_found))
          if ps.state == PuzzleState.OPEN:
            d["answer"] += ", \u2026"

        plist.append((p.sortkey, d))

      plist.sort(key=lambda i: i[0])
      prev_g = None
      for sk, d in plist:
        if sk[0] != prev_g:
          d["spacebefore"] = True
        prev_g = sk[0]
      outland["puzzles"] = [i[1] for i in plist]

    self.cached_all_puzzles_data = {"lands": out}
    return self.cached_all_puzzles_data

  def get_header_data(self):
    use_buzz = (self.score < 13)
    d = {"score": f"Buzz: {self.score * 1000:,}" if use_buzz else f"Wonder: {self.score*10000:,}",
         "stuff": "buzz" if use_buzz else "wonder",
         "lands": [[i.symbol, i.color, i.url, i.title] for i in self.sorted_open_lands],
         "to_go": None if self.score_to_go is None else (
           self.score_to_go * (1000 if use_buzz else 1000)),
         "passes": len(self.fastpasses_available),
         }
    if self.score_to_go:
      if use_buzz:
        num = self.score_to_go * 1000
        d["to_go"] = f"<b>{num:,}</b> more buzz"
      else:
        num = self.score_to_go * 10000
        d["to_go"] = f"<b>{num:,}</b> more wonder"
    return d

  def get_land_data(self, land):
    if land in self.cached_mapdata:
      print(f" mapdata cache hit: {self.username} {land.shortname}")
      return self.cached_mapdata[land]
    print(f"mapdata cache miss: {self.username} {land.shortname}")

    if isinstance(land.base_img, str):
      # most maps: single fixed base image
      base_img = land.base_img
      base_size = land.base_size
    else:
      # Safari & Cascade Bay maps: base changes as puzzles open
      need_base = 0
      for i, p in enumerate(land.base_min_puzzles):
        if self.puzzle_state[p].state != PuzzleState.CLOSED:
          need_base = max(i, need_base)
      base_img = land.base_img[need_base]
      base_size = land.base_size[need_base]

    items = []
    mapdata = {"base_url": base_img,
               "shortname": land.shortname,
               "width": base_size[0],
               "height": base_size[1]}
    now = time.time()

    if land.shortname == "safari":
      io = land.icons["sign_overlay"]
      iod = {"icon_url": io.solved.url,
             "xywh": io.solved.pos_size,
             "name": "Each animal has up to <b>five</b> answers!  To see how many an animal has, click the SUBMIT button."}

      i = land.icons["sign"]
      d = {"icon_url": i.solved.url,
           "xywh": i.solved.pos_size,
           "poly": i.solved.poly,
           "special": iod}
      items.append(((-1, "@",), d))

    if land.puzzles:
      # This is a land map page (the items are puzzles).

      keepers = []

      for i in land.icons.values():
        if not i.puzzle: continue

        p = i.puzzle
        ps = self.puzzle_state[p]
        if ps.state == PuzzleState.CLOSED: continue

        d = {"name": p.title,
             "url": p.url,
             "icon_url": i.solved.url,
             "mask_url": i.solved_mask.url}

        if hasattr(p, "keeper_answers"):
          # compute the position later
          d["xywh"] = None
          keepers.append((p.keeper_order, d, i.solved.size))
        else:
          d["xywh"] = i.solved.pos_size

        if i.solved.poly: d["poly"] = i.solved.poly

        if ps.answers_found:
          d["answer"] = ", ".join(sorted(p.display_answers[a] for a in ps.answers_found))

        if ps.state == PuzzleState.OPEN:
          if "answer" in d: d["answer"] += ", \u2026"
          d["solved"] = False
          if (now - ps.open_time < self.NEW_PUZZLE_SECONDS and
              ps.open_time != Global.STATE.event_start_time):
            d["new_open"] = ps.open_time + self.NEW_PUZZLE_SECONDS
        elif ps.state == PuzzleState.SOLVED:
          d["solved"] = True

        items.append((p.sortkey, d))

        if i.under:
          dd = {"icon_url": i.under.url,
                "xywh": i.under.pos_size}
          # Sort these before any puzzle title
          items.append(((-1, "@",), dd))
        if i.emptypipe2:
          if ps.state == PuzzleState.SOLVED:
            pipe = getattr(i, f"fullpipe{need_base}")
          else:
            pipe = getattr(i, f"emptypipe{need_base}")
          dd = {"icon_url": pipe.url, "xywh": pipe.pos_size}
          # Sort these before any puzzle title
          items.append(((-1, "@",), dd))

      if keepers:
        KEEPER_PITCH = 44
        keepers.sort(key=lambda x: x[0])
        rx = 476 - KEEPER_PITCH * (len(keepers)-1)
        for i, (_, d, (w, h)) in enumerate(keepers):
          # position of the bottom center
          cx = rx + i * KEEPER_PITCH * 2
          cy = (327, 215)[(i+len(keepers))%2]
          cx -= w // 2
          cy -= h
          d["xywh"] = [cx, cy, w, h]
          d["poly"] = f"{cx},{cy},{cx+w},{cy},{cx+w},{cy+h},{cx},{cy+h}"

    else:
      for i in land.icons.values():
        # This is a main map page (the items are other lands).

        if i.to_land not in self.open_lands: continue
        d = { "name": i.to_land.title,
              "xywh": i.solved.pos_size,
              "poly": i.solved.poly,
              "url": i.to_land.url,
              "icon_url": i.solved.url,
              "mask_url": i.solved_mask.url}
        if i.to_land.meta_puzzle:
          p = i.to_land.meta_puzzle
          ps = self.puzzle_state[p]
          if ps.state == PuzzleState.SOLVED:
            d["solved"] = True
            d["answer"] = ", ".join(sorted(p.display_answers[a] for a in ps.answers_found))
        items.append((i.to_land.sortkey, d))

        if i.under:
          dd = {"icon_url": i.under.url,
                "xywh": i.under.pos_size}
          # Sort these before any puzzle title
          items.append((("@",), dd))

    items.sort(key=lambda i: i[0])
    for i, (sk, d) in enumerate(items):
      if i < len(items)-1 and sk[0] != items[i+1][0][0]:
        d["spaceafter"] = True
    mapdata["items"] = [i[1] for i in items]

    mapdata = json.dumps(mapdata)
    self.cached_mapdata[land] = mapdata
    return mapdata

  @save_state
  def record_achievement(self, now, aname, delay):
    ach = Achievement.by_name(aname)
    self.achieve(ach, now, delay=None if save_state.REPLAYING else delay)

  def achieve(self, ach, now, delay=None):
    if ach not in self.achievements:
      self.achievements[ach] = now
      text = f'Received the <b>{html.escape(ach.title)}</b> pin.'
      self.activity_log.add(now, text)
      self.admin_log.add(now, text)
      msg = [{"method": "achieve", "title": ach.title}]
      if delay:
        async def future():
          await asyncio.sleep(delay)
          self.send_messages(msg)
          await self.flush_messages()
          self.invalidate()
        asyncio.create_task(future())
      else:
        self.send_messages(msg)
        self.invalidate()
      return True

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

    ps = self.puzzle_state[puzzle]
    if ps.state != PuzzleState.OPEN:
      print(f"submit_answer: puzzle {shortname} {ps.state} for {self.username}")
      return

    submit_filter = getattr(puzzle, "submit_filter", None)
    if submit_filter and not submit_filter(ps): return

    pending = sum(1 for s in ps.submissions if s.state == s.PENDING)
    if pending >= ps.puzzle.max_queued:
      print(f"puzzle {shortname} max pending for {self.username}")
      return

    sub = Submission(now, submit_id, self, puzzle, answer)
    for s in ps.submissions:
      if s.answer == sub.answer:
        return sub.answer

    ps.submissions.append(sub)
    self.send_messages([{"method": "history_change", "puzzle_id": shortname}])
    sub.check_or_queue(now)

  @save_state
  def cancel_submission(self, now, submit_id, shortname):
    puzzle = Puzzle.get_by_shortname(shortname)
    if not puzzle:
      print(f"no puzzle {shortname}")
      return False

    state = self.puzzle_state[puzzle]
    if state.state != state.OPEN:
      print(f"cancel_submission: puzzle {shortname} {state.state} for {self.username}")
      return False

    for i, sub in enumerate(state.submissions):
      if sub.submit_id == submit_id and sub.state == sub.PENDING:
        sub.state = sub.CANCELLED
        state.submissions.pop(i)
        state.requeue_pending(now)
        self.invalidate(puzzle)
        break
    else:
      print(f"failed to cancel submit {submit_id} puzzle {shortname} for {self.username}")
      return

  def get_fastpass_eligible_lands(self):
    usable = []
    for land in Land.ordered_lands:
      if land not in self.open_lands: continue
      for puzzle in land.puzzles:
        st = self.puzzle_state[puzzle]
        if st.state == PuzzleState.CLOSED:
          usable.append(land)
          break
    return usable

  def get_fastpass_data(self):
    if self.fastpasses_available:
      usable = []
      for land in self.get_fastpass_eligible_lands():
        d = {"shortname": land.shortname,
             "title": land.title}
        icon = OPTIONS.static_content.get(land.shortname + "/fastpass.png")
        if icon: d["url"] = icon
        usable.append(d)
    else:
      usable = None
    return {"expire_time": self.fastpasses_available,
            "usable_lands": usable}

  @classmethod
  async def realtime_expire_fastpasses(cls):
    gfq = cls.GLOBAL_FASTPASS_QUEUE
    while True:
      now = time.time()
      while gfq and now >= gfq[0][0]:
        _, team, action = heapq.heappop(gfq)
        if action is None:
          while team.fastpasses_available and now >= team.fastpasses_available[0]:
            team.apply_fastpass(None)
        else:
          text, expire = action
          if (expire in team.fastpasses_available and
              team.get_fastpass_eligible_lands()):
            team.send_messages([{"method": "warn_fastpass", "text": text}])
            await team.flush_messages()
      await asyncio.sleep(1.0)

  @save_state
  def bestow_fastpass(self, now, expire):
    self.receive_fastpass(now, expire)

  def receive_fastpass(self, now, expire):
    self.fastpasses_available.append(now + expire)
    self.fastpasses_available.sort()
    heapq.heappush(self.GLOBAL_FASTPASS_QUEUE, (now+expire, self, None))
    if expire > 60:
      heapq.heappush(self.GLOBAL_FASTPASS_QUEUE,
                     (now+expire-60, self, ("1 minute", now+expire)))
    if expire > 300:
      heapq.heappush(self.GLOBAL_FASTPASS_QUEUE,
                     (now+expire-300, self, ("5 minutes", now+expire)))
    text = "Received a PennyPass."
    self.activity_log.add(now, text)
    self.admin_log.add(now, text)
    if not save_state.REPLAYING:
      self.send_messages([{"method": "receive_fastpass", "fastpass": self.get_fastpass_data()}])
      asyncio.create_task(self.flush_messages())
    self.dirty_header = True
    self.invalidate()

  @save_state
  def apply_fastpass(self, now, land_name):
    if land_name is None:
      land = None
    else:
      land = Land.BY_SHORTNAME.get(land_name)
      if not land or not land.puzzles: return
    if not self.fastpasses_available: return
    self.fastpasses_available.pop(0)
    if not land:
      text = "A PennyPass expired."
      self.activity_log.add(now, text)
      self.admin_log.add(now, text)
      msg = {"method": "apply_fastpass",
             "fastpass": self.get_fastpass_data()}
    else:
      self.fastpasses_used[land] = self.fastpasses_used.get(land, 0) + 1
      text = f'Used a PennyPass on <b>{html.escape(land.title)}</b>.'
      self.activity_log.add(now, text)
      self.admin_log.add(now, text)
      opened = self.compute_puzzle_beam(now)
      msg = {"method": "apply_fastpass",
             "land": land.shortname,
             "title": land.title,
             "fastpass": self.get_fastpass_data()}

    if not save_state.REPLAYING:
      self.send_messages([msg])
      asyncio.create_task(self.flush_messages())
    self.dirty_header = True
    self.invalidate()
    return True

  def open_puzzle(self, puzzle, now):
    #print(f"opening {puzzle.title}")
    state = self.puzzle_state[puzzle]
    if state.state == state.CLOSED:
      state.state = state.OPEN
      state.open_time = now
      self.open_puzzles.add(state)
      puzzle.open_teams.add(self)
      self.cached_all_puzzles_data = None
      self.cached_errata_data = None
      if puzzle.land.land_order < 1000:
        puzzle.puzzle_log.add(now, f"Opened by {state.admin_html_team}.")
        self.activity_log.add(now, f"{puzzle.html} opened.")
        self.admin_log.add(now, f"{state.admin_html_puzzle} opened.")
        self.dirty_lands.add(puzzle.land.shortname)
        self.cached_mapdata.pop(puzzle.land, None)

  def solve_puzzle(self, puzzle, now):
    ps = self.puzzle_state[puzzle]
    msgs = []
    if ps.state != PuzzleState.SOLVED:
      ps.state = PuzzleState.SOLVED
      ps.solve_time = now
      for sub in ps.submissions:
        if sub.state == sub.PENDING:
          sub.state = sub.MOOT
      self.score += puzzle.points
      self.dirty_header = True
      self.last_score_change = now
      self.open_puzzles.remove(ps)
      self.send_messages(
        [{"method": "solve",
          "puzzle_id": puzzle.shortname,
          "title": html.escape(puzzle.title),
          "audio": OPTIONS.static_content.get(puzzle.land.shortname + "/solve.mp3"),
        }])

      self.dirty_lands.add(puzzle.land.shortname)
      self.cached_mapdata.pop(puzzle.land, None)
      self.cached_all_puzzles_data = None
      if puzzle.meta:
        current_map = Land.BY_SHORTNAME[self.map_mode]
        self.cached_mapdata.pop(current_map, None)
        self.dirty_lands.add("home")
      self.invalidate(puzzle)

      if self.score >= self.OUTER_LANDS_SCORE and self.outer_lands_state == "closed":
        if self.remote_only:
          self.complete_penny_visit(now)
        else:
          Global.STATE.add_task(now, self.username, f"penny-visit",
                                "Penny visit", None,
                                oncomplete=self.complete_penny_visit)
          self.outer_lands_triggered = "triggered"

      new_videos = 0
      for s, v in Team.VIDEOS_BY_SCORE.items():
        if self.score >= s:
          new_videos = max(new_videos, v)
      if new_videos > self.videos:
        self.videos = new_videos
        self.send_messages([
          {"method": "video",
           "video_url": OPTIONS.static_content.get(f"video{self.videos}.mp4"),
           "thumb": OPTIONS.static_content.get(f"thumb{self.videos}.png"),
          }])

      # If this puzzle rewards you with a penny (land meta or events),
      # request a visit and/or record that you're owed a penny.
      if puzzle in Workshop.PENNY_PUZZLES:
        if self.remote_only:
          if self.puzzle_state[Workshop.PUZZLE].state == PuzzleState.CLOSED:
            self.admin_log.add(now, f"Skipped Loony visit for remote-only team.")
            self.open_puzzle(Workshop.PUZZLE, now)
        else:
          dirty = False
          for penny in Workshop.ALL_PENNIES.values():
            if penny.puzzle == puzzle:
              if not self.pennies_earned and not self.pennies_collected:
                Global.STATE.add_task(now, self.username, f"loony-visit",
                                      "Loony visit", None,
                                      oncomplete=self.complete_loony_visit)
              self.pennies_earned.append(penny)
              Global.STATE.add_task(now, self.username, f"penny-{penny.shortname}",
                                    f"{penny.name} penny", None,
                                    oncomplete=self.collect_penny)
              dirty = True
          if dirty:
            self.send_messages([{"method": "pennies"}])

      self.achieve(Achievement.solve_puzzle, now)

      solve_duration = ps.solve_time - ps.open_time
      puzzle.solve_durations[self] = solve_duration
      puzzle.median_solve_duration = statistics.median(puzzle.solve_durations.values())
      if (puzzle.fastest_solver is None or
          puzzle.solve_durations[puzzle.fastest_solver] > solve_duration):
        # a new record
        if puzzle.fastest_solver:
          puzzle.fastest_solver.achieve(Achievement.ex_champion, now)
          asyncio.create_task(puzzle.fastest_solver.flush_messages())
        puzzle.fastest_solver = self
        self.achieve(Achievement.champion, now)

      durtxt = util.format_duration(solve_duration)
      puzzle.puzzle_log.add(now, f"Solved by {ps.admin_html_team} ({durtxt}).")
      self.activity_log.add(now, f"{puzzle.html} solved.")
      self.admin_log.add(now, f"{ps.admin_html_puzzle} solved ({durtxt}).")

      if solve_duration < 60:
        self.achieve(Achievement.speed_demon, now)
      if solve_duration >= 24*60*60:
        self.achieve(Achievement.better_late_than_never, now)
      st = datetime.datetime.fromtimestamp(now)
      if 0 <= st.hour < 3:
        self.achieve(Achievement.night_owl, now)
      elif 3 <= st.hour < 6:
        self.achieve(Achievement.early_bird, now)
      self.solve_days.add(st.weekday())
      if self.solve_days.issuperset({4,5,6}):
        self.achieve(Achievement.weekend_pass, now)
      self.streak.append(now)
      if len(self.streak) >= 3 and now - self.streak[-3] <= 600:
        self.achieve(Achievement.hot_streak, now)

      self.compute_puzzle_beam(now)

  async def collect_penny(self, task, when):
    p = task.key.split("-")[-1]
    p = Workshop.ALL_PENNIES[p]
    self.pennies_earned.remove(p)
    self.pennies_collected.append(p)
    self.activity_log.add(when, f"Collected the <b>{p.name}</b> penny.")
    self.admin_log.add(when, f"Collected the <b>{p.name}</b> penny.")
    self.send_messages([{"method": "pennies"}])
    await self.flush_messages()

  async def complete_loony_visit(self, task, when):
    self.admin_log.add(when, f"Completed the Loony visit.")
    self.open_puzzle(Workshop.PUZZLE, when)
    self.cached_all_puzzles_data = None
    self.dirty_lands.add("home")
    self.cached_mapdata.pop(Land.BY_SHORTNAME["outer"], None)
    self.cached_mapdata.pop(Land.BY_SHORTNAME["inner_only"], None)
    await self.flush_messages()

  async def complete_penny_visit(self, task, when):
    if self.remote_only:
      self.admin_log.add(when, f"Skipped Penny visit for remote-only team.")
    else:
      self.admin_log.add(when, f"Completed the Penny visit.")
    self.outer_lands_state = "open"
    self.compute_puzzle_beam(when)
    await self.flush_messages()
    self.invalidate()

  def get_puzzle_state(self, puzzle):
    if isinstance(puzzle, str):
      puzzle = Puzzle.get_by_shortname(puzzle)
      if not puzzle: return None
    return self.puzzle_state[puzzle]

  def invalidate(self, puzzle=None, flush=True):
    self.cached_bb_data = None
    login.AdminUser.notify_update(self, puzzle, flush=flush)

  BB_PUZZLE_COLOR = {PuzzleState.CLOSED: "#dddddd",
                     PuzzleState.OPEN: "#ffdd66",
                     PuzzleState.SOLVED: "#009900"}

  @classmethod
  def bb_label_info(cls):
    if cls.cached_bb_label_info:
      return cls.cached_bb_label_info

    land_offsets = []
    lx = 0
    for land in Land.ordered_lands:
      d = {"symbol": land.symbol,
           "color": land.color,
           "left": lx}
      land_offsets.append(d)
      nx = 0
      ny = 2
      for p in land.all_puzzles:
        if not p.meta:
          cx = nx * 15 + 7
          cy = ny * 15 + 7

          while True:
            ny += 1
            if ny == 4:
              nx += 1
              ny = 0
            if nx > 1 or ny > 1: break
      lx += cx + 30
    cls.cached_bb_label_info = land_offsets
    return land_offsets

  def bb_data(self):
    if not self.cached_bb_data:
      self.cached_bb_data = {
        "score": self.score,
        "score_change": self.last_score_change,
        "name": self.name,
        "username": self.username,
        }

      out = ['<g fill="none" stroke-width="3">']
      lx = 0
      for land in Land.ordered_lands:
        if land not in self.open_lands: break
        nx = 0
        ny = 2
        for p in land.all_puzzles:
          ps = self.puzzle_state[p]
          used_hints = "-hint" if ps.hints else ""
          if p.meta:
            out.append(f'<circle cx="{lx+14.5}" cy="14.5" r="12" class="bb-{ps.state}{used_hints} bbp-{p.bbid}"/>')
          else:
            cx = nx * 15 + 7
            cy = ny * 15 + 7
            if p in land.additional_puzzles:
              out.append(f'<rect x="{lx+cx-4}" y="{cy-4}" width="8" height="8" class="bb-{ps.state}{used_hints} bbp-{p.bbid}"/>')
            else:
              out.append(f'<circle cx="{lx+cx}" cy="{cy}" r="5" class="bb-{ps.state}{used_hints} bbp-{p.bbid}"/>')

            while True:
              ny += 1
              if ny == 4:
                nx += 1
                ny = 0
              if nx > 1 or ny > 1: break
        lx += cx + 30

      out.insert(0, f'<svg xmlns="http://www.w3.org/2000/svg" width="{lx}" height="59" viewBox="0 0 {lx} 59">')
      out.append("</g></svg>")
      svg = "".join(out)
      self.cached_bb_data["svg"] = svg

    return self.cached_bb_data

  def get_open_hints_data(self):
    if self.cached_open_hints_data is not None:
      return self.cached_open_hints_data

    oh = [[p.shortname, p.title] for p in sorted(self.hints_open, key=lambda p: p.sortkey)]
    d = {"available": oh}
    if self.current_hint_puzzlestate:
      d["current"] = self.current_hint_puzzlestate.puzzle.shortname
    else:
      d["current"] = None
    self.cached_open_hints_data = d

    return self.cached_open_hints_data

  @save_state
  def open_hints(self, now, puzzle):
    puzzle = Puzzle.get_by_shortname(puzzle)
    if not puzzle: return
    ps = self.puzzle_state[puzzle]
    if ps.hints_available: return
    ps.hints_available = True
    self.hints_open.add(puzzle)
    self.cached_open_hints_data = None
    puzzle.puzzle_log.add(now, f"Hints available to {ps.admin_html_team}.")
    self.activity_log.add(now, f"Hints available for {puzzle.html}.")
    self.admin_log.add(now, f"Hints available for {ps.admin_html_puzzle}.")
    self.send_messages([{"method": "hints_open", "puzzle_id": puzzle.shortname, "title": puzzle.title}])

  @save_state
  def hint_no_reply(self, now, puzzle, sender):
    puzzle = Puzzle.get_by_shortname(puzzle)
    if not puzzle: return
    ps = self.puzzle_state[puzzle]

    sender = login.AdminUser.get_by_username(sender)
    ps.claim = None
    Global.STATE.task_queue.remove(ps)

    self.admin_log.add(now, f"<b>{sender.fullname}</b> marked hint request on {ps.admin_html_puzzle} as not needing reply.")

    msg = HintMessage(ps, now, sender, "(no reply needed)", True)
    ps.hints.append(msg)

    if self.current_hint_puzzlestate == ps:
      self.current_hint_puzzlestate = None
      self.cached_open_hints_data = None
      team_message = {"method": "hint_history",
                      "puzzle_id": puzzle.shortname}
      self.send_messages([team_message])

    login.AdminUser.send_messages([{"method": "update",
                                    "team_username": self.username,
                                    "puzzle_id": puzzle.shortname}], flush=True)

  @save_state
  def add_hint_text(self, now, puzzle, sender, text):
    puzzle = Puzzle.get_by_shortname(puzzle)
    if not puzzle: return
    ps = self.puzzle_state[puzzle]

    team_message = {"method": "hint_history",
                    "puzzle_id": puzzle.shortname}
    prev = self.current_hint_puzzlestate

    if sender is None:
      self.current_hint_puzzlestate = ps
      sender = self
      if ps.hints:
        puzzle.puzzle_log.add(now, f"{ps.admin_html_team} requested a followup hint.")
        self.activity_log.add(now, f"Requested a followup hint on {puzzle.html}.")
        self.admin_log.add(now, f"Requested a followup hint on {ps.admin_html_puzzle}.")
      else:
        puzzle.puzzle_log.add(now, f"{ps.admin_html_team} requested a hint.")
        self.activity_log.add(now, f"Requested a hint on {puzzle.html}.")
        self.admin_log.add(now, f"Requested a hint on {ps.admin_html_puzzle}.")
      ps.hints.append(HintMessage(ps, now, sender, text, False))
      Global.STATE.task_queue.add(ps)
    else:
      self.current_hint_puzzlestate = None
      sender = login.AdminUser.get_by_username(sender)
      ps.last_hq_sender = sender
      ps.claim = None
      ps.hints.append(HintMessage(ps, now, sender, text, False))
      Global.STATE.task_queue.remove(ps)
      team_message["notify"] = True
      team_message["title"] = puzzle.title

      puzzle.puzzle_log.add(now, f"<b>{sender.fullname}</b> replied to hint request from {ps.admin_html_team}.")
      self.activity_log.add(now, f"Hunt HQ replied to hint request on {puzzle.html}.")
      self.admin_log.add(now, f"<b>{sender.fullname}</b> replied to hint request on {ps.admin_html_puzzle}.")

    if prev != self.current_hint_puzzlestate:
      self.cached_open_hints_data = None
    self.invalidate(puzzle)

    self.send_messages([team_message])
    login.AdminUser.send_messages([{"method": "update",
                                    "team_username": self.username,
                                    "puzzle_id": puzzle.shortname}], flush=True)

  # BEAM!
  def compute_puzzle_beam(self, now):
    #print("-----------------------------")
    open_all = (OPTIONS.open_all or self.username == "leftout")

    opened = []
    locked = []

    min_score_to_go = None

    since_start = now - Global.STATE.event_start_time
    for land in Land.ordered_lands:
      if not land.puzzles: continue

      open_count = self.fastpasses_used.get(land, 0)

      if open_all:
        open_count = 1000
      else:
        if (since_start >= land.open_at_time or
            (self.score >= land.open_at_score and
             (land.open_at_score < self.OUTER_LANDS_SCORE or
              self.outer_lands_state == "open"))):
          open_count += land.initial_puzzles

      if open_count == 0:
        to_go = land.open_at_score - self.score
        if min_score_to_go is None or min_score_to_go > to_go:
          min_score_to_go = to_go
        continue

      stop_after = 1000
      skip12 = False
      if land.shortname == "cascade":
        skip12 = True
        if self.puzzle_state[land.first_submeta].state == PuzzleState.SOLVED:
          self.open_puzzle(land.second_submeta, now)
          if self.puzzle_state[land.second_submeta].state == PuzzleState.SOLVED:
            self.open_puzzle(land.meta_puzzle, now)
          else:
            stop_after = 13
        else:
          stop_after = 9

      for i, p in enumerate(land.puzzles):
        if i >= stop_after: break
        if skip12 and 1 <= i <= 2: continue
        if self.puzzle_state[p].state == PuzzleState.CLOSED:
          if open_count > 0 or p.meta or p.submeta:
            self.open_puzzle(p, now)
            opened.append(p)
          else:
            break
        if self.puzzle_state[p].state == PuzzleState.OPEN:
          if not p.meta and not p.submeta:
            open_count -= 1

    safari = Land.BY_SHORTNAME.get("safari", None)
    if safari and (safari in self.open_lands or open_all):
      answers = set()
      keepers_solved = 0
      for p in safari.puzzles:
        answers.update(self.puzzle_state[p].answers_found)
      for kp in safari.keepers:
        kps = self.puzzle_state[kp]
        if kps.state == PuzzleState.SOLVED:
          keepers_solved += 1
        elif kps.state == PuzzleState.CLOSED:
          if open_all:
            self.open_puzzle(kp, now)
          else:
            count = sum(1 for a in kp.keeper_answers if a in answers)
            if kps.keeper_answers == 0 and count >= kp.keeper_needed:
              kps.keeper_answers = min(len(answers)+2, safari.total_keeper_answers)
              print(f"{self.username} will open {kp.icon.name} at {kps.keeper_answers} answers")
            if 0 < kps.keeper_answers <= len(answers):
              print(f"{self.username} opening {kp.icon.name}")
              self.open_puzzle(kp, now)
      meta = Puzzle.get_by_shortname("safari_adventure")
      if (meta and self.puzzle_state[meta].state == PuzzleState.CLOSED and
          (keepers_solved >= 5 or open_all)):
        self.open_puzzle(meta, now)

    if self.puzzle_state[Runaround.PUZZLE].state == PuzzleState.CLOSED:
      for p in Runaround.REQUIRED_PUZZLES:
        if self.puzzle_state[p].state != PuzzleState.SOLVED:
          break
      else:
        # Open the runaround!
        self.open_puzzle(Runaround.PUZZLE, now)
        self.cached_all_puzzles_data = None

    for st in self.puzzle_state.values():
      if st.state != PuzzleState.CLOSED:
        if st.puzzle.land.land_order >= 1000: continue
        if st.puzzle.land not in self.open_lands:
          self.open_lands[st.puzzle.land] = now
          self.sorted_open_lands = [land for land in self.open_lands.keys() if land.land_order]
          self.sorted_open_lands.sort(key=lambda land: land.land_order)
          self.dirty_lands.add("home")
          self.cached_mapdata.pop(Land.BY_SHORTNAME["outer"], None)
          self.cached_mapdata.pop(Land.BY_SHORTNAME["inner_only"], None)
          self.dirty_header = True
          if now != Global.STATE.event_start_time:
            self.send_messages([{"method": "open",
                                 "title": html.escape(st.puzzle.land.title),
                                 "land": st.puzzle.land.shortname,
                                 "fastpass": self.get_fastpass_data()}])

    # Check for the first outer land
    if Land.BY_SHORTNAME.get("studios") in self.open_lands:
      if self.map_mode != "outer":
        self.map_mode = "outer"
        self.dirty_lands.add("home")
        self.cached_mapdata.pop(Land.BY_SHORTNAME["outer"], None)
        self.cached_mapdata.pop(Land.BY_SHORTNAME["inner_only"], None)
    current_map = Land.BY_SHORTNAME[self.map_mode]
    if current_map not in self.open_lands:
      self.open_lands[current_map] = now

    self.score_to_go = min_score_to_go

    return opened

class Subicon:
  def __init__(self, d):
    if d:
      self.size = d["size"]
      pos = d.get("pos")
      if pos:
        self.pos = pos
        self.pos_size = pos + self.size
      else:
        self.pos = None
        self.pos_size = [None, None] + self.size
      self.poly = d.get("poly")
      self.url = d["url"]
    else:
      self.pos = None
      self.size = None
      self.pos_size = None
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
    self.headerimage = d.get("headerimage")

    #self.locked = Subicon(d.get("locked"))
    # self.unlocked = Subicon(d.get("unlocked"))
    # self.unlocked_mask = Subicon(d.get("unlocked_mask"))
    # self.unlocked_thumb = Subicon(d.get("unlocked_thumb"))
    self.solved = Subicon(d.get("solved"))
    self.solved_mask = Subicon(d.get("solved_mask"))
    #self.solved_thumb = Subicon(d.get("solved_thumb"))

    for opt in ("under",
                "emptypipe1", "fullpipe1",
                "emptypipe2", "fullpipe2",
                "emptypipe0", "fullpipe0"):
      s = d.get(opt)
      if s:
        setattr(self, opt, Subicon(s))
      else:
        setattr(self, opt, None)

class Land:
  BY_SHORTNAME = {}

  DEFAULT_GUESS_INTERVAL = 30  # 6 minutes
  DEFAULT_GUESS_MAX = 10

  DEFAULT_INITIAL_PUZZLES = 2

  def __init__(self, shortname, cfg, event_dir):
    print(f"  Adding land \"{shortname}\"...")

    self.BY_SHORTNAME[shortname] = self
    if shortname in ("inner_only", "outer"):
      self.shortname = "home"
    else:
      self.shortname = shortname
    self.title = cfg["title"]
    self.sortkey = (util.make_sortkey(self.title), id(self))
    self.logo = cfg.get("logo")
    self.symbol = cfg.get("symbol", None)
    self.land_order = cfg.get("land_order")
    self.color = cfg.get("color")
    self.guess_interval = cfg.get("guess_interval", self.DEFAULT_GUESS_INTERVAL)
    self.guess_max = cfg.get("guess_max", self.DEFAULT_GUESS_MAX)
    self.open_at_score, self.open_at_time = cfg.get("open_at", (None, None))
    if self.open_at_time: self.open_at_time *= 60
    self.initial_puzzles = cfg.get("initial_puzzles", self.DEFAULT_INITIAL_PUZZLES)

    self.base_img = cfg["base_img"]
    self.base_size = cfg["base_size"]

    if shortname in ("inner_only", "outer"):
      self.url = "/"
    else:
      self.url = "/land/" + shortname

    assignments = cfg.get("assignments", {})

    self.total_keeper_answers = 0
    self.keepers = []
    self.icons = {}
    self.meta_puzzle = None

    for name, d in cfg.get("icons", {}).items():
      i = Icon(name, self, d)
      self.icons[name] = i

      pd = assignments.get(name, {})
      if "puzzle" in pd:
        p = pd["puzzle"]
        if OPTIONS.placeholders or p.startswith("_"):
          p = Puzzle.placeholder_puzzle(p)
        else:
          p = Puzzle.from_json(os.path.join(event_dir, "puzzles", p + ".json"))
        p.land = self
        p.icon = i
        i.puzzle = p
        p.meta = not not pd.get("meta")
        if p.meta:
          self.meta_puzzle = p
        p.submeta = not not pd.get("submeta")

        if "answers" in pd:
          self.keepers.append(p)
          p.keeper_answers = pd["answers"]
          p.keeper_needed = pd["needed"]
          p.keeper_order = pd["order"]
          self.total_keeper_answers += len(p.keeper_answers)

        p.post_init(self, i)

    self.puzzles = tuple(self.icons[i].puzzle for i in cfg.get("order", ()))
    self.additional_puzzles = tuple(self.icons[i].puzzle for i in cfg.get("additional_order", ()))
    self.base_min_puzzles = tuple(self.icons[i].puzzle for i in cfg.get("base_min_puzzles", ()))
    self.all_puzzles = self.additional_puzzles + self.puzzles

    if self.shortname == "cascade":
      self.first_submeta = self.icons["lazyriver"].puzzle
      self.second_submeta = self.icons["lifeguard"].puzzle

  def __repr__(self):
    return f"<Land \"{self.title}\">"

  @classmethod
  def resolve_lands(cls):
    by_land_order = []
    for land in cls.BY_SHORTNAME.values():
      if land.land_order:
        by_land_order.append((land.land_order, land))
      for i in land.icons.values():
        if not i.puzzle:
          i.to_land = cls.BY_SHORTNAME.get(i.name)

    by_land_order.sort()
    cls.ordered_lands = [i[1] for i in by_land_order]


class Puzzle:
  BY_SHORTNAME = {}
  DEFAULT_MAX_QUEUED = 3
  PLACEHOLDER_COUNT = 0
  NEXT_BBID = 1

  def __init__(self, shortname):
    if not re.match(r"^[a-z][a-z0-9_]*$", shortname):
      raise ValueError(f"\"{shortname}\" is not a legal puzzle shortname")
    if shortname in self.BY_SHORTNAME:
      raise ValueError(f"duplicate puzzle shortname \"{shortname}\"")

    self.BY_SHORTNAME[shortname] = self
    self.shortname = shortname
    self.url = f"/puzzle/{shortname}"
    self.admin_url = f"/admin/puzzle/{shortname}"
    self.points = 1
    #import random
    self.hints_available_time = 24 * 3600   # 24 hours
    self.emojify = False
    self.explanations = {}
    self.puzzle_log = Log()
    self.zip_version = None

    self.median_solve_duration = None
    self.solve_durations = {}     # {team: duration}
    self.fastest_solver = None
    self.incorrect_answers = {}   # {answer: {teams}}
    self.incorrect_counts = []    # [count: answer]
    self.open_teams = set()
    self.submitted_teams = set()
    self.errata = []

    save_state.add_instance("Puzzle:" + shortname, self)

  def post_init(self, land, icon):
    self.land = land
    self.icon = icon
    if self.meta:
      group = 0
    elif hasattr(self, "keeper_answers") or self.submeta:
      group = 1
    else:
      group = 2
    self.sortkey = (group, util.make_sortkey(self.title), id(self))
    self.bbid = Puzzle.NEXT_BBID
    Puzzle.NEXT_BBID += 1

    self.html = (f'<a href="{self.url}"><span class=puzzletitle>{html.escape(self.title)}</span></a> '
                 f'<span class="landtag" style="background-color: {land.color};">{land.symbol}</span>')
    self.admin_html = (f'<a href="{self.admin_url}"><span class=puzzletitle>{html.escape(self.title)}</span></a> '
                 f'<span class="landtag" style="background-color: {land.color};">{land.symbol}</span>')

    for a in self.answers:
      ex = util.explain_unicode(a)
      if ex:
        self.explanations[a] = ex
        self.emojify = True
    for a in self.responses.keys():
      ex = util.explain_unicode(a)
      if ex:
        self.explanations[a] = ex


  def __hash__(self):
    return id(self)
  def __eq__(self, other):
    return self is other
  def __lt__(self, other):
    return self.title < other.title

  def __repr__(self):
    return f"<Puzzle {self.shortname}>"
  __str__ = __repr__

  PLACEHOLDER_MULTI_ANSWERS = ("ALFA BRAVO CHARLIE DELTA ECHO "
                               "FOXTROT GOLF HOTEL INDIA JULIETT").split()
  #PLACEHOLDER_MULTI_ANSWERS = ("BRETT BEERS ANGST BEING SEMINAR AIMLESS INHABIT TUT RENETT RTS FIG DEER ACM IAMB").split()

  @classmethod
  def placeholder_puzzle(cls, pstr):
    cls.PLACEHOLDER_COUNT += 1
    number = cls.PLACEHOLDER_COUNT

    if pstr.startswith("_multi"):
      count = int(pstr[6:].replace("_", ""))
    else:
      count = None

    h = hashlib.sha256(str(number).encode("ascii")).digest()
    tag = (string.ascii_uppercase[h[0] % 26] +
           string.ascii_uppercase[h[1] % 26] +
           string.ascii_uppercase[h[2] % 26])
    height = (0, 100, 200, 400, 800, 1600, 3200)[h[3]%7]

    shortname = f"{tag.lower()}_placeholder_{number}"
    self = cls(shortname)

    self.path = None

    if pstr.startswith("_"):
      if tag[0] in "AEIOU":
        self.title = f"The {tag} Placeholder"
      else:
        self.title = f"{tag} Placeholder"
    else:
      self.title = pstr
    self.oncall = "nobody@example.org"
    self.puzzletron_id = -1
    self.authors = ["A. Computer"]

    self.max_queued = 10
    if count is None:
      if pstr == "_emoji":
        self.answers = {"\U0001f3f4\u200d\u2620\ufe0f"}
        self.display_answers = {"\U0001f3f4\u200d\u2620\ufe0f": "\U0001f3f4\u200d\u2620\ufe0f"}
        self.responses = {}
        self.html_body = f"<p>The answer to this placeholder puzzle is a pirate flag.</p>"
      elif pstr == "_task":
        self.answers = {tag}
        self.display_answers = {tag: tag}
        self.responses = {
          "REDHERRING": "No, that's just a red herring.",
          "POPCORN": ["The popcorn vendor is being dispatched to your location!",
                      "Deliver popcorn"],
          "WILDGUESS": None
          }
        self.html_body = f"<p>Submit <b>POPCORN</b> when you're ready for a visit from Hunt HQ.</p>"
      else:
        self.answers = {tag}
        self.display_answers = {tag: tag}
        self.responses = {}
        self.html_body = (f"<p>The answer to this placeholder puzzle is <b>{tag}</b>.</p>"
                          f"<div style=\"height: {height}px;\"></div><p>Hello.</p>")
    else:
      self.answers = set()
      self.display_answers = {}
      self.responses = {}
      for i in cls.PLACEHOLDER_MULTI_ANSWERS[:count]:
        self.answers.add(i)
        self.display_answers[i] = i
        # har de har har.
        if i == "ALFA":
          self.responses["ALPHA"] = "With the <i>correct</i> spelling, please."
        if i == "JULIETT":
          self.responses["JULIET"] = "With the <i>correct</i> spelling, please."
      self.html_body = f"<p>The answers to this placeholder puzzle are the first {count} letters of the NATO phonetic alphabet.</p>"

    self.html_head = None
    self.solution_head = None
    self.solution_body = "The solution goes here."
    self.for_ops_url = "https://isotropic.org/"

    return self

  @classmethod
  def from_json(cls, path):
    shortname = os.path.splitext(os.path.basename(path))[0]
    with open(path) as f:
      j = json.load(f)

    assert shortname == j["shortname"]
    self = cls(shortname)

    self.path = path

    self.title = j["title"]
    self.oncall = j["oncall"]
    self.authors = j["authors"]
    self.puzzletron_id = j["puzzletron_id"]
    self.zip_version = j.get("zip_version")
    self.max_queued = j.get("max_queued", self.DEFAULT_MAX_QUEUED)

    if "incorrect_responses" in j and "responses" not in j:
      j["responses"] = j.pop("incorrect_responses")

    self.answers = set()
    self.display_answers = {}
    for a in j["answers"]:
      disp = a.upper().strip()
      a = self.canonicalize_answer(a)
      self.display_answers[a] = disp
      self.answers.add(a)

    self.responses = dict(
        (self.canonicalize_answer(k), self.respace_text(v))
        for (k, v) in j["responses"].items())

    self.html_head = j.get("html_head")
    self.html_body = j["html_body"]
    self.solution_head = j.get("solution_head")
    self.solution_body = j.get("solution_body", "(MISSING SOLUTION)")
    self.for_ops_url = j.get("for_ops_url", None)

    return self

  def reload(self):
    if not self.path:
      return "This puzzle doesn't support reloading."

    try:
      with open(self.path) as f:
        j = json.load(f)
    except Exception as e:
      return f"Error reloading puzzle: {e}"

    if j["shortname"] != self.shortname:
      return f"New file has shortname '{j['shortname']}'."

    new_answers = set()
    new_display_answers = {}
    for a in j["answers"]:
      disp = a.upper().strip()
      a = self.canonicalize_answer(a)
      new_display_answers[a] = disp
      new_answers.add(a)

    if new_answers != self.answers:
      return f"New file has different canonical answers."

    self.answers = new_answers
    self.display_answers = new_display_answers

    self.title = j["title"]
    self.oncall = j["oncall"]
    self.authors = j["authors"]
    self.puzzletron_id = j["puzzletron_id"]
    self.zip_version = j.get("zip_version")
    self.max_queued = j.get("max_queued", self.DEFAULT_MAX_QUEUED)

    if "incorrect_responses" in j and "responses" not in j:
      j["responses"] = j.pop("incorrect_responses")

    self.responses = dict(
        (self.canonicalize_answer(k), self.respace_text(v))
        for (k, v) in j["responses"].items())

    self.html_head = j.get("html_head")
    self.html_body = j["html_body"]
    self.solution_head = j.get("solution_head")
    self.solution_body = j.get("solution_body", "(MISSING SOLUTION)")
    self.for_ops_url = j.get("for_ops_url", None)


  @classmethod
  def get_by_shortname(cls, shortname):
    return cls.BY_SHORTNAME.get(shortname)

  @classmethod
  def all_puzzles(cls):
    return cls.BY_SHORTNAME.values()

  @save_state
  def set_hints_available_time(self, now, new_time, admin_user):
    self.hints_available_time = new_time
    admin_user = login.AdminUser.get_by_username(admin_user)
    self.puzzle_log.add(now, f"Hint time set to {util.format_duration(new_time)} by {admin_user.fullname}.")
    if not save_state.REPLAYING:
      self.maybe_open_hints(now)
      self.invalidate()

  def invalidate(self, flush=True):
    d = {"method": "update",
         "puzzle_id": self.shortname}
    login.AdminUser.send_messages([d], flush=flush)

  def maybe_open_hints(self, now):
    msg = [{"method": "hints_open", "puzzle_id": self.shortname, "title": self.title}]
    for t in Team.all_teams():
      ps = t.puzzle_state[self]
      if (ps.state == PuzzleState.OPEN and
          not ps.hints_available and
          now - ps.open_time >= self.hints_available_time):
        t.open_hints(self.shortname)
        asyncio.create_task(t.flush_messages())

  @staticmethod
  def canonicalize_answer(text):
    text = unicodedata.normalize("NFD", text.upper())
    out = []
    for k in text:
      cat = unicodedata.category(k)
      # Letters, "other symbols", or specific characters needed for complex emojis
      if cat == "So" or cat[0] == "L" or k == u"\u200D" or k == u"\uFE0F":
        out.append(k)
    return "".join(out)

  @staticmethod
  def respace_text(text):
    if text is None: return None
    if text is True: return True
    if isinstance(text, (list, tuple)):
      return tuple(Puzzle.respace_text(t) for t in text)
    else:
      return " ".join(text.split()).strip()

  @classmethod
  async def realtime_open_hints(cls):
    while True:
      now = time.time()
      for t in Team.all_teams():
        flush = False
        for ps in t.open_puzzles:
          if not ps.hints_available and now - ps.open_time >= ps.puzzle.hints_available_time:
            t.open_hints(ps.puzzle.shortname)
            flush = True
        if flush:
          asyncio.create_task(t.flush_messages())
      await asyncio.sleep(10.0)


class Erratum:
  def __init__(self, when, puzzle, text, sender):
    self.when = when
    self.puzzle = puzzle
    self.text = text
    self.sender = sender

    puzzle.errata.insert(0, self)


class Global:
  STATE = None
  UNDO_DONE_DELAY = 5

  @save_state
  def __init__(self, now):
    self.options = None
    self.event_start_time = None
    self.expected_start_time = int(now + OPTIONS.start_delay)
    Global.STATE = self
    asyncio.create_task(self.future_start())

    self.stopping = False
    self.stop_cv = asyncio.Condition()

    self.task_queue = TaskQueue()

    self.errata = []

  @save_state
  def post_erratum(self, now, shortname, text, sender):
    puzzle = Puzzle.get_by_shortname(shortname)
    if not puzzle: return
    sender = login.AdminUser.get_by_username(sender)
    if not sender: return
    self.errata.insert(0, Erratum(now, puzzle, text, sender))

    puzzle.puzzle_log.add(now, f"An erratum was posted by <b>{sender.fullname}</b>.")

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
      self.start_event(True)

  @save_state
  def start_event(self, now, timed):
    if self.event_start_time is not None: return
    self.event_start_time = now
    print(f"starting event at {now}")
    for team in Team.BY_USERNAME.values():
      team.compute_puzzle_beam(self.event_start_time)
      team.open_puzzle(Event.PUZZLE, now)
      team.invalidate(flush=False)
    if timed and not save_state.REPLAYING:
      asyncio.create_task(self.notify_event_start())
    asyncio.create_task(login.AdminUser.flush_messages())

    for land in Land.BY_SHORTNAME.values():
      if land.open_at_time:
        asyncio.create_task(self.beam_all(land.open_at_time))

  async def beam_all(self, delay):
    await asyncio.sleep(delay + 1)
    now = time.time()
    for team in Team.all_teams():
      team.compute_puzzle_beam(now)
      await team.flush_messages()

  def add_task(self, now, team, taskname, text, url, oncomplete=None):
    team = Team.get_by_username(team)
    if not team: return
    self.task_queue.add_task(now, team, taskname, text, url, oncomplete)

  @save_state
  def claim_task(self, now, task_key, username):
    task = self.task_queue.get_by_key(task_key)
    if not task: return
    if username is None:
      task.claim = None
    else:
      user = login.AdminUser.get_by_username(username)
      if not user: return
      task.claim = user
    self.task_queue.change()

  @save_state
  def complete_task(self, now, task_key, undo):
    if undo:
      self.task_queue.pending_removal.pop(task_key, None)
    else:
      self.task_queue.pending_removal[task_key] = now + self.UNDO_DONE_DELAY
      if not save_state.REPLAYING:
        asyncio.create_task(self.task_queue.purge(self.UNDO_DONE_DELAY))
    self.task_queue.change()

  async def notify_event_start(self):
    for team in Team.BY_USERNAME.values():
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
          if team.achieve_now(Achievement.flawless):
            asyncio.create_task(team.flush_messages())
      await asyncio.sleep(15)

  def bb_task_queue_data(self):
    return self.task_queue.get_bb_data()


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

    # TODO(dougz): this currently requires no incorrect intervening answers
    Achievement("hot_streak",
                "Hot streak",
                "Solve three puzzles within ten minutes.")

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
                "Trigger answer throttling with incorrect guesses.")

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

class MiscLand:
  SINGLETON = None

  @classmethod
  def get(cls):
    if not cls.SINGLETON:
      cls.SINGLETON = MiscLand()
    return cls.SINGLETON

  def __init__(self):
    self.shortname = "pennypark"
    self.title = "Penny Park"
    self.symbol = "PP"
    self.color = "#000000"
    self.land_order = 1000
    self.guess_interval = 30
    self.guess_max = 4

class Event:
  ALL_EVENTS = []

  def __init__(self, shortname, d):
    self.shortname = shortname
    self.title = d["title"]
    self.time = d["time"]
    self.location = d["location"]
    self.display_answer = d["answer"]
    self.answer = Puzzle.canonicalize_answer(self.display_answer)
    self.order = d["order"]
    self.text = d["text"]

    self.ALL_EVENTS.append(self)

  @classmethod
  def post_init(cls):
    cls.ALL_EVENTS.sort(key=lambda ev: ev.order)

    p = Puzzle("events")
    cls.PUZZLE = p

    p.oncall = ""
    p.puzzletron_id = -1
    p.authors = ["Left Out"]

    p.title = "Events"
    p.url = "/events"
    p.answers = {e.answer for e in cls.ALL_EVENTS}
    p.display_answers = dict((e.answer, e.display_answer) for e in cls.ALL_EVENTS)
    p.responses = {}
    p.html_body = None
    p.html_head = None
    p.for_ops_url = ""
    p.max_queued = Puzzle.DEFAULT_MAX_QUEUED
    p.meta = False
    p.submeta = False
    p.points = 0  # no buzz/wonder for finishing

    def on_correct_answer(now, team):
      team.receive_fastpass(now, 300)
      ps = team.puzzle_state[cls.PUZZLE]
      completed = [e.answer in ps.answers_found for e in cls.ALL_EVENTS]
      team.send_messages([{"method": "event_complete", "completed": completed}])

    p.on_correct_answer = on_correct_answer

    p.post_init(MiscLand.get(), None)

    e = [e for e in cls.ALL_EVENTS if e.time == "__special__"][0]
    e.team_time = {}

    teams_by_size = [((t.size, id(t)), t) for t in Team.all_teams()]
    teams_by_size.sort()
    half = (len(teams_by_size)+1) // 2
    for i, (_, t) in enumerate(teams_by_size):
      if i < half:
        e.team_time[t] = "10:30am Saturday"
      else:
        e.team_time[t] = "9am Saturday"
    e.time = None

class Workshop:
  ALL_PENNIES = {}
  PENNY_PUZZLES = set()

  @classmethod
  def build(cls, d):
    for shortname, pd in d["pennies"].items():
      Workshop(shortname, pd)

    cls.pre_response = d["pre_response"]
    cls.post_response = d["post_response"]


  def __init__(self, shortname, d):
    self.shortname = shortname
    self.name = d["name"]
    self.puzzle = d["puzzle"]

    self.ALL_PENNIES[shortname] = self

  @classmethod
  def submit_filter(cls, ps):
    return len(ps.team.pennies_collected) == len(cls.ALL_PENNIES)

  @classmethod
  def post_init(cls):
    for p in cls.ALL_PENNIES.values():
      p.puzzle = Puzzle.get_by_shortname(p.puzzle)
      cls.PENNY_PUZZLES.add(p.puzzle)

    p = Puzzle("workshop")
    cls.PUZZLE = p

    p.oncall = ""
    p.puzzletron_id = -1
    p.authors = ["Left Out"]

    p.title = "Workshop"
    p.url = "/workshop"
    p.answers = {"MASHNOTE"}
    p.display_answers = {"MASHNOTE": "MASH NOTE"}
    p.responses = {}
    p.html_body = None
    p.html_head = None
    p.for_ops_url = ""
    p.max_queued = Puzzle.DEFAULT_MAX_QUEUED
    p.meta = False
    p.submeta = False
    p.points = 0  # no buzz/wonder for finishing

    p.submit_filter = cls.submit_filter

    p.post_init(MiscLand.get(), None)


class Runaround:
  SEGMENTS = []
  # All these puzzles must be solved to start the Runaround.
  REQUIRED_PUZZLES = set()

  def __init__(self, d):
    self.shortname = d["land"]
    self.answer = Puzzle.canonicalize_answer(d["answer"])
    self.display_answer = d["answer"]

  @classmethod
  def build(cls, d):
    for dd in d["minis"]:
      cls.SEGMENTS.append(Runaround(dd))

    p = Puzzle("runaround")
    cls.PUZZLE = p

    p.oncall = ""
    p.puzzletron_id = -1
    p.authors = ["Left Out"]

    p.title = "Heart of the Park"
    p.url = "/heart_of_the_park"
    p.answers = set()
    p.display_answers = {}
    for s in cls.SEGMENTS:
      p.answers.add(s.answer)
      p.display_answers[s.answer] = s.display_answer
    p.responses = {}
    p.html_body = None
    p.html_head = None
    p.for_ops_url = ""
    p.max_queued = Puzzle.DEFAULT_MAX_QUEUED
    p.meta = False
    p.submeta = False
    p.points = 0  # no buzz/wonder for finishing

    def on_correct_answer(now, team):
      ps = team.puzzle_state[cls.PUZZLE]
      segments = {}
      for s in cls.SEGMENTS:
        if s.answer in ps.answers_found:
          segments[s.shortname] = s.display_answer
      team.send_messages([{"method": "segments_complete", "segments": segments}])

    p.on_correct_answer = on_correct_answer

    p.post_init(MiscLand.get(), None)

  @classmethod
  def post_init(cls):
    # All land metas are needed to start the runaround ...
    for land in Land.BY_SHORTNAME.values():
      if land.meta_puzzle:
        cls.REQUIRED_PUZZLES.add(land.meta_puzzle)

    # ... plus the pressed-penny puzzle.
    cls.REQUIRED_PUZZLES.add(Workshop.PUZZLE)

    print("Required for runaround:")
    for p in cls.REQUIRED_PUZZLES:
      print(f"  {p.shortname} {p.title}")

    # Note that the Events puzzle is *not* needed (even though it
    # produces a penny).
