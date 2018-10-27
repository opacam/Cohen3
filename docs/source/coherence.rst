    .. _coherence:

Cohen3 source tree
==================

This is the source tree for Cohen3's package. The main module name is named
coherence, so...all the submodules and subpackages will contain `coherence`.
This allow us to maintain compatibility to projects who wants to migrate from
python 2 to python 3 and has the original project `Coherence` as one of his
dependencies, allowing to the developers to maintain his source code with
minimal changes.

.. toctree::
    :maxdepth: 5

    modules
    coherence.backends
    coherence.extern
    coherence.upnp
    coherence.web
