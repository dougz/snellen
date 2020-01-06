import asyncio
import collections
import copy
import csv
import datetime
import hashlib
import heapq
import html
import itertools
import json
import os
import re
import statistics
import string
import time
import unicodedata
import urllib

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
  def __init__(self, parent, when, sender, text, special=None):
    self.parent = parent  # PuzzleState
    parent.cached_hint_data_team = None
    parent.cached_hint_data_admin = None
    self.when = when
    # sender is either a Team or an AdminUser
    self.sender = sender
    self.text = text

    # specials:
    #   "cancel"  -- cancelled by player
    #   "ack"     -- hq clicked "no reply needed"
    #   "solved"  -- cancelled by solving
    self.special = special

class Task:
  def __init__(self, when, team, taskname, text, url, oncomplete, kind):
    self.when = int(when)
    self.team = team
    self.taskname = taskname
    self.text = text
    self.url = url
    self.oncomplete = oncomplete
    self.key = "t-" + team.username + "-" + taskname
    self.claim = None
    self.kind = kind


class TaskQueue:
  def __init__(self):
    # PuzzleStates with outstanding hint requests
    self.states = set()
    self.tasks = {}

    self.pending_removal = {}

    self.cached_json = None
    self.cached_bbdata = None

    self.favicon_data = {"red":
                         {"s32x32": OPTIONS.static_content["admin_fav_red/favicon-32x32.png"],
                          "s16x16": OPTIONS.static_content["admin_fav_red/favicon-16x16.png"]},
                         "amber":
                         {"s32x32": OPTIONS.static_content["admin_fav_amber/favicon-32x32.png"],
                          "s16x16": OPTIONS.static_content["admin_fav_amber/favicon-16x16.png"]},
                         "green":
                         {"s32x32": OPTIONS.static_content["admin_fav_green/favicon-32x32.png"],
                          "s16x16": OPTIONS.static_content["admin_fav_green/favicon-16x16.png"]},
                         }

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
        task = self.tasks.get(key)
        if task:
          Global.STATE.complete_task(key)

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

  def add_task(self, when, team, taskname, text, url, oncomplete, kind):
    task = Task(when, team, taskname, text, url, oncomplete, kind)
    if task.key in self.tasks: return  # dups
    self.tasks[task.key] = task
    self.change()

  def remove_task(self, key):
    task = self.tasks.pop(key, None)
    self.change()
    return task

  def change(self):
    self.cached_json = None
    self.cached_bbdata = None
    if not save_state.REPLAYING:
      self.to_json()
      login.AdminUser.send_messages([{"method": "task_queue"}], flush=True)

  def get_bb_data(self):
    if self.cached_bbdata is None:
      self.to_json()
    return self.cached_bbdata

  def to_json(self):
    if self.cached_json is not None: return self.cached_json

    summary = {}
    for k in ("hint", "puzzle", "visit", "penny"):
      summary[k] = [0, 0]

    q = []
    for ps in self.states:
      ts = 0
      for h in reversed(ps.hints):
        if h.sender is None and not h.special:
          ts = h.when
        else:
          break
      q.append({"team": ps.team.name,
                "kind": "hint",
                "what": "Hint: " + ps.puzzle.title,
                "when": ts,
                "claimant": ps.claim.fullname if ps.claim else None,
                "last_sender": ps.last_hq_sender.fullname if ps.last_hq_sender else None,
                "key": "h-" + ps.team.username + "-" + ps.puzzle.shortname,
                "target": f"/admin/team/{ps.team.username}/puzzle/{ps.puzzle.shortname}"})
      summary["hint"][1] += 1
      if ps.claim: summary["hint"][0] += 1
    for task in self.tasks.values():
      d = {"team": task.team.name,
           "kind": task.kind,
           "what": task.text,
           "target": task.url,
           "when": task.when,
           "claimant": task.claim.fullname if task.claim else None,
           "key": task.key,
      }
      w = self.pending_removal.get(task.key)
      if w: d["done_pending"] = w
      q.append(d)
      summary[task.kind][1] += 1
      if task.claim: summary[task.kind][0] += 1

    self.cached_json = json.dumps({"queue": q, "favicons": self.favicon_data})
    self.cached_bbdata = {"by_kind": summary}

    return self.cached_json


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
    self.hints_available = False
    self.hints = []
    self.last_hq_sender = None # AdminUser of most recent reply
    self.claim = None          # AdminUser claiming hint response
    self.keeper_answers = 0

    self.cached_hint_data_team = None
    self.cached_hint_data_admin = None

    self.admin_url = f"/admin/team/{team.username}/puzzle/{puzzle.shortname}"
    self.admin_html_puzzle = (
      f'<a href="{self.admin_url}">{html.escape(puzzle.title)}</a> '
      f'<span class="landtag" style="background-color: {puzzle.land.color};">{puzzle.land.symbol}</span>')


    self.admin_html_team = f'<a href="{self.admin_url}">{html.escape(team.name)}</a>'

  def remove_pending(self):
    count = 0
    for count, sub in enumerate(reversed(self.submissions)):
      if sub.state != sub.PENDING:
        break
    if not count: return []

    after = self.submissions[-count:]
    del self.submissions[-count:]
    return after

  def requeue(self, after, now):
    for sub in after:
      sub.check_time = None
      self.submissions.append(sub)
      sub.check_or_queue(now)

  def requeue_pending(self, now):
    self.requeue(self.remove_pending(), now)

  def reset_and_requeue(self, now, user):
    sub = Submission(now, -1, self.team, self.puzzle, None)
    sub.state = Submission.RESET
    sub.user = user

    after = self.remove_pending()
    self.submissions.append(sub)
    self.requeue(after, now)

  def hint_request_outstanding(self):
    return (self.hints and self.hints[-1].sender is None and
            self.hints[-1].special is None)

  def get_hint_data_team(self):
    if self.cached_hint_data_team is not None:
      return self.cached_hint_data_team

    out = []
    for hm in self.hints:
      if hm.special == "ack": continue
      d = {"when": hm.when, "text": hm.text,
           "sender": "Hunt HQ" if hm.sender else self.team.name}
      if hm.special: d["special"] = hm.special
      out.append(d)

    self.cached_hint_data_team = out
    return out

  def get_hint_data_admin(self):
    if self.cached_hint_data_admin is not None:
      return self.cached_hint_data_admin

    out = []
    for hm in self.hints:
      d = {"when": hm.when, "text": hm.text,
           "sender": hm.sender.fullname if hm.sender else self.team.name}
      if hm.special: d["special"] = hm.special
      out.append(d)

    self.cached_hint_data_admin = out
    return out




class Submission:
  PENDING = "pending"
  PARTIAL = "partial"
  INCORRECT = "incorrect"
  CORRECT = "correct"
  MOOT = "moot"
  CANCELLED = "cancelled"
  REQUESTED = "requested"
  RESET = "reset"

  COLOR = {
    PENDING: "gray",
    PARTIAL: "yellow",
    INCORRECT: "red",
    CORRECT: "green",
    MOOT: "gray",
    CANCELLED: "gray",
    REQUESTED: "yellow",
    RESET: "blue",
    "no answer": "red",
    "wrong number": "red",
    "complete": "yellow",
    }

  GLOBAL_SUBMIT_QUEUE = []

  def __init__(self, now, submit_id, team, puzzle, answer):
    self.state = self.PENDING
    self.submit_id = submit_id
    self.team = team
    self.puzzle = puzzle
    self.puzzle_state = team.get_puzzle_state(puzzle)
    if answer is None:
      self.answer = None
    else:
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
      self.team.invalidate(self.puzzle)

  def compute_check_time(self):
    # Note that self is already in the submissions list (at the end)
    # when this is called.

    guess_interval = self.puzzle.land.guess_interval
    guess_max = self.puzzle.land.guess_max

    guesses = 0
    last_ding = self.puzzle_state.open_time - guess_interval
    last_reset = 0
    for sub in self.puzzle_state.submissions[:-1]:
      if sub.state == self.RESET:
        guesses = 0
        last_ding = sub.sent_time - guess_interval
        last_reset = sub.sent_time
        continue

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
    virtual_sent_time = max(sub.sent_time, last_reset)
    interval = max(virtual_sent_time - last_ding, 0)
    gotten = int(interval / guess_interval)
    guesses += gotten
    if guesses > guess_max: guesses = guess_max
    #print(f"** {sub.answer} {sub.sent_time - sub.puzzle_state.open_time:.3f}   {interval:.3f}: +{gotten} = {guesses}")

    if guesses > 0:
      return virtual_sent_time

    return last_ding + (gotten+1) * guess_interval

  def check_answer(self, now):
    self.submit_time = now
    answer = self.answer

    fn = getattr(self.puzzle, "handle_answer", None)
    if fn:
      fn(self, now)
    else:
      if answer in self.puzzle.answers:
        self.state = self.CORRECT
        self.extra_response = self.puzzle.responses.get(answer)

      elif answer in self.puzzle.responses:
        response = self.puzzle.responses[answer]
        if response is True:
          # alternate correct answer
          self.state = self.CORRECT
          self.extra_response = None
          # Note: alternate correct answers are only supported for
          # single-answer puzzles.
          for a in self.puzzle.answers:
            self.answer = answer = a
            break
        elif isinstance(response, str):
          # partial-progress response
          self.state = self.PARTIAL
          self.extra_response = response
        elif isinstance(response, dict):
          # task for HQ
          self.state = self.REQUESTED
          if self.team.remote_only:
            self.extra_response = response.get(
              "remote_reply", response.get("reply", "Request sent."))
            t = response.get(
              "remote_task", response.get("task", "Unknown task."))
            u = response.get("remote_task_url", response.get("task_url"))
          else:
            self.extra_response = response.get("reply", "Request sent.")
            t = response.get("task", "Unknown task.")
            u = response.get("task_url")

          Global.STATE.add_task(now, self.team.username, answer.lower(),
                                t, u, None, "puzzle")
        elif response is None:
          # incorrect but "honest guess"
          self.state = self.INCORRECT
          self.team.last_incorrect_answer = now
          self.wrong_but_reasonable = True
      else:
        self.state = self.INCORRECT
        self.team.last_incorrect_answer = now

    Global.STATE.log_submit(now, self.team.username, self.puzzle.shortname,
                            self.raw_answer, answer, self.state)

    self.puzzle.submitted_teams.add(self.team)
    if self.state == self.INCORRECT:
      same_answer = self.puzzle.incorrect_answers.setdefault(answer, set())
      same_answer.add(self.team)
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
      self.check_answer_correct(now)

    self.team.invalidate(self.puzzle)

  def check_answer_correct(self, now):
      if len(self.puzzle.answers) > 1:
        a = self.puzzle.display_answers[self.answer]
        self.team.activity_log.add(now, f"Got answer <b>{html.escape(a)}</b> for {self.puzzle.html}.")
        self.team.admin_log.add(now, f"Got answer <b>{html.escape(a)}</b> for {self.puzzle_state.admin_html_puzzle}.")
      self.puzzle_state.answers_found.add(self.answer)
      self.team.cached_all_puzzles_data = None
      fn = getattr(self.puzzle, "on_correct_answer", None)
      if fn: fn(now, self.team)
      if self.puzzle_state.answers_found == self.puzzle.answers:
        self.extra_response = self.team.solve_puzzle(self.puzzle, now)
      else:
        self.team.dirty_lands.add(self.puzzle.land.shortname)
        self.team.cached_mapdata.pop(self.puzzle.land, None)
        self.team.compute_puzzle_beam(now)

  def json_dict(self):
    if self.state == self.RESET:
      return {"sent_time": self.sent_time,
              "state": self.state,
              "color": Submission.COLOR[self.state],
              "user": self.user.fullname}
    else:
      return {"submit_time": self.submit_time,
              "answer": self.answer,
              "check_time": self.check_time,
              "state": self.state,
              "color": Submission.COLOR[self.state],
              "response": self.extra_response,
              "submit_id": self.submit_id}

  @classmethod
  async def realtime_process_submit_queue(cls):
    while True:
      now = time.time()
      teams, beam = cls.process_submit_queue(now)

      if beam:
        Global.STATE.compute_all_beams()
        teams.update(Team.all_teams())

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

    # Check for land opening by time.
    beam = False
    if Global.STATE and Global.STATE.event_start_time:
      for land in Land.BY_SHORTNAME.values():
        if not land.open_at_time: continue   # None or 0
        rel = now - Global.STATE.event_start_time
        if rel < land.open_at_time: continue # not yet
        if land.time_unlocked: continue # already done
        land.time_unlocked = True
        print(f"recomputing all beams for {land.shortname} {rel}")
        beam = True

    return teams, beam


class Team(login.LoginUser):
  BY_USERNAME = {}
  ALT_USERNAME = {}

  GLOBAL_FASTPASS_QUEUE = []

  cached_bb_label_info = None

  def __init__(self, username, info):
    username = username.lower()

    assert username not in self.BY_USERNAME
    self.BY_USERNAME[username] = self

    self.active_sessions = set()

    self.username = username
    self.password_hash = info["pwhash"].encode("ascii")
    self.name = info["name"]
    self.name_sort = util.make_sortkey(self.name)
    if not self.name_sort:
      self.name_sort = util.make_sortkey(username)
    self.size = info["size"]
    self.remote_only = info["remote_only"]
    self.attrs = info.get("attrs", {})
    alt = self.attrs.get("alt", None)
    if alt: self.ALT_USERNAME[alt] = self

    save_state.add_instance("Team:" + username, self)

    self.next_submit_id = 1
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

    self.force_all_lands_open = self.attrs.get("all_lands_open", False)
    self.force_all_puzzles_open = self.attrs.get("all_puzzles_open", False)

    self.message_mu = asyncio.Lock()
    self.message_serial = 1
    self.pending_messages = []
    self.dirty_lands = set()
    self.dirty_header = False

    self.solve_days = set()
    self.last_incorrect_answer = None

    self.fastpasses_available = []
    self.fastpasses_used = {}

    self.pennies_earned = []
    self.pennies_collected = []
    self.coin_found = None

    self.last_hour = collections.deque()
    self.last_submit = 0
    self.last_solve = 0

    self.cached_bb_data = None
    self.cached_mapdata = {}
    self.cached_open_hints_data = None
    self.cached_errata_data = None
    self.cached_jukebox_data = None
    self.cached_admin_data = None

    self.admin_url = f"/admin/team/{username}"
    self.admin_html = f'<a href="{self.admin_url}">{html.escape(self.name)}</a>'

  def trim_last_hour(self, now):
    if not self.last_hour: return False

    changed = False
    when = now - 3600
    while self.last_hour and self.last_hour[0][0] < when:
      self.last_hour.popleft()
      changed = True
    return changed

  @classmethod
  async def realtime_trim_last_hour(cls):
    while True:
      await asyncio.sleep(20.0)
      now = time.time()
      for team in Team.all_teams():
        if team.trim_last_hour(now):
          team.invalidate()

  def get_admin_data(self):
    if self.cached_admin_data: return self.cached_admin_data

    self.trim_last_hour(time.time())
    d = {}
    for _, k in self.last_hour:
      d[k] = d.get(k, 0) + 1

    out = {"url": self.admin_url,
           "name": self.name,
           "name_sort": self.name_sort,
           "remote": self.remote_only,
           "score": self.score,
           "pennies": [len(self.pennies_earned) + len(self.pennies_collected),
                       len(self.pennies_collected),
                       len(self.pennies_earned)],
           "submits_hr": d.get("submit", 0),
           "solves_hr": d.get("solve", 0),
           "beam": len(self.open_puzzles),
           "last_submit": self.last_submit,
           "last_solve": self.last_solve,
           "fastpass": len(self.fastpasses_available),
           }

    self.cached_admin_data = out
    return out

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

  @save_state
  def update_phone(self, now, new_phone):
    self.admin_log.add(
      now, (f"Changed contact phone from "
            f"<b>{html.escape(self.attrs.get('phone', '(unknown)'))}</b> to "
            f"<b>{html.escape(new_phone)}</b>."))
    self.attrs["phone"] = new_phone
    self.invalidate()

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
    self.admin_log.add(now, f"<span class=\"adminnote\"><b>{user_fullname}</b> noted: {text}</span>")
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
    use_buzz = (self.outer_lands_state != "open")
    d = {"score": f"Buzz: {self.score * 1000:,}" if use_buzz else f"Wonder: {self.score*10000:,}",
         "lands": [[i.symbol, i.color, i.url, i.title] for i in self.sorted_open_lands],
         "passes": len(self.fastpasses_available),
         }
    if self.score_to_go and 0 < self.score_to_go <= 10:

      if self.score + self.score_to_go == CONSTANTS["outer_lands_score"]:
        num = self.score_to_go * 1000
        d["to_go"] = f"Generate <b>{num:,}</b> more Buzz to receive a special visit!"
      elif use_buzz:
        num = self.score_to_go * 1000
        d["to_go"] = f"Generate <b>{num:,}</b> more Buzz to unlock the next land!"
      else:
        num = self.score_to_go * 10000
        d["to_go"] = f"Generate <b>{num:,}</b> more Wonder to unlock the next land!"
    return d

  def get_mainmap_data(self, forced_lands=()):
    mainmap = Land.BY_SHORTNAME["mainmap"]

    if mainmap in self.cached_mapdata:
      #print(f" mapdata cache hit: {self.username} mainmap")
      return self.cached_mapdata[mainmap]
    #print(f"mapdata cache miss: {self.username} mainmap")

    items = []

    for i, land in enumerate(("canyon", "cascade", "safari", "studios")):
      if Land.BY_SHORTNAME[land] in self.open_lands:
        base_img = mainmap.base_img[4-i]
        base_size = mainmap.base_size[4-i]
        break
    else:
      base_img = mainmap.base_img[0]
      base_size = mainmap.base_size[0]

    mapdata = {"base_url": base_img,
               "shortname": mainmap.shortname,
               "width": base_size[0],
               "height": base_size[1]}

    for i in mainmap.icons.values():
      if (i.to_land not in self.open_lands and
          i.to_land not in forced_lands): continue
      d = { "name": i.to_land.title,
            "icon": i.name,
            "xywh": i.image.pos_size,
            "poly": i.image.poly,
            "url": i.to_land.url,
            "icon_url": i.image.url,
            "mask_url": i.mask.url,
            "offset": i.offset }
      if i.to_land.meta_puzzle:
        p = i.to_land.meta_puzzle
        ps = self.puzzle_state[p]
        if ps.state == PuzzleState.SOLVED:
          d["solved"] = True
          d["answer"] = ", ".join(sorted(p.display_answers[a] for a in ps.answers_found))
      items.append((("A", i.to_land.sortkey), d))

      if i.under:
        dd = {"icon_url": i.under.url,
              "xywh": i.under.pos_size}
        # Sort these before any puzzle title
        items.append((("@",), dd))

    # Add events
    e = mainmap.icons.get("events")
    if e:
      d = {"name": "Events",
           "icon": e.name,
           "xywh": e.image.pos_size,
           "poly": e.image.poly,
           "url": "/events",
           "icon_url": e.image.url,
           "mask_url": e.mask.url,
           "nolist": True,
           "offset": e.offset}
      items.append((("@",), d))

    # Add workshop
    e = mainmap.icons.get("workshop")
    if e:
      d = {"name": "Workshop",
           "icon": e.name,
           "xywh": e.image.pos_size,
           "poly": e.image.poly,
           "icon_url": e.image.url,
           "mask_url": e.mask.url,
           "offset": e.offset}

      ps = self.puzzle_state[Workshop.PUZZLE]
      if ps.state == PuzzleState.CLOSED:
        warning = mainmap.icons.get("warning")
        dd = {"icon_url": warning.image.url,
              "xywh": warning.image.pos_size}
        d["special"] = dd
        d["nolist"] = True
      else:
        d["url"] = "/workshop"
        d["spaceafter"] = True
        if ps.state == PuzzleState.SOLVED:
          d["solved"] = True
          d["answer"] = ", ".join(sorted(ps.puzzle.display_answers[a] for a in ps.answers_found))

      items.append((("@@",), d))

    # Add statue
    work = False
    if self.puzzle_state[Runaround.PUZZLE].state == PuzzleState.CLOSED:
      e = mainmap.icons.get("statue")
    else:
      e = mainmap.icons.get("statue_open")
      work = True
    if e:
      d = {"xywh": e.image.pos_size,
           "poly": e.image.poly,
           "icon_url": e.image.url,
           "icon": e.name,
           "offset": e.offset}
      if work:
        d["name"] = "Heart of the Park"
        d["url"] = "/heart_of_the_park"
        d["mask_url"] = e.mask.url
        d["spaceafter"] = True
      else:
        d["nolist"] = True
      items.append((("@",), d))

    # cloud + logo image overlaid on top
    for i, land in enumerate(
        ("bigtop", "yesterday", "balloons", "hollow", "space")):
      if Land.BY_SHORTNAME[land] in self.open_lands:
        cloud_img = mainmap.cloud_img[5-i]
        break
    else:
      cloud_img = mainmap.cloud_img[0]
    d = {"xywh": [0, 0] + base_size,
         "icon_url": cloud_img}
    items.append((("~",), d))

    items.sort(key=lambda i: i[0])
    for i, (sk, d) in enumerate(items):
      if i < len(items)-1 and sk[0] != items[i+1][0][0]:
        d["spaceafter"] = True
    mapdata["items"] = [i[1] for i in items]

    mapdata = json.dumps(mapdata)
    self.cached_mapdata[mainmap] = mapdata
    return mapdata


  def get_land_data(self, land):
    if land in self.cached_mapdata:
      print(f" mapdata cache hit: {self.username} {land.shortname}")
      return self.cached_mapdata[land]
    print(f"mapdata cache miss: {self.username} {land.shortname}")

    show_solved = self.attrs.get("show_solved", False)

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
      if land.shortname == "safari":
        # safari: opening tiger puzzle forces full map
        if self.puzzle_state[land.meta_puzzle].state != PuzzleState.CLOSED:
          need_base = 3
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
      iod = {"icon_url": io.image.url,
             "xywh": io.image.pos_size,
             "name": "Each animal has up to <b>five</b> answers!  To see how many an animal has, click the SUBMIT button."}

      i = land.icons["sign"]
      d = {"icon_url": i.image.url,
           "xywh": i.image.pos_size,
           "poly": i.image.poly,
           "special": iod}
      items.append(((-1, "@",), d))

    # This is a land map page (the items are puzzles).

    keepers = []

    for i in land.icons.values():
      if not i.puzzle: continue

      p = i.puzzle
      ps = self.puzzle_state[p]
      if ps.state == PuzzleState.CLOSED: continue

      d = {"name": p.title,
           "icon": i.name,
           "url": p.url,
           "icon_url": i.image.url,
           "mask_url": i.mask.url,
           "offset": i.offset}

      if hasattr(p, "keeper_answers"):
        # compute the position later
        d["xywh"] = None
        keepers.append((p.keeper_order, d, i.image.size))
      else:
        d["xywh"] = i.image.pos_size

      if i.image.poly: d["poly"] = i.image.poly

      if ps.answers_found:
        d["answer"] = ", ".join(sorted(p.display_answers[a] for a in ps.answers_found))

      if ps.state == PuzzleState.OPEN:
        if "answer" in d: d["answer"] += ", \u2026"
        d["solved"] = False
        if (now - ps.open_time < CONSTANTS["new_puzzle_seconds"] and
            ps.open_time != Global.STATE.event_start_time):
          d["new_open"] = ps.open_time + CONSTANTS["new_puzzle_seconds"]
      elif ps.state == PuzzleState.SOLVED:
        d["solved"] = True

      if show_solved:
        d["answer"] = ", ".join(sorted(p.display_answers.values()))
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

    items.sort(key=lambda i: i[0])
    for i, (sk, d) in enumerate(items):
      if i < len(items)-1 and sk[0] != items[i+1][0][0]:
        d["spaceafter"] = True
    mapdata["items"] = [i[1] for i in items]

    mapdata = json.dumps(mapdata)
    self.cached_mapdata[land] = mapdata
    return mapdata

  @classmethod
  def get_by_username(cls, username):
    return cls.BY_USERNAME.get(username)

  @classmethod
  def get_by_login_username(cls, username):
    x = cls.BY_USERNAME.get(username)
    if x: return x
    return cls.ALT_USERNAME.get(username)

  def get_submit_id(self):
    self.next_submit_id += 1
    return self.next_submit_id - 1

  @save_state
  def submit_answer(self, now, submit_id, shortname, answer):
    self.next_submit_id = max(self.next_submit_id, submit_id+1)

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

    self.last_hour.append((now, "submit"))
    self.last_submit = now
    self.cached_admin_data = None

    sub = Submission(now, submit_id, self, puzzle, answer)
    if not sub.answer: return ""
    if not ps.puzzle.allow_duplicates:
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

  @save_state
  def reset_spam(self, now, shortname, username):
    puzzle = Puzzle.get_by_shortname(shortname)
    if not puzzle: return
    user = login.AdminUser.get_by_username(username)
    ps = self.puzzle_state[puzzle]
    ps.reset_and_requeue(now, user)


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
        _, _, team, action = heapq.heappop(gfq)
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
  def bestow_fastpass(self, now, expire, sender):
    sender = login.AdminUser.get_by_username(sender)
    self.admin_log.add(now, f"Bestowed a PennyPass by <b>{sender.fullname}</b>.")
    self.receive_fastpass(now, expire)

  def receive_fastpass(self, now, expire, silent=False):
    self.fastpasses_available.append(now + expire)
    self.fastpasses_available.sort()
    heapq.heappush(self.GLOBAL_FASTPASS_QUEUE, (now+expire, self.username, self, None))
    if expire > 60:
      heapq.heappush(self.GLOBAL_FASTPASS_QUEUE,
                     (now+expire-60, self.username, self, ("1 minute", now+expire)))
    if expire > 300:
      heapq.heappush(self.GLOBAL_FASTPASS_QUEUE,
                     (now+expire-300, self.username, self, ("5 minutes", now+expire)))
    text = "Received a PennyPass."
    if not silent: self.activity_log.add(now, text)
    self.admin_log.add(now, text)
    if not silent and not save_state.REPLAYING:
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

  def open_puzzle(self, puzzle, now, opened_list):
    ps = self.puzzle_state[puzzle]
    if ps.state == PuzzleState.CLOSED:
      ps.state = PuzzleState.OPEN
      ps.open_time = now
      if opened_list is not None: opened_list.append(puzzle)
      self.open_puzzles.add(ps)
      puzzle.open_teams.add(self)
      puzzle.cached_admin_data = None
      self.cached_all_puzzles_data = None
      self.cached_errata_data = None
      self.cached_admin_data = None
      if puzzle.land.land_order < 1000:
        self.dirty_lands.add(puzzle.land.shortname)
        self.cached_mapdata.pop(puzzle.land, None)

  def solve_puzzle(self, puzzle, now):
    extra_response = []
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

      self.activity_log.add(now, f"{puzzle.html} solved.")
      self.last_hour.append((now, "solve"))
      self.last_solve = now

      if ps.hint_request_outstanding():
        ps.hints.append(HintMessage(ps, now, None, None, special="solved"))
        if self.current_hint_puzzlestate == ps:
          self.current_hint_puzzlestate = None
        self.cached_open_hints_data = None
        Global.STATE.task_queue.remove(ps)

      msg = {"method": "solve",
             "puzzle_id": puzzle.shortname,
             "title": html.escape(puzzle.title),
             "audio": puzzle.solve_audio,
      }
      if puzzle.solve_extra:
        msg.update(puzzle.solve_extra)
      self.send_messages([msg])

      self.dirty_lands.add(puzzle.land.shortname)
      self.cached_mapdata.pop(puzzle.land, None)
      self.cached_all_puzzles_data = None
      self.cached_jukebox_data = None
      self.cached_open_hints_data = None
      self.cached_admin_data = None
      if puzzle.meta:
        current_map = Land.BY_SHORTNAME["mainmap"]
        self.cached_mapdata.pop(current_map, None)
        self.dirty_lands.add("mainmap")
      self.invalidate(puzzle)

      if self.score >= CONSTANTS["outer_lands_score"] and self.outer_lands_state == "closed":
        if self.remote_only:
          self.complete_penny_visit(now)
        else:
          Global.STATE.add_task(now, self.username, f"penny-visit",
                                "Penny character visit", None,
                                self.complete_penny_visit, "visit")
          self.outer_lands_triggered = "triggered"
          extra_response.append("Expect a special visit soon!")
      if puzzle is Runaround.PUZZLE:
        extra_response.append(Runaround.solve_response)

      new_videos = 0
      for v, s in enumerate(CONSTANTS["videos_by_score"]):
        if self.score >= s:
          new_videos = max(new_videos, v+1)
      if new_videos > self.videos:
        self.videos = new_videos
        thumb = OPTIONS.static_content.get(f"thumb{self.videos}.png")
        self.activity_log.add(
          now,
          "A new Park History video is available!<br>"
          f"<a href=\"/about_the_park#history\"><img class=videothumb src=\"{thumb}\"></a>")
        self.send_messages([
          {"method": "video",
           "video_url": OPTIONS.static_content.get(f"video{self.videos}.mp4"),
           "thumb": thumb,
          }])

      # If this puzzle rewards you with a penny (land meta or events),
      # request a visit and/or record that you're owed a penny.
      if puzzle in Workshop.PENNY_PUZZLES:
        earned = self.earned_pennies()
        if earned:
          if self.remote_only:
            if self.puzzle_state[Workshop.PUZZLE].state == PuzzleState.CLOSED:
              self.admin_log.add(now, f"Skipped Loonie Toonie visit for remote-only team.")
              self.open_puzzle(Workshop.PUZZLE, now, None)
          else:
            if self.puzzle_state[Workshop.PUZZLE].state == PuzzleState.CLOSED:
              # No LT visit yet: "expect a visit soon"
              extra_response.append(Workshop.pre_response)
            else:
              # Workshop already open: "new thing in the workshop"
              extra_response.append(Workshop.post_response)

            dirty = False
            for penny in earned:
              if not self.pennies_earned and not self.pennies_collected:
                Global.STATE.add_task(now, self.username, f"loony-visit",
                                      "Loonie Toonie visit", None,
                                      self.complete_loony_visit, "visit")
                Global.STATE.add_task(now, self.username, f"penny-{penny.shortname}",
                                      f"First penny: {penny.name}", None,
                                      self.collect_penny, "penny")
              else:
                Global.STATE.add_task(now, self.username, f"penny-{penny.shortname}",
                                      f"Return penny: {penny.name}", None,
                                      self.collect_penny, "penny")
              self.pennies_earned.append(penny)
              dirty = True
            if dirty:
              self.send_messages([{"method": "pennies"}])

      if puzzle == Runaround.PUZZLE:
        Global.STATE.add_task(now, self.username, f"final-machine",
                              f"Machine interaction!", None,
                              self.complete_machine_interaction, "visit")

      solve_duration = ps.solve_time - ps.open_time
      puzzle.solve_durations[self] = solve_duration
      puzzle.median_solve_duration = statistics.median(puzzle.solve_durations.values())
      puzzle.adjust_hints_available_time()

      durtxt = util.format_duration(solve_duration)
      puzzle.puzzle_log.add(now, f"Solved by {ps.admin_html_team} ({durtxt}).")
      self.admin_log.add(now, f"{ps.admin_html_puzzle} solved ({durtxt}).")

      self.compute_puzzle_beam(now)
      if extra_response: return "<br>".join(extra_response)

  # Return any pennies that are newly-earned.
  def earned_pennies(self):
    out = []
    for penny in Workshop.ALL_PENNIES.values():
      if penny in self.pennies_collected: continue
      if penny in self.pennies_earned: continue
      for p in penny.puzzles:
        if self.puzzle_state[p].state != PuzzleState.SOLVED:
          break
      else:
        out.append(penny)
    return out

  def collect_penny(self, task, when):
    p = task.key.split("-")[-1]
    p = Workshop.ALL_PENNIES[p]
    self.pennies_earned.remove(p)
    self.pennies_collected.append(p)
    self.activity_log.add(when, f"Collected the <b>{p.name}</b> penny.")
    self.admin_log.add(when, f"Collected the <b>{p.name}</b> penny.")
    self.send_messages([{"method": "pennies"}])
    self.invalidate()
    if not save_state.REPLAYING:
      asyncio.create_task(self.flush_messages())

  def complete_loony_visit(self, task, when):
    self.admin_log.add(when, f"Completed the Loonie Toonie visit.")
    self.open_puzzle(Workshop.PUZZLE, when, None)
    self.cached_all_puzzles_data = None
    self.dirty_lands.add("mainmap")
    self.cached_mapdata.pop(Land.BY_SHORTNAME["mainmap"], None)
    self.invalidate(Workshop.PUZZLE)
    if not save_state.REPLAYING:
      asyncio.create_task(self.flush_messages())

  def complete_penny_visit(self, task, when):
    if self.remote_only:
      self.admin_log.add(when, f"Skipped Penny visit for remote-only team.")
    else:
      self.admin_log.add(when, f"Completed the Penny visit.")
    self.outer_lands_state = "open"
    self.compute_puzzle_beam(when)
    self.invalidate()
    if not save_state.REPLAYING:
      asyncio.create_task(self.flush_messages())

  def complete_machine_interaction(self, task, when):
    print("completed machine interaction")
    self.coin_found = when
    self.invalidate()

  @save_state
  def concierge_update(self, now, submit_id, result):
    puzzle = Puzzle.get_by_shortname("concierge_services")
    ps = self.puzzle_state[puzzle]

    sub = None
    if ps.submissions and ps.submissions[-1].submit_id == submit_id:
      sub = ps.submissions[-1]
    else:
      for s in ps.submissions:
        if s.submit_id == submit_id:
          sub = s
          break
    if not sub: return None
    print(f"sub is {sub}")

    if result == "no_answer":
      sub.state = "no answer"
      sub.extra_response = ("We did not reach you when we called.  Please check your "
                            "team contact number on the Guest Services page and submit again.")
    elif result == "wrong_number":
      sub.state = "wrong number"
      sub.extra_response = ("We did not reach you when we called.  Please check your "
                            "team contact number on the Guest Services page and submit again.")
    elif sub.answer in sub.puzzle.answers:
      sub.state = Submission.CORRECT
      sub.check_answer_correct(now)
    else:
      sub.state = "complete"

  def get_puzzle_state(self, puzzle):
    if isinstance(puzzle, str):
      puzzle = Puzzle.get_by_shortname(puzzle)
      if not puzzle: return None
    return self.puzzle_state[puzzle]

  def invalidate(self, puzzle=None, flush=True):
    self.cached_bb_data = None
    self.cached_admin_data = None
    if puzzle: puzzle.cached_admin_data = None
    login.AdminUser.notify_update(self, puzzle, flush=flush)

  def get_jukebox_data(self):
    if self.cached_jukebox_data: return self.cached_jukebox_data

    data = []
    j = Puzzle.get_by_shortname("jukebox")

    for item in j.extra:
      p = item["puzzle"]
      if self.puzzle_state[p].state == PuzzleState.SOLVED:
        d = copy.copy(item)
        d.pop("puzzle")
        d.pop("i")
        data.append(d)

    self.cached_jukebox_data = data
    return data

  BB_PUZZLE_COLOR = {PuzzleState.CLOSED: "#dddddd",
                     PuzzleState.OPEN: "#ffdd66",
                     PuzzleState.SOLVED: "#009900"}

  @classmethod
  def bb_label_info(cls):
    if cls.cached_bb_label_info:
      return cls.cached_bb_label_info

    land_offsets = []
    lx = 0
    for land in Land.ordered_lands + [MiscLand.get()]:
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
            if ny == 5:
              nx += 1
              ny = 0
            if nx > 1 or ny > 1: break
      lx += cx + 30
    cls.cached_bb_label_info = land_offsets
    return land_offsets

  def bb_data(self):
    def state_from_ps(ps):
      if ps.state == "open":
        if ps.hints_available:
          if ps.hints:
            return "open-hint"
          else:
            return "available"
        else:
          return "open"
      elif ps.state == "closed":
        return "closed"
      else:
        if ps.hints:
          return "solved-hint"
        else:
          return "solved"

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
          st = state_from_ps(ps)
          if p.meta:
            out.append(f'<circle cx="{lx+14.5}" cy="14.5" r="12" class="bb-{st} bbp-{p.bbid}"/>')
          else:
            cx = nx * 15 + 7
            cy = ny * 15 + 7
            if p in land.additional_puzzles or p.submeta:
              out.append(f'<rect x="{lx+cx-4}" y="{cy-4}" width="8" height="8" class="bb-{st} bbp-{p.bbid}"/>')
            else:
              out.append(f'<circle cx="{lx+cx}" cy="{cy}" r="5" class="bb-{st} bbp-{p.bbid}"/>')

            while True:
              ny += 1
              if ny == 5:
                nx += 1
                ny = 0
              if nx > 1 or ny > 1: break
        lx += cx + 30

      land = MiscLand.get()
      lx = [x["left"] for x in self.bb_label_info() if x["symbol"] == land.symbol][0]
      for (p, cy, r) in zip(land.all_puzzles, (7, 29.5, 59.5), (5, 9, 12)):
        ps = self.puzzle_state[p]
        st = state_from_ps(ps)
        out.append(f'<circle cx="{lx+14.5}" cy="{cy}" r="{r}" class="bb-{st} bbp-{p.bbid}"/>')

      if self.coin_found:
        out.append(f'<g transform="translate({lx+14.5} {cy}) scale(1 -1)">'
                   '<path d="M0 11L6.47 -8.9L-10.46 3.4L10.46 3.4L-6.47 -8.9z" fill="yellow"/>'
                   f'</g>')
      lx += 30

      out.insert(0, f'<svg xmlns="http://www.w3.org/2000/svg" width="{lx}" height="74" viewBox="0 0 {lx} 74">')
      out.append("</g></svg>")
      svg = "".join(out)
      self.cached_bb_data["svg"] = svg

    return self.cached_bb_data

  def get_open_hints_data(self):
    if self.cached_open_hints_data is not None:
      return self.cached_open_hints_data

    oh = []
    for p in sorted(self.hints_open, key=lambda p: p.sortkey):
      ps = self.puzzle_state[p]
      if ps.state == PuzzleState.SOLVED and not ps.hints: continue
      oh.append([p.shortname, p.title, ps.state == PuzzleState.SOLVED])

    d = {"available": oh}
    if self.current_hint_puzzlestate:
      d["current"] = self.current_hint_puzzlestate.puzzle.shortname
    else:
      d["current"] = None
    self.cached_open_hints_data = d

    return self.cached_open_hints_data

  def open_hints(self, now, puzzle):
    ps = self.puzzle_state[puzzle]
    if ps.hints_available: return
    if ps.state == PuzzleState.SOLVED: return
    ps.hints_available = True
    self.hints_open.add(puzzle)
    self.cached_open_hints_data = None
    self.cached_bb_data = None
    self.invalidate(puzzle, flush=False)
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

    msg = HintMessage(ps, now, sender, None, special="ack")
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
      if text is None:
        self.current_hint_puzzlestate = None
        puzzle.puzzle_log.add(now, f"{ps.admin_html_team} canceled their hint request.")
        self.activity_log.add(now, f"Canceled the hint request on {puzzle.html}.")
        self.admin_log.add(now, f"Canceled the hint request on {ps.admin_html_puzzle}.")
        ps.hints.append(HintMessage(ps, now, sender, None, special="cancel"))
        Global.STATE.task_queue.remove(ps)
      else:
        self.current_hint_puzzlestate = ps
        if ps.hints:
          puzzle.puzzle_log.add(now, f"{ps.admin_html_team} requested a followup hint.")
          self.activity_log.add(now, f"Requested a followup hint on {puzzle.html}.")
          self.admin_log.add(now, f"Requested a followup hint on {ps.admin_html_puzzle}.")
        else:
          puzzle.puzzle_log.add(now, f"{ps.admin_html_team} requested a hint.")
          self.activity_log.add(now, f"Requested a hint on {puzzle.html}.")
          self.admin_log.add(now, f"Requested a hint on {ps.admin_html_puzzle}.")
        ps.hints.append(HintMessage(ps, now, sender, text))
        Global.STATE.task_queue.add(ps)
    else:
      self.current_hint_puzzlestate = None
      sender = login.AdminUser.get_by_username(sender)
      ps.last_hq_sender = sender
      ps.claim = None
      hm = HintMessage(ps, now, sender, text)
      ps.hints.append(hm)
      Global.STATE.task_queue.remove(ps)
      ps.puzzle.hint_replies.append(hm)
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

  @save_state
  def open_all_lands(self, now):
    if not self.force_all_lands_open:
      self.force_all_lands_open = True
      self.compute_puzzle_beam(now)
      self.invalidate()

  @save_state
  def open_all_puzzles(self, now):
    if not self.force_all_puzzles_open:
      self.force_all_puzzles_open = True
      self.compute_puzzle_beam(now)
      self.invalidate()

  # BEAM!
  def compute_puzzle_beam(self, now):
    opened = []
    locked = []

    min_score_to_go = None

    since_start = now - Global.STATE.event_start_time
    for land in Land.ordered_lands:
      if not land.puzzles: continue

      open_count = self.fastpasses_used.get(land, 0)

      if self.force_all_puzzles_open:
        open_count = 1000
      else:
        if (self.force_all_lands_open or
            (since_start >= land.open_at_time or
             (self.score >= land.open_at_score and
              (land.open_at_score < CONSTANTS["outer_lands_score"] or
               self.outer_lands_state == "open")))):
          open_count += land.initial_puzzles

      if open_count == 0:
        to_go = land.open_at_score - self.score
        if min_score_to_go is None or min_score_to_go > to_go:
          min_score_to_go = to_go
        continue

      stop_after = 1000
      skip12 = False
      if not self.force_all_puzzles_open and land.shortname == "cascade":
        skip12 = True
        if self.puzzle_state[land.first_submeta].state == PuzzleState.SOLVED:
          self.open_puzzle(land.second_submeta, now, opened)
          if self.puzzle_state[land.second_submeta].state == PuzzleState.SOLVED:
            self.open_puzzle(land.meta_puzzle, now, opened)
          else:
            stop_after = 13
        else:
          stop_after = 9

      for i, p in enumerate(land.puzzles):
        if i >= stop_after: break
        if skip12 and 1 <= i <= 2: continue
        if self.puzzle_state[p].state == PuzzleState.CLOSED:
          if open_count > 0 or p.meta or p.submeta:
            self.open_puzzle(p, now, opened)
          else:
            break
        if self.puzzle_state[p].state == PuzzleState.OPEN:
          if not p.meta and not p.submeta:
            open_count -= 1

    safari = Land.BY_SHORTNAME.get("safari", None)
    if safari and (safari in self.open_lands or self.force_all_puzzles_open):
      answers = set()
      keepers_solved = 0
      for p in safari.puzzles:
        answers.update(self.puzzle_state[p].answers_found)
      for kp in safari.keepers:
        kps = self.puzzle_state[kp]
        if kps.state == PuzzleState.SOLVED:
          keepers_solved += 1
        elif kps.state == PuzzleState.CLOSED:
          if self.force_all_puzzles_open:
            self.open_puzzle(kp, now, opened)
          else:
            count = sum(1 for a in kp.keeper_answers if a in answers)
            if kps.keeper_answers == 0 and count >= kp.keeper_needed:
              kps.keeper_answers = min(len(answers)+2, safari.total_keeper_answers)
            if 0 < kps.keeper_answers <= len(answers):
              self.open_puzzle(kp, now, opened)
      meta = Puzzle.get_by_shortname("safari_adventure")
      if (meta and self.puzzle_state[meta].state == PuzzleState.CLOSED and
          (keepers_solved >= 5 or self.force_all_puzzles_open)):
        self.open_puzzle(meta, now, opened)

    if self.puzzle_state[Runaround.PUZZLE].state == PuzzleState.CLOSED:
      for p in Runaround.REQUIRED_PUZZLES:
        if self.puzzle_state[p].state != PuzzleState.SOLVED:
          break
      else:
        # Open the runaround!
        self.open_puzzle(Runaround.PUZZLE, now, opened)
        self.invalidate(Runaround.PUZZLE)
        self.cached_all_puzzles_data = None
        self.dirty_lands.add("mainmap")
        self.cached_mapdata.pop(Land.BY_SHORTNAME["mainmap"], None)

    lands_opened = set()
    for st in self.puzzle_state.values():
      if st.state != PuzzleState.CLOSED:
        if st.puzzle.land.land_order >= 1000: continue
        if st.puzzle.land not in self.open_lands:
          self.open_lands[st.puzzle.land] = now
          st.puzzle.land.open_teams.add(self)
          self.sorted_open_lands = [land for land in self.open_lands.keys() if land.land_order]
          self.sorted_open_lands.sort(key=lambda land: land.land_order)
          self.dirty_lands.add("mainmap")
          self.cached_mapdata.pop(Land.BY_SHORTNAME["mainmap"], None)
          self.dirty_header = True
          lands_opened.add(st.puzzle.land)
          if now != Global.STATE.event_start_time:
            title = html.escape(st.puzzle.land.title)
            self.send_messages([{"method": "open_land",
                                 "title": title,
                                 "land": st.puzzle.land.shortname}])

    if lands_opened:
      self.send_messages([{"method": "update_fastpass",
                           "fastpass": self.get_fastpass_data()}])

    for puzzle in opened:
      ps = self.puzzle_state[puzzle]

      if puzzle.land in lands_opened:
        lands_opened.discard(puzzle.land)
        title = html.escape(puzzle.land.title)
        self.activity_log.add(now, f"<b>{title}</b> is now open!")

      puzzle.puzzle_log.add(now, f"Opened by {ps.admin_html_team}.")
      self.activity_log.add(now, f"{puzzle.html} opened.")
      self.admin_log.add(now, f"{ps.admin_html_puzzle} opened.")


    current_map = Land.BY_SHORTNAME["mainmap"]
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
    self.offset = d.get("offset", [0,0,0])
    if len(self.offset) == 2:
      self.offset.append(0)

    for opt in ("image", "mask", "under",
                "emptypipe1", "fullpipe1",
                "emptypipe2", "fullpipe2",
                "emptypipe0", "fullpipe0"):
      s = d.get(opt)
      if s:
        setattr(self, opt, Subicon(s))
      else:
        setattr(self, opt, None)

    assert getattr(self, "image")

class Land:
  BY_SHORTNAME = {}

  def __init__(self, shortname, cfg, event_dir):
    print(f"  Adding land \"{shortname}\"...")

    self.BY_SHORTNAME[shortname] = self
    self.shortname = shortname
    self.title = cfg["title"]
    self.sortkey = (util.make_sortkey(self.title), id(self))
    self.logo = cfg.get("logo")
    self.symbol = cfg.get("symbol", None)
    self.land_order = cfg.get("land_order")
    self.color = cfg.get("color")
    self.guess_interval = cfg.get("guess_interval", CONSTANTS["default_guess_interval_sec"])
    self.guess_max = cfg.get("guess_max", CONSTANTS["default_guess_max"])
    self.open_at_score, self.open_at_time = cfg.get("open_at", (None, None))
    self.time_unlocked = False
    if self.open_at_time:
      self.open_at_time = int(self.open_at_time * CONSTANTS["time_scale"])
    if "assignments" in cfg:
      self.initial_puzzles = cfg["initial_puzzles"]

    self.base_img = cfg["base_img"]
    self.base_size = cfg["base_size"]

    self.cloud_img = cfg.get("cloud_img")

    if shortname == "mainmap":
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

    self.open_teams = set()

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

    for i, land in enumerate(cls.ordered_lands):
      for j, p in enumerate(land.all_puzzles):
        p.release_order = (i+1) * 100 + (j+1)

    jukebox = Puzzle.get_by_shortname("jukebox")
    land = cls.BY_SHORTNAME.get("yesterday", None)
    if jukebox and land:
      by_icon = {}
      for item in jukebox.extra:
        by_icon[item["i"]] = item
      for p in land.puzzles:
        item = by_icon.get(p.icon.name)
        if item:
          item["puzzle"] = p

    for land in cls.BY_SHORTNAME.values():
      for p in land.all_puzzles:
        if not p.style:
          if OPTIONS.debug:
            p.style = land.shortname + "/land.css"
          else:
            p.style = land.shortname + "/land-compiled.css"


class Puzzle:
  BY_SHORTNAME = {}
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
    self.hints_available_time = CONSTANTS["failsafe_hint_time"] * CONSTANTS["time_scale"]
    self.hints_available_time_auto = True
    self.emojify = False
    self.explanations = {}
    self.puzzle_log = Log()
    self.zip_version = None
    self.allow_duplicates = False
    self.wait_for_requested = False
    self.style = None
    self.solve_audio = None
    self.solve_extra = None

    self.median_solve_duration = None
    self.solve_durations = {}     # {team: duration}
    self.incorrect_answers = {}   # {answer: {teams}}
    self.incorrect_counts = []    # [(count, answer)]
    self.open_teams = set()
    self.submitted_teams = set()
    self.errata = []
    self.hint_replies = []

    self.cached_admin_data = None

    save_state.add_instance("Puzzle:" + shortname, self)

  def get_admin_data(self):
    if self.cached_admin_data: return self.cached_admin_data

    out = {"url": self.admin_url,
           "title": self.title,
           "title_sort": self.title_sortkey,
           "symbol": self.land.symbol,
           "color": self.land.color,
           "order": self.release_order,
           "hint_time": self.hints_available_time,
           "hint_time_auto": self.hints_available_time_auto,
           "open_count": len(self.open_teams),
           "submitted_count": len(self.submitted_teams),
           "solved_count": len(self.solve_durations),
           "unsolved_count": len(self.open_teams) - len(self.solve_durations),
           "errata": True if self.errata else False,
           "median_solve": self.median_solve_duration,
           "incorrect_count": sum(i[0] for i in self.incorrect_counts),
           }

    self.cached_admin_data = out
    return out

  def post_init(self, land, icon):
    self.land = land
    self.icon = icon
    if self.meta:
      group = 0
    elif hasattr(self, "keeper_answers") or self.submeta:
      group = 1
    else:
      group = 2
    self.title_sortkey = util.make_sortkey(self.title)
    self.sortkey = (group, self.title_sortkey, id(self))
    self.bbid = Puzzle.NEXT_BBID
    Puzzle.NEXT_BBID += 1

    self.html_title = html.escape(self.title)
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

    if self.shortname == "concierge_services":
      self.handle_answer = self.do_concierge_callback
      self.allow_duplicates = True
      self.wait_for_requested = True

    land_audio = OPTIONS.static_content.get(land.shortname + "/solve.mp3")
    if not self.solve_audio and land_audio: self.solve_audio = land_audio

  def do_concierge_callback(self, sub, now):
    sub.state = sub.REQUESTED
    d = {"phone": sub.team.attrs.get("phone", "(unknown)"),
         "team": sub.team.name,
         "answer": sub.answer,
         "u": sub.team.username,
         "s": sub.submit_id}
    url = ("https://mitmh-2019-leftout-cg.netlify.com/callbacks/callbacks.html?" +
           urllib.parse.urlencode(d))
    Global.STATE.add_task(now, sub.team.username, f"concierge-callback-{sub.submit_id}",
                          "Concierge callback", url, None, "puzzle")

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
    self.max_queued = j.get("max_queued", CONSTANTS["default_max_queued"])
    self.extra = j.get("extra")
    self.scrum = j.get("scrum", False)
    if self.scrum:
      self.title = "TEAMWORK TIME: " + self.title

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
    self.max_queued = j.get("max_queued", CONSTANTS["default_max_queued"])

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
  def open_hints_for(self, now, team_usernames):
    for t in team_usernames:
      t = Team.get_by_username(t)
      t.open_hints(now, self)
    if not save_state.REPLAYING and team_usernames:
      asyncio.create_task(login.AdminUser.flush_messages())

  @save_state
  def set_hints_available_time(self, now, new_time, admin_user):
    self.hints_available_time_auto = False
    self.hints_available_time = new_time
    admin_user = login.AdminUser.get_by_username(admin_user)
    self.puzzle_log.add(now, f"Hint time set to {util.format_duration(new_time)} by {admin_user.fullname}.")
    if not save_state.REPLAYING:
      self.maybe_open_hints(now)
      self.invalidate()

  def adjust_hints_available_time(self):
    if not self.hints_available_time_auto: return
    N = CONSTANTS["hint_available_solves"]
    if len(self.solve_durations) < N: return
    dur = list(self.solve_durations.values())
    heapq.heapify(dur)
    m = max(heapq.nsmallest(N, dur))
    m = max(m, CONSTANTS["no_hints_before"] * CONSTANTS["time_scale"])
    self.hints_available_time = m
    if not save_state.REPLAYING:
      self.invalidate()

  def invalidate(self, flush=True):
    self.cached_admin_data = None
    d = {"method": "update",
         "puzzle_id": self.shortname}
    login.AdminUser.send_messages([d], flush=flush)

  def maybe_open_hints(self, now):
    if not Global.STATE.event_start_time: return
    open_time = now - Global.STATE.event_start_time
    if open_time < CONSTANTS["global_no_hints_before"] * CONSTANTS["time_scale"]: return

    open_for = []
    for t in Team.all_teams():
      ps = t.puzzle_state[self]
      if (ps.state == PuzzleState.OPEN and
          not ps.hints_available and
          now - ps.open_time >= self.hints_available_time):
        open_for.append(t)
    if open_for:
      print(f"opening hints for {len(open_for)} team(s)")
      ps.puzzle.open_hints_for([t.username for t in open_for])
      for t in open_for:
        asyncio.create_task(t.flush_messages())

  def get_hint_reply_data(self, last=None):
    out = []
    for hm in reversed(self.hint_replies):
      d = {"when": hm.when, "text": hm.text,
           "team": hm.parent.team.name,
           "sender": hm.sender.fullname}
      out.append(d)
    return out

  EXTRA_ALLOWED_CHARS = None

  @classmethod
  def canonicalize_answer(cls, text):
    text = unicodedata.normalize("NFD", text.upper())
    out = []
    for k in text:
      cat = unicodedata.category(k)
      # Letters, "other symbols", or specific characters needed for complex emojis
      if cat == "So" or cat[0] == "L" or k in cls.EXTRA_ALLOWED_CHARS:
        out.append(k)
    return "".join(out)

  @staticmethod
  def respace_text(text):
    if text is None: return None
    if text is True: return True
    if isinstance(text, dict):
      out = {}
      for k, v in text.items():
        if k.endswith("url"):
          out[k] = v
        else:
          out[k] = Puzzle.respace_text(v)
      return out
    else:
      return " ".join(text.split()).strip()

  @classmethod
  async def realtime_open_hints(cls):
    while True:
      await asyncio.sleep(10.0)

      now = time.time()

      if not Global.STATE.event_start_time: continue
      open_time = now - Global.STATE.event_start_time
      if open_time < CONSTANTS["global_no_hints_before"] * CONSTANTS["time_scale"]: continue

      needs_flush = set()
      for p in Puzzle.all_puzzles():
        open_for = []
        for t in p.open_teams:
          ps = t.puzzle_state[p]
          if ps.state == PuzzleState.SOLVED: continue
          if not ps.hints_available and now - ps.open_time >= ps.puzzle.hints_available_time:
            open_for.append(t.username)
            needs_flush.add(t)
        if open_for:
          p.open_hints_for(open_for)

      for t in needs_flush:
        asyncio.create_task(t.flush_messages())


class Erratum:
  def __init__(self, when, puzzle, text, sender):
    self.when = when
    self.puzzle = puzzle
    self.text = text
    self.sender = sender

    self.json = {"when": self.when,
                 "puzzle_id": self.puzzle.shortname,
                 "title": self.puzzle.title,
                 "sender": self.sender.fullname,
                 "text": self.text}

    if text:
      puzzle.errata.insert(0, self)

  def to_json(self):
    return self.json


class Global:
  STATE = None

  # Start preloading images this long before puzzles open.
  PRELOAD_ADVANCE = 45
  # Spread preloading out over this many seconds.
  PRELOAD_SPREAD = 30

  SUBMIT_LOG_FILE = None

  @classmethod
  def set_submit_log_filename(cls, fn):
    cls.SUBMIT_LOG_FILE = fn

  @save_state
  def __init__(self, now):
    self.options = None
    self.hunt_closed = False
    self.event_start_time = None
    self.expected_start_time = int(now + OPTIONS.start_delay)
    Global.STATE = self
    asyncio.create_task(self.future_start())
    asyncio.create_task(self.future_send_preload())

    self.stopping = False
    self.stop_cv = asyncio.Condition()

    self.task_queue = TaskQueue()

    self.errata = []
    self.reloads = []
    self.cached_errata_data = None
    self.preload_urls = None

    self.submit_log = None
    self.submit_writer = None

    if self.SUBMIT_LOG_FILE:
      self.submit_log = open(self.SUBMIT_LOG_FILE, "w")
      self.submit_writer = csv.writer(self.submit_log)
      self.submit_writer.writerow(["time", "unix_time", "team", "puzzle",
                                   "input", "canonical", "result"])

  def log_submit(self, when, team_username, shortname,
                 answer, canonical_answer, result):
    if not self.submit_writer: return
    w = datetime.datetime.fromtimestamp(when)
    when_fmt = w.strftime("%Y-%m-%d %H:%M:%S")
    self.submit_writer.writerow([when_fmt, when, team_username, shortname,
                                 answer, canonical_answer, result])
    self.submit_log.flush()


  @save_state
  def compute_all_beams(self, now):
    for team in Team.all_teams():
      team.compute_puzzle_beam(now)
      team.invalidate()

  @save_state
  def update_lands(self, now, scores, times, counts):
    for i, land in enumerate(Land.ordered_lands):
      land.open_at_score = scores[i]
      land.open_at_time = times[i]
      land.initial_puzzles = counts[i]

    if self.event_start_time:
      for team in Team.all_teams():
        team.compute_puzzle_beam(now)
        team.invalidate()

  @save_state
  def post_erratum(self, now, shortname, text, sender):
    if not text: return
    puzzle = Puzzle.get_by_shortname(shortname)
    if not puzzle: return
    sender = login.AdminUser.get_by_username(sender)
    if not sender: return
    self.errata.insert(0, Erratum(now, puzzle, text, sender))
    self.cached_errata_data = None

    puzzle.puzzle_log.add(now, f"An erratum was posted by <b>{sender.fullname}</b>.")

    for t in puzzle.open_teams:
      t.activity_log.add(now, f"An erratum was posted for {puzzle.html}.")

  @save_state
  def save_reload(self, now, shortname, sender):
    puzzle = Puzzle.get_by_shortname(shortname)
    if not puzzle: return
    sender = login.AdminUser.get_by_username(sender)
    if not sender: return
    self.reloads.append(Erratum(now, puzzle, "", sender))
    self.cached_errata_data = None

    puzzle.puzzle_log.add(now, f"Puzzle was reloaded by <b>{sender.fullname}</b>.")

  @save_state
  def close_hunt(self, now):
    self.hunt_closed = True

  def get_errata_data(self):
    if self.cached_errata_data is None:
      data = [e.to_json() for e in itertools.chain(self.errata, self.reloads)]
      data.sort(key=lambda x: x["when"])
      self.cached_errata_data = data
    return self.cached_errata_data

  async def stop_server(self):
    async with self.stop_cv:
      self.stopping = True
      self.stop_cv.notify_all()

  @save_state
  def update_event_start(self, now, when):
    if self.event_start_time: return
    self.expected_start_time = when
    asyncio.create_task(self.future_start())
    asyncio.create_task(self.future_send_preload())
    asyncio.create_task(self.update_event_start_teams())

  async def future_start(self):
    delay = self.expected_start_time - time.time()
    if delay > 0:
      await asyncio.sleep(delay)
    now = time.time()
    if not self.event_start_time and now >= self.expected_start_time:
      self.start_event(True)

  async def future_send_preload(self):
    delay = self.expected_start_time - self.PRELOAD_ADVANCE - time.time()
    if delay > 0:
      await asyncio.sleep(delay)
    if not self.preload_urls: return
    now = time.time()
    if (not self.event_start_time and
        now >= self.expected_start_time - self.PRELOAD_ADVANCE):
      msg = [{"method": "preload", "maps": self.preload_urls,
              "spread": self.PRELOAD_SPREAD}]
      for t in Team.all_teams():
        t.send_messages(msg)
        await t.flush_messages()

  @save_state
  def start_event(self, now, timed):
    if self.event_start_time is not None: return
    self.event_start_time = now
    self.event_hash = hashlib.md5(str(now).encode("ascii")).hexdigest()[:8]
    print(f"starting event at {now} hash is {self.event_hash}")
    for team in Team.BY_USERNAME.values():
      team.receive_fastpass(now, CONSTANTS["pennypass_expiration"] * CONSTANTS["time_scale"], silent=True)
      team.compute_puzzle_beam(self.event_start_time)
      team.open_puzzle(Event.PUZZLE, now, None)
      team.invalidate(flush=False)
    if timed and not save_state.REPLAYING:
      asyncio.create_task(self.notify_event_start())
    asyncio.create_task(login.AdminUser.flush_messages())

  def add_task(self, now, team, taskname, text, url, oncomplete, kind):
    team = Team.get_by_username(team)
    if not team: return
    self.task_queue.add_task(now, team, taskname, text, url, oncomplete, kind)

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

  def mark_task_complete(self, task_key, undo):
    if undo:
      self.task_queue.pending_removal.pop(task_key, None)
    else:
      delay = CONSTANTS["undo_done_sec"]
      self.task_queue.pending_removal[task_key] = time.time() + delay
      asyncio.create_task(self.task_queue.purge(delay))
    self.task_queue.change()

  @save_state
  def complete_task(self, now, task_key):
    task = Global.STATE.task_queue.remove_task(task_key)
    if task and task.oncomplete:
      task.oncomplete(task, now)

  async def notify_event_start(self):
    for team in Team.BY_USERNAME.values():
      team.send_messages([{"method": "to_page", "url": "/"}])
      await team.flush_messages()

  async def update_event_start_teams(self):
    for team in Team.BY_USERNAME.values():
      team.send_messages([{"method": "update_start", "new_start": self.expected_start_time}])
      await team.flush_messages()

  def bb_task_queue_data(self):
    return self.task_queue.get_bb_data()

  def maybe_preload(self):
    if self.event_start_time:
      print("Skipping preload; event has started.")
      return

    initial_lands = [land for land in Land.ordered_lands if land.open_at_score == 0]
    print(f"Initial lands: {initial_lands}")

    for t in Team.all_teams():
      if t.force_all_lands_open: continue
      if t.force_all_puzzles_open: continue
      map_data = t.get_mainmap_data(forced_lands=initial_lands)
      break

    map_data = json.loads(map_data)
    urls = [map_data["base_url"]]
    for d in map_data["items"]:
      u = d.get("icon_url")
      if u: urls.append(u)
      u = d.get("mask_url")
      if u: urls.append(u)

    self.preload_urls = urls


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
    self.all_puzzles = []

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
    p.style = "default.css"
    p.solve_audio = OPTIONS.static_content.get("events_solve.mp3")

    p.title = "Events"
    p.url = "/events"
    p.answers = {e.answer for e in cls.ALL_EVENTS}
    p.display_answers = dict((e.answer, e.display_answer) for e in cls.ALL_EVENTS)
    p.responses = {}
    p.html_body = None
    p.html_head = None
    p.for_ops_url = ""
    p.max_queued = CONSTANTS["default_max_queued"]
    p.meta = False
    p.submeta = False
    p.points = 0  # no buzz/wonder for finishing
    p.hints_available_time = 96 * 3600
    p.hints_available_solves = 1000
    p.release_order = 0

    def on_correct_answer(now, team):
      team.receive_fastpass(now, CONSTANTS["pennypass_expiration"] * CONSTANTS["time_scale"])
      ps = team.puzzle_state[cls.PUZZLE]
      completed = [e.answer in ps.answers_found for e in cls.ALL_EVENTS]
      team.send_messages([{"method": "event_complete", "completed": completed}])

    p.on_correct_answer = on_correct_answer

    land = MiscLand.get()
    land.all_puzzles.append(p)
    p.post_init(land, None)

    e = [e for e in cls.ALL_EVENTS if e.time == "__special__"][0]
    e.team_time = {}

    teams_by_size = [((t.size, id(t)), t) for t in Team.all_teams()]
    teams_by_size.sort()
    half = (len(teams_by_size)+1) // 2
    for i, (_, t) in enumerate(teams_by_size):
      if i < half:
        e.team_time[t] = "11am Saturday"
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
    cls.config = d

  def __init__(self, shortname, d):
    self.shortname = shortname
    self.name = d["name"]
    p = d["puzzle"]
    if isinstance(p, str):
      self.puzzles = {d["puzzle"]}
    else:
      self.puzzles = set(d["puzzle"])

    self.ALL_PENNIES[shortname] = self

  @classmethod
  def submit_filter(cls, ps):
    return len(ps.team.pennies_collected) == len(cls.ALL_PENNIES)

  @classmethod
  def post_init(cls):
    missing = []
    for penny in cls.ALL_PENNIES.values():
      pset = set()
      for shortname in penny.puzzles:
        pp = Puzzle.get_by_shortname(shortname)
        if not pp:
          missing.append(shortname)
        pset.add(pp)
        cls.PENNY_PUZZLES.add(pp)
      penny.puzzles = pset

    if missing:
      raise ValueError(f"missing pennies: {', '.join(missing)}")

    p = Puzzle("workshop")
    cls.PUZZLE = p

    p.oncall = ""
    p.puzzletron_id = -1
    p.authors = ["Left Out"]
    p.style = "default.css"
    p.solve_audio = OPTIONS.static_content.get("reveal.mp3")
    p.solve_extra = {"url": OPTIONS.static_content.get("reveal_under.png"),
                     "video_url": OPTIONS.static_content.get("reveal_over.png"),
                     "to_go": "/heart_of_the_park",
                     "text": "<b>Workshop</b> was solved!"}

    p.title = "Workshop"
    p.url = "/workshop"
    da = cls.config["answer"]
    a = Puzzle.canonicalize_answer(da)
    p.answers = {a}
    p.display_answers = {a: da}
    p.responses = {}
    p.html_body = None
    p.html_head = None
    p.for_ops_url = ""
    p.max_queued = CONSTANTS["default_max_queued"]
    p.meta = False
    p.submeta = False
    p.points = 0  # no buzz/wonder for finishing
    p.hints_available_time = 96 * 3600
    p.hints_available_solves = 1000
    p.release_order = 10000

    p.submit_filter = cls.submit_filter

    land = MiscLand.get()
    land.all_puzzles.append(p)
    p.post_init(land, None)


class Runaround:
  SEGMENTS = []
  # All these puzzles must be solved to start the Runaround.
  REQUIRED_PUZZLES = set()

  def __init__(self, d):
    self.shortname = d["land"]
    self.land = Land.BY_SHORTNAME[self.shortname]
    self.title = self.land.title
    self.answer = Puzzle.canonicalize_answer(d["answer"])
    self.display_answer = d["answer"]
    self.instructions = d["instructions"]

  @classmethod
  def build(cls, d):
    for dd in d["minis"]:
      cls.SEGMENTS.append(Runaround(dd))
    cls.solve_response = d["solve_response"]

  @classmethod
  def post_init(cls):
    p = Puzzle("runaround")
    cls.PUZZLE = p

    p.oncall = ""
    p.puzzletron_id = -1
    p.authors = ["Left Out"]
    p.style = "runaround.css"
    p.solve_audio = OPTIONS.static_content.get("end_solve.mp3")

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
    p.max_queued = CONSTANTS["default_max_queued"]
    p.meta = False
    p.submeta = False
    p.points = 0  # no buzz/wonder for finishing
    p.hints_available_time = 96 * 3600
    p.hints_available_solves = 1000
    p.release_order = 10001

    def on_correct_answer(now, team):
      ps = team.puzzle_state[cls.PUZZLE]
      segments = {}
      for s in cls.SEGMENTS:
        if s.answer in ps.answers_found:
          segments[s.shortname] = {"answer": s.display_answer,
                                   "instructions": s.instructions}
      team.send_messages([{"method": "segments_complete", "segments": segments}])

    p.on_correct_answer = on_correct_answer

    land = MiscLand.get()
    land.all_puzzles.append(p)
    p.post_init(land, None)

    # # All land metas are needed to start the runaround ...
    # for land in Land.BY_SHORTNAME.values():
    #   if land.meta_puzzle:
    #     cls.REQUIRED_PUZZLES.add(land.meta_puzzle)

    # ... plus the pressed-penny puzzle.
    cls.REQUIRED_PUZZLES.add(Workshop.PUZZLE)

    print("Required for runaround:")
    for p in cls.REQUIRED_PUZZLES:
      print(f"  {p.shortname} {p.title}")

    # Note that the Events puzzle is *not* needed (even though it
    # produces a penny).
