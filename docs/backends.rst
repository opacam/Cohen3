Backends
========

Introduction
------------

The backends are a special part of the Cohen3 project. They add extra capabilities
to the main project, allowing to create a server which will serve some content
depending on the enabled backend. The plugins were wrote a long time ago, and
due to the nature of the backend himself it needs some kind of maintenance
because, on some cases, we depend on external resources which may change...
this could lead into some plugins may stop working. Another reason for backend
failure maybe  a bug in source code, if you detect that some backend is not
working anymore, please, create a new issue at
`Cohen3 issue tracker <https://github.com/opacam/Cohen3/issues>`_, this way
there is a chance that the problem could be solved.

If you plan to create your own backend you should check the section
:ref:`Write a backend <write_a_backend>` which describes different methods
for creating a backend.

Working Backends
----------------
    - :ref:`Appletrailers storage <coherence.backends.appletrailers>`
    - :ref:`FSStore storage <coherence.backends.fs>`
    - :ref:`Gstreamer renderer <coherence.backends.gstreamer\_renderer>`
    - :ref:`Lolcats storage <coherence.backends.lolcats>`
    - :ref:`Playlist storage <coherence.backends.playlist>`
    - :ref:`Ted storage <coherence.backends.ted>`

Untested Backends
-----------------
    - :ref:`Ampache storage <coherence.backends.ampache>`
    - :ref:`Audiocd storage <coherence.backends.audiocd>`
    - :ref:`Axiscam storage <coherence.backends.axiscam>`
    - :ref:`Banshee storage <coherence.backends.banshee>`
    - :ref:`Buzztard storage <coherence.backends.buzztard>`
    - :ref:`DVBD storage <coherence.backends.dvbd>`
    - :ref:`Elisa renderer <coherence.backends.elisarenderer>` (see note 1)
    - :ref:`Elisa storage <coherence.backends.elisastorage>` (see note 1)
    - :ref:`Feed storage <coherence.backends.feed>`
    - :ref:`Flickr storage <coherence.backends.flickr>`
    - :ref:`Gallery2 storage <coherence.backends.gallery2>`
    - :ref:`Iradio storage <coherence.backends.iradio>`
    - :ref:`Itv storage <coherence.backends.itv>`
    - :ref:`Mediadb storage <coherence.backends.mediadb>`
    - :ref:`SWR3 storage <coherence.backends.swr3>`
    - :ref:`Test storage <coherence.backends.test>`
    - :ref:`Tracker storage <coherence.backends.tracker>`
    - :ref:`Yamj storage <coherence.backends.yamj>`

*Note 1: Those backends depends on twisted.axiom and twisted.epsilon, which has
been partially migrated to python 3...and may not work.*

Not working backends
--------------------
    - :ref:`Miroguide storage <coherence.backends.miroguide>`: miroguide's api is not working anymore
    - :ref:`BBC storage <coherence.backends.bbc>`: bbc shutdown rss service
    - :ref:`LastFM storage <coherence.backends.lastfm>`: service moved to new api...needs update
    - :ref:`Picasa storage <coherence.backends.picasa>`: google shutdown this service
    - :ref:`Twitch storage <coherence.backends.twitch>`: Partially working, video play is not working
    - :ref:`Youtube storage <coherence.backends.youtube>`: api must be updated to v3

Note: Some of this non working backends, may be removed in a future releases
(if we not find some way around the backend's problem).

.. toctree::
    :hidden:
    :titlesonly:
