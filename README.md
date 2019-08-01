# Setting up

- Declare the base directory

    `export SNELLEN_BASE=<the directory>`

 - Install Python 3

    Linux: `apt-get install python3.7`

    Mac: `brew install python3`

- Install the Python 3 libraries

    Linux:

    `apt-get install python3-bs4 python3-bcrypt python3-lxml python3-tornado python3-pycurl`

    Mac:

    `brew install openssl`

    `pip3 install bs4 bcrypt lxml tornado`

    `pip3 install --install-option="--with-openssl" --install-option="--openssl-dir=/usr/local/opt/openssl" pycurl`

- Download and symlink closure and closure-compiler in external

    Here is one such procedure:

    1. Download (and unzip) the 20190301 closure library
    [here](https://github.com/google/closure-library/archive/v20190301.zip).

    2. Download (and unzip) the 20190301 closure compiler
    [here](https://dl.google.com/closure-compiler/compiler-20190301.zip).

    3. Symlink them with something like:

    `cd $SNELLEN_BASE`

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


# Running the tests

`scripts/tests.sh`


# Running the server

`sudo nginx`  (sudo needed to listen on port 80)

`scripts/run.sh`


