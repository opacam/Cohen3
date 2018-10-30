.. _install:

Installation
============

Basic install (pip)
-------------------

Install from the git master branch zip package::

  $ pip install --user https://github.com/opacam/Cohen3/archive/master.zip

Or you can install directly from the git master branch::

  $ pip install --user git+git://github.com/opacam/Cohen3@master#egg=Cohen3

Note: With the command above you will install the Cohen3 package with the
standard dependencies

Install with extra dependencies
-------------------------------

Some of the plugins will depend of system libraries that you must install
in order to make it work the plugin.

Note: the apt commands showed in this document are the ones used in our travis
builds. The tests are made using a GNU Linux Os: ubuntu xenial.

You must have an updated cython package::

    $ pip install --upgrade cython

First of all yo must clone the repository::

    $ git clone https://github.com/opacam/Cohen3.git


Enter into the cloned repository, and run the proper commands, depending of the
plugin/feature you want to use:

    - Audiocd storage::

        $ sudo apt-get install libdiscid0
        $ pip install -e .[audio]

    - For using dbus-python::

        $ sudo apt-get install libdbus-1-dev
        $ pip install -e .[dbus]

    - For using gstreamer:

        Install libraries and plugins for GStreamer1.0 ::

            $ sudo apt-get install --yes gstreamer1.0-alsa gstreamer1.0-plugins-bad gstreamer1.0-plugins-base gstreamer1.0-plugins-base-apps gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly gstreamer1.0-libav


        Install Dependencies for gi.repository: Gst, GObject, Cairo::

            $ sudo apt-get install -y libgirepository1.0-dev libcairo2-dev gir1.2-gtk-3.0 gobject-introspection python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-gst-1.0

        Run the pip command to install the python bindings::

            $ pip install -e .[gstreamer]

    - For using elisa::

        $ pip install -e .[elisa]

    - For using picasa (*plugin obsolete, should be migrated to Google photos*)::

        $ pip install -e .[picasa]

    - For using twitch storage::

        $ pip install -e .[twitch]

    - For using toutube storage (*plugin outdated*)::

        $ pip install -e .[youtube]

Also there are some special setup commands that can be useful for developers:

    - Install all dependencies::

        $ pip install -e .[dev]

    - Install all docs dependencies::

        $ pip install -e .[doc]

    - Install all test dependencies::

        $ pip install -e .[test]


*Note: If you have any doubt about how to install some dependencies, you can check the
.travis.yml file, it can be useful in some cases.*

Python dependencies
-------------------

The basic dependencies for the package are:

    - ConfigObj >= 4.3
    - Twisted >= 18.7
    - zope.interface
    - lxml
    - eventdispatcher >= 1.9.4
    - python-dateutil
    - pyopenssl

Depending of the plugin or module you want to use, you may need to install
some extra dependencies:

    - audio_store:
        - pycdb
        - discid
    - elisa_store:
        - Epsilon
        - Axiom
    - twitch storage:
        - livestreamer
    - picasa_store:
        - gdata
    - youtube_store:
        - gdata
    - web_ui:
        - autobahn
    - gstreamer_player:
        - pygobject>= 3.30.0
        - pycairo>=1.17.1


Starting as Service
-------------------

*Still not documented*
