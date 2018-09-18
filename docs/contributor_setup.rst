 
Setting Up the Code for Local Development
-----------------------------------------

Here's how to set up `Cohen3` for local development.

1. Fork the `Cohen3` repo on GitHub.
2. Clone your fork locally::

    $ git clone git@github.com:your_name_here/Cohen3.git

3. Install your local copy into a virtualenv. Assuming you have `pyenv
   <https://github.com/pyenv/pyenv>`_ installed, this is how you set up your
   fork for local development::

    $ CONFIGURE_OPTS=--enable-shared pyenv install 3.7-dev
    $ CONFIGURE_OPTS=--enable-shared pyenv virtualenv 3.7-dev cohen3
    $ cd Cohen3/
    $ pyenv activate cohen3
    $ pip install pipenv
    $ pipenv install
    $ pip install -e .[dev]

4. Create a branch for local development::

    $ git checkout -b name-of-your-bugfix-or-feature

Now you can make your changes locally.

5. When you're done making changes, check that your changes pass the tests::

    $ pycodestyle coherence --statistics --ignore=E402
    $ pylint -E coherence --rcfile=.pylintrc
    $ nosetests --with-coverage --cover-erase --cover-package=coherence --cover-html

6. Check that the test coverage hasn't dropped:

    The last command of the above point (nosetests), will print a report at the
    end of the tests (or you can check the results via your web browser: check
    the created folder "cover" and visualize the index.htm file for a nice
    report). Check that coverage percent against the coverage before the
    changes you made.

    :Note: You also can check the coverage once you submitted the pull requests
           and travis tests are done (but this, probably, it will be  slower
           than do it manually from your os, because you can skip some steps
           that travis cannot skip).

7. Commit your changes and push your branch to GitHub::

    $ git add .
    $ git commit -m "Your detailed description of your changes."
    $ git push origin name-of-your-bugfix-or-feature

8. Submit a pull request through the GitHub website.
