Cohen
=====
Simple DLNA/UPnP Media Server

.. image:: http://img.shields.io/travis/unintended/Cohen.svg?style=flat-square
    :target: http://travis-ci.org/unintended/cohen


Overview
--------
Cohen is a DLNA/UPnP Media Server written in Python,
providing several UPnP MediaServers and MediaRenderers,
and enabling your application to participate in digital living networks.

Cohen is actually a highly simplified and refreshed version of
`Coherence Framework <https://github.com/coherence-project/Coherence>`_ project by `Frank Scholz <mailto:dev@coherence-project.org>`_
which looks like no longer supported.

Software Information
    - Latest release: |version| (:ref:`CHANGELOG`)
    - GitHub: https://github.com/unintended/Cohen
    - Issue tracker: https://github.com/unintended/Cohen/issues
    - PyPI: https://pypi.python.org/pypi/cohen
    - Free software: MIT licence


Features
--------
Cohen is known to work with various clients
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


Installation from source
------------------------
After downloading and extracting the archive or having done a git
clone, move into the freshly created 'Cohen' folder and install
the files with::

  $ sudo python ./setup.py install

This will copy the Python module files into your local Python package
folder and the cohen executable to ``/usr/local/bin/cohen``.


Quickstart
----------
To just export some files on your hard-disk fire up Cohen with
an UPnP MediaServer with a file-system backend enabled::

  $ cohen --plugin=backend:FSStore,content:/path/to/your/media/files

You can also configure cohen via a config file. Feel free to check our example ``misc/cohen.conf.example``.
The config file can be placed anywhere, cohen looks by default for
``$HOME/.cohen``, but you can pass the path via the commandline option
'-c' to it too::

  $ cohen -c /path/to/config/file



Contributing
------------
Report bugs at https://github.com/unintended/Cohen/issues

Feel free to fetch the repo and send your pull requests!
