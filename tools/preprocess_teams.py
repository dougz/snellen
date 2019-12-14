#!/usr/bin/python3

import argparse
import bcrypt
import json
import os
import re
import yaml


def make_hash(password):
  return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def main():
  parser = argparse.ArgumentParser(
    description="Process the team data file for use by the server.")

  parser.add_argument("--input_dir",
                      help="Input directory with teams.yaml to process.")
  parser.add_argument("--output_dir",
                      help="Directory to write output to.")
  options = parser.parse_args()

  with open(os.path.join(options.input_dir, "teams.yaml")) as f:
    y = yaml.load(f)

  out = {}
  names = set()
  logins = set()
  for i, (username, d) in enumerate(y["teams"].items()):
    print(f"{i+1}: {d['name']} ({username})")

    od = {}

    # usernames and alt-usernames are case-insensitive
    username = username.lower()
    if "alt" in d:
      d["alt"] = d["alt"].lower()
    assert re.match(r"^[a-z][a-z0-9]*$", username)

    # No duplicate usernames
    assert username not in out

    # Or logins.
    assert username not in logins
    logins.add(username)
    if "alt" in d:
      assert d["alt"] not in logins
      logins.add(d["alt"])

    # No duplicate team names
    assert d["name"] not in names
    names.add(d["name"])
    od["name"] = d.pop("name")

    # Team size plausible
    assert 0 < d["size"] <= 500
    od["size"] = d.pop("size")

    # Password nonempty
    assert d["password"], f"{username} missing password"
    od["pwhash"] = make_hash(d.pop("password"))

    od["remote_only"] = d.pop("remote_only", False)

    if d:
      od["attrs"] = d

    out[username] = od

  with open(os.path.join(options.output_dir, "teams.json"), "w") as f:
    json.dump(out, f, sort_keys=True, indent=2)


if __name__ == "__main__":
  main()
