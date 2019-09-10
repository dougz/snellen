import base64
import json
import os
import requests
import time

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes

class Oauth2Token:
  def __init__(self, creds_file):
    if creds_file is None:
      creds_file = os.path.join(os.getenv("HUNT2020_BASE"),
                                "snellen/misc/upload-credentials.json")
    self.creds_file = creds_file
    self.cached = None

  def get(self):
    if not self.cached:
      self.cached = self._get_auth_token()
    return self.cached

  def invalidate(self):
    self.cached = None

  def _get_auth_token(self):
    with open(self.creds_file) as f:
      j = json.load(f)

    header = b"{\"alg\":\"RS256\",\"typ\":\"JWT\"}"
    h = base64.urlsafe_b64encode(header)

    now = int(time.time())
    claims = {
      "iss": j["client_email"],
      "scope": "https://www.googleapis.com/auth/devstorage.read_write",
      "aud": "https://www.googleapis.com/oauth2/v4/token",
      "exp": now + 3600,
      "iat": now,
    }

    cs = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8"))

    to_sign = h + b"." + cs

    private_key = serialization.load_pem_private_key(
      j["private_key"].encode("utf-8"), password=None, backend=default_backend())

    sig = private_key.sign(to_sign,
                           padding.PKCS1v15(),
                           hashes.SHA256())
    sig = base64.urlsafe_b64encode(sig)

    jwt = to_sign + b"." + sig

    r = requests.post(
      "https://www.googleapis.com/oauth2/v4/token",
      data=(b"grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&" +
            b"assertion=" + jwt),
      headers={"Content-Type": "application/x-www-form-urlencoded"})
    r.raise_for_status()

    j = json.loads(r.content.decode("utf-8"))
    token = j["token_type"] + " " + j["access_token"]
    return token

