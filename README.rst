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

        <div style="text-align:center;">
        <h5>Dlna/UPnP framework</h5>
        <img style="width: 12.5em;" src="coherence/web/static/images/coherence-icon.png"></img>
        <h5>For the Digital Living</h5>
        </div>

Overview
--------
Cohen3 Framework is a DLNA/UPnP Media Server for Python 3, based on the python 2
version named `Cohen <https://github.com/unintended/Cohen>`_. Provides several
UPnP MediaServers and MediaRenderers to make simple publishing and streaming
different types of media content to your network.

Cohen3 is the Python 3's version of the
`Coherence Framework <https://github.com/coherence-project/Coherence>`_
project, originally created by `Frank Scholz <mailto:dev@coherence-project.org>`_.
If you ever used the original Coherence project you could use Cohen3 like you
do in the original Coherence project.

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
Right now Cohen is in development mode. All the code has been refactored in order
to work for Python 3, moreover, some additions has been made to make easier
to create a custom Backend (check the
`models documentation <https://opacam.github.io/Cohen3/source/coherence.backends.models.html>`_ for more information).
The original Coherence project was unmaintained for a while and some of the
backends has become obsolete. You can see the backends status in the below table.

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Backend Name
     - Status
     - Description/Notes
   * - |question| AmpacheStore
     - *Not tested*
     -
   * - |success| AppleTrailersStore
     - **WORKING**
     -
   * - |question| AudioCDStore
     - *Not tested*
     -
   * - |question| AxisCamStore
     - *Not tested*
     -
   * - |question| BansheeStore
     - *Not tested*
     -
   * - |fails| BBCStore
     - *Not working*
     - *BBC shutdown the uri service, this backend will not work*
   * - |question| BuzztardStore
     - *Not tested*
     -
   * - |question| DVBDStore
     - *Not tested*
     -
   * - |question| ElisaPlayer
     - *Not tested*
     -
   * - |question| ElisaMediaStore
     - *Not tested*
     -
   * - |question| FeedStore
     - *Not tested*
     -
   * - |question| FlickrStore
     - *Not tested*
     -
   * - |success| FSStore
     - **WORKING**
     -
   * - |question| Gallery2Store
     - *Not tested*
     -
   * - |question| GStreamerPlayer
     - *Not tested*
     -
   * - |success| IRadioStore (ShoutCast)
     - **WORKING**
     -
   * - |question| ITVStore
     - *Not tested*
     -
   * - |question| LastFMStore
     - *Not working*
     - *service moved to new api...needs update*
   * - |success| LolcatsStore
     - **WORKING**
     -
   * - |question| MediaStore
     - *Not tested*
     -
   * - |question| MiroGuideStore
     - *Deprecated*
     - The miroguide's api is not working anymore :(
   * - |question| PicasaStore
     - *partially tested*
     - *May work until starting year 2019, where google will begin to shutdown
       this service, the source code should be rewrite using the api for the new
       service `Google Photos`*
   * - |success| PlayListStore
     - **WORKING**
     -
   * - |question| RadiotimeStore
     - *Not tested*
     -
   * - |question| SWR3Store
     - *Not tested*
     -
   * - |success| TEDStore
     - **WORKING**
     -
   * - |question| TestStore
     - *Not tested*
     -
   * - |question| TrackerStore
     - *Not tested*
     -
   * - |question| TestStore
     - *Not tested*
     -
   * - |fails| TwitchStore
     - *Partially working, video play is not working*
     - *Needs fixes*
   * - |fails| YamjStore
     - *Not tested*
     -
   * - |fails| YouTubeStore
     - *can't work*
     - *Google moved to new api...backend should be rewrite with new api in mind*

Notes:

    - Some of the listed backends it may be removed in a future releases...
      depending on if the target service is still available, dependencies of the
      backend, maintainability...keep in mind that the main goal of this project
      is to have a working media server/client capable of serve local files into
      a dlna/upnp network, all the backends are extra features wich may be handy
      for some end-users and also may be useful as a reference of how to make
      your own backend using the Cohen3's modules.

.. |success| image:: misc/other-icons/checked.png
   :align: middle
   :height: 15
   :width: 15

.. |fails| image:: misc/other-icons/cross.png
   :align: middle
   :height: 15
   :width: 15

.. |question| image:: misc/other-icons/question.png
   :align: middle
   :height: 15
   :width: 15

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
