# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2018, Pol Canelles <canellestudi@gmail.com>
'''
Backend models for Container
----------------------------

Backend container to be used as a container for backend items, used by backend
store :class:`~coherence.backends.models.stores.BackendBaseStore`.

The `BackendContainer` inherits from :class:`~coherence.backend.Container` and
will initialize a :class:`~coherence.upnp.core.DIDLLite.Container` stored into
variable :attr:`BackendContainer.item`. This is the base class for our
containers.

We also provide some more containers:

    - :class:`BackendMusicAlbum`: Container which will contain audio items
      from an album
    - :class:`BackendBasePlaylist`: Container which will contain items to be
      played

.. note:: To write this module, some of the the old backends has been taken
          as a reference:

              - :mod:`~coherence.backends.appletrailers_storage`
              - :mod:`~coherence.backends.lolcats_storage`
              - :mod:`~coherence.backends.banshee_storage`
              - :mod:`~coherence.backends.fs_storage`

.. warning:: Be aware that we use super to initialize all the classes of this
             module in order to have a better MRO class resolution...so...take
             it into account if you inherit from one of this classes.

.. versionadded:: 0.8.3
'''
from coherence.backend import Container
from coherence.upnp.core import DIDLLite


class BackendContainer(Container):
    '''
    The BackendContainer will hold the reference to all your instances of
    BackendItem/s. This class could be used as a container for a simple
    backend. It is almost the same as a :class:`~coherence.backend.Container`
    but with some slight differences that will make easier to create an
    inherited class form BackendContainer:

        - The arguments to initialize the BackendContainer are
        - When we initialize the BackendContainer we also create an attribute
          item whim will be of :class:`~coherence.upnp.core.DIDLLite.Container`
          which will allow us to perform most of the operations we need to
          operate with your BackendItem/s
    '''
    logCategory = 'BackendContainer'

    item = None
    '''Define the initialized :attr:`item_cls`. It will be set when the class
    :class:`BackendContainer` is initialized based on the attribute
    :attr:`item_cls`'''

    item_cls = DIDLLite.Container
    '''Define an atomic object from :mod:`~coherence.upnp.core.DIDLLite`
    to be used to initialize the :attr:`item`'''

    def __init__(self, item_id, parent_id, name, **kwargs):
        super(BackendContainer, self).__init__(None, name)
        self.id = item_id
        self.parent_id = parent_id

        self.store = kwargs.get('store', None)
        self.storage_id = kwargs.get('storage_id', None)

        self.item = self.item_cls(self.id, parent_id, self.name)
        self.item.childCount = len(self.children)

    def __repr__(self):
        return \
            f'<BackendContainer {self.id} {self.get_name()} ' \
            f'[parent id: {self.parent_id}]>'


class BackendMusicAlbum(BackendContainer):
    """Definition for a music album. This is an inherited class from
    :class:`BackendContainer` but we use a different item class
    :class:`~coherence.upnp.core.DIDLLite.MusicAlbum` to create our item
    """

    logCategory = 'BackendMusicAlbum'

    item_cls = DIDLLite.MusicAlbum

    def __init__(self, item_id, parent_id, name, **kwargs):
        super(BackendMusicAlbum, self).__init__(
            item_id, parent_id, name, **kwargs)

        self.title = name
        self.artist = kwargs.get('artist', None)
        self.genre = kwargs.get('genre', None)
        self.cover = kwargs.get('cover', None)

        self.item = self.item_cls(
            self.id, self.parent_id, self.name)
        self.item.attachments = {}
        self.item.title = self.title
        self.item.artist = self.artist
        self.item.genre = self.genre
        self.item.albumArtURI = self.cover

    def get_name(self):
        return self.title

    def get_cover(self):
        return self.cover

    def __repr__(self):
        return \
            f'<BackendMusicAlbum {self.id} title="{self.title}" ' \
            f'genre="{self.genre}" artist="{self.artist}" ' \
            f'cover="{self.cover}">'


class BackendBasePlaylist(BackendContainer):
    """Definition for a playlist. This is an inherited class from
    :class:`BackendContainer` but we use a different item class
    :class:`~coherence.upnp.core.DIDLLite.PlaylistContainer` to create our item
    """

    logCategory = 'BackendBasePlaylist'

    item_cls = DIDLLite.PlaylistContainer

    def __init__(self, item_id, parent_id, name, **kwargs):
        super(BackendBasePlaylist, self).__init__(
            item_id, parent_id, name, **kwargs)

        self.title = name

    def get_name(self):
        return self.title

    def __repr__(self):
        return \
            f'<BackendBasePlaylist {self.id} title="{self.title}>'
