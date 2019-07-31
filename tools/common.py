import requests

CONTENT_TYPES = {".jpg": "image/jpeg",
              ".png": "image/png",
              ".js": "text/javascript; charset=utf-8",
              ".txt": "text/plain; charset=utf-8",
              ".html": "text/html; charset=utf-8",
              ".zip": "application/zip",
              ".wav": "audio/wav",
              ".mp3": "audio/mpeg",
              ".css": "text/css; charset=utf-8",
}

def upload_object(bucket, path, content_type, data, creds):
  r = requests.head(f"https://{bucket}.storage.googleapis.com/{path}")
  if r.status_code in (200, 204):
    print(f"    already have {path}...")
    return
  if r.status_code != 404:
    r.raise_for_status()

  print(f"    uploading {path}...")
  for i in range(2):
    r = requests.put(f"https://storage.googleapis.com/{bucket}/{path}",
                     headers={"Content-Type": content_type,
                              "Cache-Control": "public,max-age=86400",
                              "Authorization": creds.get()},
                     data=data)
    if r.status_code == 401:
      creds.invalidate()
      continue

    r.raise_for_status()
    break



