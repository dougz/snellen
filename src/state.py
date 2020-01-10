import functools
import json
import sys
import time

class SaverClass:
  instance_index = {}
  class_map = {}
  log = None
  next_id = 1

  REPLAYING = False

  @classmethod
  def open(cls, filename):
    cls.filename = filename
    cls.log = open(filename, "a+")
    cls.log.seek(0, 2)  # go to end

  @classmethod
  def set_classes(cls, **kwargs):
    cls.class_map.update(kwargs)

  @classmethod
  def close(cls):
    cls.log.close()

  @classmethod
  def __call__(cls, fn):
    n = fn.__name__
    if n == "__init__":
      # special handling for __init__

      @functools.wraps(fn)
      def wrapped_init(self, *args, **kwargs):
        now = time.time()
        cname = self.__class__.__name__
        fn(self, now, *args, **kwargs)
        if not hasattr(self, "_saver_id"):
          self._saver_id = cname + ":" + str(cls.next_id)
          cls.next_id += 1
          cls.instance_index[self._saver_id] = self
        record = (self._saver_id, fn.__name__, now, args, kwargs)
        json.dump(record, cls.log)
        cls.log.write("\n")
        cls.log.flush()

      return wrapped_init

    else:
      @functools.wraps(fn)
      def wrapped_fn(self, *args, **kwargs):
        now = time.time()
        record = (self._saver_id, fn.__name__, now, args, kwargs)
        json.dump(record, cls.log)
        cls.log.write("\n")
        cls.log.flush()
        return fn(self, now, *args, **kwargs)

      return wrapped_fn

  @classmethod
  def add_instance(cls, saver_id, instance):
    instance._saver_id = saver_id
    cls.instance_index[saver_id] = instance

  @classmethod
  def replay(cls, advance_time=None):
    start = time.time()
    replay_count = 0
    count = 1
    skipped = set()
    cls.REPLAYING = True
    try:
      cls.log.seek(0, 0)
      for line in cls.log:
        if line.startswith("#"):
          replay_count += 1
          continue
        record = json.loads(line)
        saver_id, name, now, args, kwargs = record
        if advance_time:
          advance_time(now)
        count += 1

        classname, num = saver_id.split(":")
        try:
          num = int(num)
          if cls.next_id <= num:
            cls.next_id = num + 1
        except ValueError:
          pass
        klass = cls.class_map[classname]
        if name == "__init__":
          obj = klass.__new__(klass)
          obj.__init__.__wrapped__(obj, now, *args, **kwargs)
          obj._saver_id = saver_id
          cls.instance_index[saver_id] = obj
        else:
          instance = cls.instance_index.get(saver_id, None)
          if instance:
            getattr(klass, name).__wrapped__(instance, now, *args, **kwargs)
          else:
            skipped.add(saver_id)
      cls.log.seek(0, 2)
    except Exception as e:
      print("whoops", e)
      raise
    finally:
      cls.REPLAYING = False

    cls.log.write("# replay\n")

    if skipped:
      print("Replay skipped references to: " + ", ".join(skipped))
    dur = int((time.time() - start) * 1000)
    print(f"Replayed {count} log items in {dur} ms.  {replay_count} previous replays.")

    return replay_count


save_state = SaverClass()

__all__ = ["save_state"]
