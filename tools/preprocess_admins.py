#!/usr/bin/python3

import argparse
import bcrypt
import json
import os
import yaml
import re


def make_hash(password):
  return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def main():
  parser = argparse.ArgumentParser(
    description="Process the admin data file for use by the server.")

  parser.add_argument("--input_dir",
                      help="Input directory with admins.yaml to process.")
  parser.add_argument("--output_dir",
                      help="Directory to write output to.")
  options = parser.parse_args()

  with open(os.path.join(options.input_dir, "admins.yaml")) as f:
    y = yaml.load(f)

  out = {}
  names = set()
  for i, (username, d) in enumerate(y["admins"].items()):
    od = {}

    u = re.sub(r"[^a-z0-9_]", "", username.lower())
    if u != username:
      print(f"{i+1}: {d['name']} ({u}) (was {username})")
      username = u
    else:
      print(f"{i+1}: {d['name']} ({username})")

    # No duplicate usernames
    assert username not in out, f"Duplicate username {username}!"

    # No duplicate full names
    assert d["name"] not in names, f"Duplicate full name {d['name']}!"
    names.add(d["name"])
    od["name"] = d.pop("name")

    # Password nonempty
    if "pwhash" in d:
      od["pwhash"] = d["pwhash"]
    elif "password" in d:
      od["pwhash"] = make_hash(d.pop("password"))
    else:
      raise ValueError(f"Error in {username}: no password or pwhash")

    if "roles" in d:
      od["roles"] = d["roles"]

    out[username] = od

  with open(os.path.join(options.output_dir, "admins.json"), "w") as f:
    json.dump(out, f, sort_keys=True, indent=2)


if __name__ == "__main__":
  main()
