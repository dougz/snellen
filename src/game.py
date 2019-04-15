import unicodedata
import re

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
  BY_SHORTNAME = {}

  def __init__(self,
               shortname,
               title,
               answer,
               matchers):
    assert shortname not in self.BY_SHORTNAME
    self.BY_SHORTNAME[shortname] = self

    self.shortname = shortname
    self.title = title
    self.display_answer = answer
    self.canonical_answer = self.canonicalize_answer(answer)

  @classmethod
  def add_puzzle(cls, shortname, title, answer, matchers=()):
    print(f"  Adding puzzle {shortname} \"{title}\"")
    Puzzle(shortname, title, answer, matchers)

  @classmethod
  def get_by_shortname(cls, shortname):
    return cls.BY_SHORTNAME.get(shortname)

  @staticmethod
  def canonicalize_answer(text):
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore")
    text = text.decode("ascii")
    text = re.sub("[^a-zA-Z]+", "", text)
    return text.upper()




