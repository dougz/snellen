#!/bin/bash

# Arguments:
#
#  -e, --event_dir
#    Directory for event (contains definitions of teams & puzzles as
#    well as log files).
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
#
#  --debug
#    Enables debug mode:
#      * client.js is used directly rather than serving the compiled
#        version.
#      * html templates are re-read from disk on page reload
#
#  --default_credentials
#      "username:password" to fill in by default on the login page.
#      Useful when developing and you have to restart the server and
#      log in a lot.
#
#  --port
#      Use this to specify a port for the server to listen.  Use only
#      for localhost testing, as in production serving uses UNIX
#      sockets instead.


exec python3 src/main.py \
     --event_dir test_event \
     --template_path html \
     --root_password joshua \
     "$@"

