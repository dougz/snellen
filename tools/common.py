import base64
import hashlib
import json
import requests

SECRET_KEY_LENGTH = 16

CONTENT_TYPES = {
  ".jpg": "image/jpeg",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webp": "image/webp",
  ".gif": "image/gif",

  ".wav": "audio/wav",
  ".mp3": "audio/mpeg",
  ".m4a": "audio/m4a",

  ".mp4": "video/mp4",

  ".js": "text/javascript; charset=utf-8",
  ".json": "text/javascript; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",

  ".zip": "application/zip",
  ".pdf": "application/pdf",

  ".eot": "application/vnd.ms-fontobject",
  ".otf": "application/font-sfnt",
  ".ttf": "application/font-sfnt",
  ".woff": "application/font-woff",
  ".woff2": "font/woff2",

  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

object_cache = {}

def load_object_cache(bucket, creds):
  page_token = None
  while True:
    url = f"https://www.googleapis.com/storage/v1/b/{bucket}/o"
    if page_token:
      url += f"?pageToken={page_token}"

    r = requests.get(url, headers={"Authorization": creds.get()})
    if r.status_code == 401:
      creds.invalidate()
      continue
    if r.status_code != 200:
      r.raise_for_status()

    d = json.loads(r.content)
    if "items" not in d: break
    for i in d["items"]:
      object_cache[i["name"]] = i["md5Hash"]

    page_token = d.get("nextPageToken")
    if not page_token: break

  return object_cache


def upload_object(source, bucket, path, content_type, data, creds, update=False):
  if path in object_cache and not update:
    print(f"    Already have {source} as {path} (cached)...")
    return

  if not update:
    for retry in range(2):
      r = requests.head(f"https://{bucket}.storage.googleapis.com/{path}",
                        headers={"Authorization": creds.get()})
      if r.status_code == 401:
        creds.invalidate()
        continue
      else:
        break

    if r.status_code in (200, 204):
      print(f"    Already have {source} as {path}...")
      return
    if r.status_code != 404:
      r.raise_for_status()

  print(f"    Uploading {source} as {path}...")
  for i in range(2):
    r = requests.put(f"https://storage.googleapis.com/{bucket}/{path}",
                     headers={"Content-Type": content_type,
                              "Cache-Control": "public,max-age=345600",
                              "Authorization": creds.get()},
                     data=data)
    if r.status_code == 401:
      creds.invalidate()
      continue

    r.raise_for_status()
    break


def hash_name(data):
  h = hashlib.sha256(data).digest()
  n = base64.urlsafe_b64encode(h).decode("ascii")[:SECRET_KEY_LENGTH]
  return n


