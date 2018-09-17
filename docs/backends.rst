
Backends (plugins)
------------------

Those are all supported backends. Some of them maybe will not work, cause the
target service has been shutdown or because there is some bug in source code,
if this is the case, please, create a new issue at
`Cohen3 issue tracker <https://github.com/opacam/Cohen3/issues>`_, this way
there is a chance that the problem could be solved.

The available plugins are:

    - :ref:`Ampache storage <coherence.backends.ampache>`: *Not tested*
    - :ref:`Appletrailers storage <coherence.backends.appletrailers>`: *Not tested*
    - :ref:`Audiocd storage <coherence.backends.audiocd>`: *Not tested*
    - :ref:`Axiscam storage <coherence.backends.axiscam>`: *Not tested*
    - :ref:`Banshee storage <coherence.backends.banshee>`: *Not tested*
    - :ref:`BBC storage <coherence.backends.bbc>`: *Not tested*
    - :ref:`Buzztard storage <coherence.backends.buzztard>`: *Not tested*
    - :ref:`DVBD storage <coherence.backends.dvbd>`: *Not tested*
    - :ref:`Elisa renderer <coherence.backends.elisarenderer>`: *Not tested* (see note 1)
    - :ref:`Elisa storage <coherence.backends.elisastorage>`: *Not tested* (see note 1)
    - :ref:`Feed storage <coherence.backends.feed>`: *Not tested*
    - :ref:`Flickr storage <coherence.backends.flickr>`: *Not tested*
    - :ref:`FSStore storage <coherence.backends.fs>`: **WORKING**
    - :ref:`Gallery2 storage <coherence.backends.gallery2>`: *Not tested*
    - :ref:`Gstreamer renderer <coherence.backends.gstreamer\_renderer>`: **WORKING**
    - :ref:`Iradio storage <coherence.backends.iradio>`: *Not tested*
    - :ref:`Itv storage <coherence.backends.itv>`: *Not tested*
    - :ref:`LastFM storage <coherence.backends.lastfm>`: *Not tested*
    - :ref:`Lolcats storage <coherence.backends.lolcats>`: *Not tested*
    - :ref:`Mediadb storage <coherence.backends.mediadb>`: *Not tested*
    - :ref:`Miroguide storage <coherence.backends.miroguide>`: *Not tested*
    - :ref:`Picasa storage <coherence.backends.picasa>`: **NOT WORKING** (google shutdown this service)
    - :ref:`Playlist storage <coherence.backends.playlist>`: **WORKING**
    - :ref:`SWR3 storage <coherence.backends.swr3>`: *Not tested*
    - :ref:`Ted storage <coherence.backends.ted>`: *Not tested*
    - :ref:`Test storage <coherence.backends.test>`: *Not tested*
    - :ref:`Tracker storage <coherence.backends.tracker>`: *Not tested*
    - :ref:`Twitch storage <coherence.backends.twitch>`: *Not tested*
    - :ref:`Yamj storage <coherence.backends.yamj>`: *Not tested*
    - :ref:`Youtube storage <coherence.backends.youtube>`: **NOT WORKING** (api must be updated to v3)


*Note 1: Those backends depends on twisted.axiom and twisted.epsilon, which has
been partially migrated to python 3...and may not work.*


.. toctree::
    :hidden:

    source/coherence.backends
