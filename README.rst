Cohen3
======
Simple DLNA/UPnP Media Server

.. image:: http://img.shields.io/pypi/v/Cohen3.svg?style=flat-square
    :target: https://pypi.python.org/pypi/Cohen3

.. image:: http://img.shields.io/pypi/dm/Cohen3.svg?style=flat-square
    :target: https://pypi.python.org/pypi/Cohen3

.. image:: https://travis-ci.com/opacam/Cohen3.svg?branch=master
    :target: https://travis-ci.com/opacam/Cohen3


Overview
--------
Cohen3 Framework is a DLNA/UPnP Media Server for Python 3, based on the python 2
version named `Cohen <https://github.com/unintended/Cohen>`_. Provides several
UPnP MediaServers and MediaRenderers to make simple publishing and streaming
different types of media content to your network.

Cohen3 is actually a highly simplified and refreshed version of
`Coherence Framework <https://github.com/coherence-project/Coherence>`_
project by `Frank Scholz <mailto:dev@coherence-project.org>`_ which looks like
no longer supported.

- Documentation: https://opacam.github.io/Cohen3/
- GitHub: https://github.com/opacam/Cohen3
- Issue tracker: https://github.com/opacam/Cohen3/issues
- PyPI: https://pypi.python.org/pypi/cohen3
- Free software: MIT licence

Features
--------
Cohen3 is known to work with various clients

    - Sony Playstation 3/4
    - XBox360/One
    - Denon AV Receivers
    - WD HD Live MediaPlayers
    - Samsung TVs
    - Sony Bravia TVs

And provides a lot of backends to fulfil your media streaming needs

    - Local file storage
    - YouTube
    - Twitch.tv
    - and much more...

Project Status
--------------
Right now this project is in development mode...there is more work to do
in order to recover the expected behaviour, but right now the basic functionality
of the project (Create a DLNA/UpnP client or a server with the FSStore plugin)
seems to work in our tests.

NOTE: All the dependencies of the setup.py file are the basic dependencies in
order to run a media server. Should be mentioned that some of the backends
needs more dependencies and some of them may not work as expected because there
aren't tested yet, see the install instructions section for more information.

Installation from source
------------------------
After downloading and extracting the archive or having done a git
clone, move into the freshly created 'Cohen3' folder and install
the files with::

  $ sudo python ./setup.py install

This will copy the Python module files into your local Python package
folder and the cohen executable to ``/usr/local/bin/cohen3``.

If you want to install Cohen3 with extra dependencies you must do the steps above
and moreover install pip, then you can run the following command
(instead of the mentioned above) for installing the development dependencies::

  $ sudo pip install -e .[dev]

Note:  The supported install modes are:

    - dev: all the dependencies will be installed except docs
    - test: used by travis builds (omits dbus and docs)
    - docs: install build dependencies to generate docs
    - dbus: install dependencies needed by tube service or dvbd storage
    - gstreamer: needed if you use GStreamerPlayer
    - picasa: needed by the picasa storage
    - youtube: needed by the youtube backend

Quickstart
----------
To just export some files on your hard-disk fire up Cohen with
an UPnP MediaServer with a file-system backend enabled::

  $ cohen3 --plugin=backend:FSStore,content:/path/to/your/media/files

You can also configure cohen via a config file. Feel free to check our example ``misc/cohen.conf.example``.
The config file can be placed anywhere, cohen looks by default for
``$HOME/.cohen``, but you can pass the path via the commandline option
'-c' to it too::

  $ cohen3 -c /path/to/config/file

Contributing
------------
Report bugs at https://github.com/opacam/Cohen3/issues

Feel free to fetch the repo and send your `pull requests! <https://github.com/opacam/Cohen3/pulls>`_
