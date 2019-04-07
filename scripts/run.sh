#!/bin/bash

# Arguments:
#
#  -t, --template_path
#    Path to the directory with HTML templates.
#
#  -c, --cookie_secret
#    Value included in the HMAC of session cookies; set this to some
#    string known only to you.
#
#  -r, --root_password
#    Creates an admin user named "root" with the given password.  Use
#    only when initializing the admin user database.


exec python3 src/main.py \
     --template_path html \
     --root_password joshua

