    .. _coherence.backends:

coherence.backends (package)
============================

The backends package contains a sub package
:ref:`coherence.backends.models <coherence.backends.models (package)>`
which contains some base classes meant to be used to create a custom Backend.

Also contains all Cohen3 available backends. Most of them are BackendStores
which allow to create a Media Server for specific situations. Check out each
module for further documentation.

Here are all available Cohen3 Backends:

.. toctree::

    backends/ampache
    backends/appletrailers
    backends/audiocd
    backends/axiscam
    backends/banshee
    backends/bbc
    backends/buzztard
    backends/dvbd
    backends/elisarenderer
    backends/elisastorage
    backends/feed
    backends/flickr
    backends/fs
    backends/gallery2
    backends/gstreamer_renderer
    backends/iradio
    backends/itv
    backends/lastfm
    backends/lolcats
    backends/mediadb
    backends/miroguide
    backends/picasa
    backends/playlist
    backends/radiotime
    backends/swr3
    backends/ted
    backends/test
    backends/tracker
    backends/twitch
    backends/yamj
    backends/youtube

coherence.backends.models (package)
-----------------------------------

If you plan to write a custom backend this classes should make easier to
develop it:

.. toctree::

    backends/models/items
    backends/models/containers
    backends/models/stores

If you want to see some more examples about how to apply those
classes you can check those backends:

    - :ref:`AppleTrailersStorage <coherence.backends.appletrailers>`
    - :ref:`LolcatsStore <coherence.backends.lolcats>`
    - :ref:`TedStorage <coherence.backends.ted>`
