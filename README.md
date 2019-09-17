# Setting up

- Declare the base directory

    `export HUNT2020_BASE=<the directory>`

 - Install Python 3

    Linux: `apt-get install python3.7`

    Mac: `brew install python3`

- Install the Python 3 libraries

    Linux: `apt-get install python3-bs4 python3-bcrypt python3-html5lib python3-tornado python3-pycurl`

    Mac: `pip3 install bs4 bcrypt html5lib tornado python-dateutil`

- Download and symlink closure and closure-compiler in external

    Here is one such procedure:

    1. Download (and unzip) the 20190301 closure library
    [here](https://github.com/google/closure-library/archive/v20190301.zip).

    2. Download (and unzip) the 20190301 closure compiler
    [here](https://dl.google.com/closure-compiler/compiler-20190301.zip).

    3. Symlink them with something like:

    `cd $HUNT2020_BASE/snellen`

    `mkdir -p external`

    `ln -sf /path/to/closure-compiler-v20190301.jar external/closure-compiler.jar`

    `ln -sf /path/to/closure-library-20190301/closure external/`

- Run the recompile script

    `scripts/recompile.sh`

- Install nginx

    Linux: `apt-get install nginx`

    Mac: `brew install nginx`

- Install the nginx config file

    Linux: Copy the `config/snellen` file to `/etc/nginx/sites-available`, and then create a symlink
    to it from `/etc/nginx/sites-enabled`.

    Mac: Copy the `config/snellen` file into `/usr/local/etc/nginx/servers/`.

    In both cases, be sure that any of the static paths in the config file have been updated to
    match your environment.  Also, if you already have nginx installed for other purposes, remove
    the "default server" from the "listen" lines and uncomment the server_name directive.

- Clone the test_event_src and test_event repos.  This should go into
  directories parallel to the snellen source directory, with $HUNT2020_BASE as the parent:

    ```
    /some/path/to/snellen
    /some/path/to/test_event
    /some/path/to/test_event_src
    ```

  `test_event` is created from `test_event_src` by running the
  preprocess_* scripts in snellen/tools on the source config files and
  puzzle zips in test_event_src.  For convenience you can just clone
  the prebuild `test_event' repo instead.

  TODO(dougz): document how to build test_event from test_event_src



# Running the tests

`scripts/tests.sh`


# Running the server

`sudo nginx`  (sudo needed to listen on port 80)

```
cd $HUNT2020_BASE/..
./snellen/scripts/run.sh
```
