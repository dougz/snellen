# Setting up

- Declare the base directory

    `export SNELLEN_BASE=<the directory>`

- Install the Python dependencies

    `apt-get install python3-bs4 python3-bcrypt python3-lxml python3-tornado`

    (-or- `pip3 install bs4 bcrypt lxml tornado`)

- Install and symlink closure and closure-compiler in tools

    Here is one such procedure:

    1. Download the closure library:

    `git clone https://github.com/google/closure-library`.

    2. Download the closure compiler as described [here](https://github.com/google/closure-compiler).

    3. Symlink them with something like:

    `cd $SNELLEN_BASE`

    `mkdir tools`

    `ln -sf /path/to/closure-compiler-v20XXXX.jar tools/closure-compiler.jar`

    `ln -sf /path/to/closure-library/closure tools/closure`

- Run the recompile script

    `scripts/recompile.sh`


# Running the tests

`scripts/tests.sh`


# Running the server

To run locally:

`scripts/run.sh --port=8888`

Otherwise read the file header for more options!
