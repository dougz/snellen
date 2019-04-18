import configparser
import os
import re
import unicodedata

import bs4

import login
from state import save_state

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

    self.puzzles_open = set()


  # This method is exported into the file that's used to create all
  # the teams.
  @classmethod
  def add_team(cls, username, password, team_name, location):
    if username not in cls.BY_USERNAME:
      print(f"  Adding team {username} \"{team_name}\"")
      Team(username, login.make_hash(password), team_name, location)

  @classmethod
  def get_by_username(cls, username):
    return cls.BY_USERNAME.get(username)




class Puzzle:
  BY_NICKNAME = {}

  def __init__(self, path):
    nickname = os.path.basename(path)
    print(f"  Adding puzzle {nickname}")

    self.BY_NICKNAME[nickname] = self

    c = configparser.ConfigParser()
    c.read(os.path.join(path, "metadata.cfg"))

    p = c["PUZZLE"]
    assert nickname == p["nickname"]

    self.nickname = nickname
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
  def get_by_nickname(cls, nickname):
    return cls.BY_NICKNAME.get(nickname)

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







