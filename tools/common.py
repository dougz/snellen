import requests

MIME_TYPES = {".jpg": "image/jpeg",
              ".png": "image/png",
              ".js": "text/javascript",
              ".txt": "text/plain",
              ".html": "text/html",
              ".zip": "application/zip",
              ".wav": "audio/wav",
              ".mp3": "audio/mpeg",
              ".css": "text/css",
}

def upload_object(bucket, path, mime_type, data, creds):
  r = requests.head(f"https://{bucket}.storage.googleapis.com/{path}")
  if r.status_code in (200, 204): return
  if r.status_code != 404:
    r.raise_for_status()

  for i in range(2):
    r = requests.put(f"https://storage.googleapis.com/{bucket}/{path}",
                     headers={"Content-Type": mime_type,
                              "Authorization": creds.get()},
                     data=data)
    if r.status_code == 401:
      creds.invalidate()
      continue

    r.raise_for_status()
    break



