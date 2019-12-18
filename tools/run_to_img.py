#!/usr/bin/python3

with open("/tmp/emoji.txt", "r") as f:
  data = f.read()

for x in data:
  y = ord(x)
  if y < 128:
    print(x)
  else:
    print(hex(y))


