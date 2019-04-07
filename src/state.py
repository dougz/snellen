import functools
import json
import time

class Saver:
  def __init__(self):
    self.index = {}

  def open(self, filename):
    self.filename = filename
    self.log = open(filename, "a+")
    self.log.seek(0, 2)  # go to end

  def close(self):
    self.log.close()

  def __call__(self, fn):
    self.index[fn.__name__] = fn

    @functools.wraps(fn)
    def wrapped_fn(*args, **kwargs):
      now = time.time()
      record = (fn.__name__, now, args[1:], kwargs)
      json.dump(record, self.log)
      self.log.write("\n")
      self.log.flush()
      return fn(args[0], now, *args[1:], **kwargs)

    return wrapped_fn

  def replay(self, instance):
    self.log.seek(0, 0)
    for line in self.log:
      record = json.loads(line)
      name, now, args, kwargs = record
      fn = self.index[name]
      fn(instance, now, *args, **kwargs)
    self.log.seek(0, 2)



# mutating = Saver()


# class TestClass:
#   def __init__(self):
#     pass

#   @mutating
#   def save(self, now, thing):
#     print(f"@{now} {thing}")


# print("creating instance")
# t = TestClass()
# mutating.replay(t)

# print("----")
# print("invoking save")
# t.save(b"he\n\u2009llo")

# mutating.close()
