Cohen3
======

.. image:: https://travis-ci.com/opacam/Cohen3.svg?branch=master
        :target: https://travis-ci.com/opacam/Cohen3

.. image:: https://img.shields.io/pypi/status/Cohen3.svg
        :target: https://pypi.python.org/pypi/Cohen3/

.. image:: https://codecov.io/gh/opacam/Cohen3/branch/master/graph/badge.svg
        :target: https://codecov.io/gh/opacam/Cohen3
        :alt: PyPI version

.. image:: http://img.shields.io/pypi/v/Cohen3.svg?style=flat
        :target: https://pypi.python.org/pypi/Cohen3
        :alt: PyPI version

.. image:: https://img.shields.io/github/tag/opacam/Cohen3.svg
        :target: https://github.com/opacam/Cohen3/tags
        :alt: GitHub tag

.. image:: https://img.shields.io/github/release/opacam/Cohen3.svg
        :target: https://github.com/opacam/Cohen3/releases
        :alt: GitHub release

.. image:: https://img.shields.io/packagist/dm/doctrine/orm.svg?style=flat
        :target: https://pypi.python.org/pypi/Cohen3
        :alt: Packagist

.. image:: http://hits.dwyl.io/opacam/Cohen3.svg
        :target: http://hits.dwyl.io/opacam/Cohen3

.. image:: https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat
        :target: https://github.com/opacam/Cohen3/issues

.. image:: https://img.shields.io/github/commits-since/opacam/Cohen3/latest.svg
        :target: https://github.com/opacam/Cohen3/commits/master
        :alt: Github commits (since latest release)

.. image:: https://img.shields.io/github/last-commit/opacam/Cohen3.svg
        :target: https://github.com/opacam/Cohen3/commits/master
        :alt: GitHub last commit

.. image:: https://img.shields.io/github/license/opacam/Cohen3.svg
        :target: https://github.com/opacam/Cohen3/blob/master/LICENSE

.. raw:: html

        <h5 align="center">Dlna/UPnP framework</h5>
        <p align="center">
        <img style="width: 12.5em;" src="coherence/web/static/images/coherence-icon.png">
        </p>
        <h5 align="center">For the Digital Living</h5>

Overview
--------
Cohen3 Framework is a DLNA/UPnP Media Server for `Python 3`, based on the
`Python 2` version named `Cohen <https://github.com/unintended/Cohen>`_.
Provides several UPnP MediaServers and MediaRenderers to make simple publishing
and streaming different types of media content to your network.

Cohen3 is the Python 3's version of the
`Coherence Framework <https://github.com/coherence-project/Coherence>`_
project, originally created by
`Frank Scholz <mailto:dev@coherence-project.org>`_. If you ever used the
original Coherence project you could use Cohen3 like you do in the original
Coherence project.

- Documentation: https://opacam.github.io/Cohen3/
- GitHub: https://github.com/opacam/Cohen3
- Issue tracker: https://github.com/opacam/Cohen3/issues
- PyPI: https://pypi.python.org/pypi/cohen3
- Free software: MIT licence

Features
--------
The original `Coherence Framework` were know to work with different kind of
dlna/UPnP clients and Cohen3 should also work for them:

    - Sony Playstation 3/4
    - XBox360/One
    - Denon AV Receivers
    - WD HD Live MediaPlayers
    - Samsung TVs
    - Sony Bravia TVs

And provides a lot of backends to fulfil your media streaming needs:

    - Local file storage
    - Apple Trailers
    - Lol Cats
    - ShoutCast Radio
    - and much more...

Project Status
--------------
Right now Cohen is in development mode. All the code has been refactored in
order to work for Python 3, moreover, some additions has been made to make
easier to create a custom Backend (check the
`coherence.backends.models <https://opacam.github.io/Cohen3/source/coherence.
backends.html#coherence-backends-models-package>`_ package documentation for
more information). The original Coherence project was unmaintained for a while
and some of the backends has become obsolete. You can see the backends status
in the below table.

.. list-table::
   :widths: 10 25 65
   :header-rows: 1

   * - Status
     - Backend Name
     - Description/Notes
   * - |question|
     - AmpacheStore
     -
   * - |success|
     - AppleTrailersStore
     -
   * - |question|
     - AudioCDStore
     -
   * - |question|
     - AxisCamStore
     -
   * - |question|
     - BansheeStore
     -
   * - |fails|
     - BBCStore
     - *BBC shutdown the uri service, this backend will not work*
   * - |question|
     - BuzztardStore
     -
   * - |question|
     - DVBDStore
     -
   * - |question|
     - ElisaPlayer
     -
   * - |question|
     - ElisaMediaStore
     -
   * - |question|
     - FeedStore
     -
   * - |question|
     - FlickrStore
     -
   * - |success|
     - FSStore
     -
   * - |question|
     - Gallery2Store
     -
   * - |question|
     - GStreamerPlayer
     -
   * - |success|
     - IRadioStore (ShoutCast)
     -
   * - |question|
     - ITVStore
     -
   * - |fails|
     - LastFMStore
     - *service moved to new api...needs update*
   * - |success|
     - LolcatsStore
     -
   * - |question|
     - MediaStore
     -
   * - |fails|
     - MiroGuideStore
     - The miroguide's api is not working anymore :(
   * - |question|
     - PicasaStore
     - *Partially tested, may work until starting year 2019, where google will
       begin to shutdown this service, the source code should be rewrite using
       the api for the new service `Google Photos`*
   * - |success|
     - PlayListStore
     -
   * - |question|
     - RadiotimeStore
     -
   * - |question|
     - SWR3Store
     -
   * - |success|
     - TEDStore
     -
   * - |question|
     - TestStore
     -
   * - |question|
     - TrackerStore
     -
   * - |question|
     - TestStore
     -
   * - |fails|
     - TwitchStore
     - *Partially working, video play is not working*
   * - |question|
     - YamjStore
     -
   * - |fails|
     - YouTubeStore
     - *Google moved to new api...backend should be rewrite with new api in
       mind*

Notes:

    - Some of the listed backends it may be removed in a future releases...
      depending on if the target service is still available, dependencies of
      the backend, maintainability...keep in mind that the main goal of this
      project is to have a working media server/client capable of serve local
      files into a dlna/upnp network, all the backends are extra features which
      may be handy for some end-users and also may be useful as a reference of
      how to make your own backend using the Cohen3's modules.

.. |success| image:: misc/other-icons/checked.png
   :align: middle
   :height: 5
   :width: 5

.. |fails| image:: misc/other-icons/cross.png
   :align: middle
   :height: 5
   :width: 5

.. |question| image:: misc/other-icons/question.png
   :align: middle
   :height: 5
   :width: 5

Installation with pip
---------------------
If you want to install with pip, first make sure that the `pip` command
triggers the python3 version of python or use `pip3` instead. You can install
the `Cohen3` python package from `pypi` or github

To install from pypi:
^^^^^^^^^^^^^^^^^^^^^

  $ pip3 install --user Cohen3

To install from git:
^^^^^^^^^^^^^^^^^^^^

  $ pip3 install --user https://github.com/opacam/Cohen3/archive/master.zip

.. note::
    - An user install is recommended or use an virtualenv

.. tip::
      If you encounter problems while installing, caused by some dependency,
      you may try to bypass this error by installing the conflicting dependency
      before `Cohen3`, so if you face an error like this for `Twisted`:

        ERROR: Could not find a version that satisfies the requirement
        Twisted>=19.2.1 (from Cohen3) (from versions: none)

      You should be able to fix it installing Twisted before the install of
      `Cohen3`:

        pip3 install --upgrade --user Twisted

Installation from source
------------------------
After downloading and extracting the archive or having done a git
clone, move into the freshly created 'Cohen3' folder and install
the files with::

  $ sudo python ./setup.py install

This will copy the Python module files into your local Python package
folder and the cohen executable to ``/usr/local/bin/cohen3``.

If you want to install Cohen3 with extra dependencies you must do the steps
above and moreover install pip, then you can run the following command
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

You can also configure cohen via a config file. Feel free to check our example
``misc/cohen.conf.example``. The config file can be placed anywhere, cohen
looks by default for ``$HOME/.cohen``, but you can pass the path via the
command line option '-c' to it too::

  $ cohen3 -c /path/to/config/file

For developers
--------------
Starting from version 0.9.0 the event system has changed from louie/dispatcher
to EventDispatcher (external dependency). Here are the most important changes:

    - The new event system is not a global dispatcher anymore
    - All the signal/receivers are connected between them only if it is
      necessary.
    - We don't connect/disconnect anymore, instead we will bind/unbind.
    - The events has been renamed (this is necessary because the old event
      names contains dots in his names, and this could cause troubles with the
      new event system)

Please, check the documentation for further details at
`"The events system" <https://opacam.github.io/Cohen3/events.html>`_ section.

Contributing
------------
Report bugs at https://github.com/opacam/Cohen3/issues

Feel free to fetch the repo and send your
`pull requests! <https://github.com/opacam/Cohen3/pulls>`_
