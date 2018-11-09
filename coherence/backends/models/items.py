# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2018, Pol Canelles <canellestudi@gmail.com>
'''
Backend models for BackendItem
------------------------------

Backend items to be used directly or subclassed. This classes inherits from
:class:`~coherence.backend.BackendItem`. This classes should cover the most
basic needs for different types of media and goes one step further from the
:mod:`~coherence.backend` by initializing the corresponding DIDLLite object.

* For video backends:

    - :class:`BackendVideoItem`: item representing a video resource

* For audio backends:

    - :class:`BackendAudioItem`: item representing a audio resource
    - :class:`BackendMusicTrackItem`: item representing an audio resource

* For image/photo backends:

    - :class:`BackendImageItem`: item representing a image resource
    - :class:`BackendPhotoItem`: item representing a photo resource

* For create a custom backend:

    - If the items described above does not meet your needs, you can subclass
      them or you may use the base class :class:`BackendBaseItem`, used to
      develop all those backend items described above.

.. note::
    To write this module, some of the the old backends has been taken
    as a reference:

        - :mod:`~coherence.backends.appletrailers_storage`
        - :mod:`~coherence.backends.banshee_storage`
        - :mod:`~coherence.backends.fs_storage`

.. warning:: Be aware that we use super to initialize all the classes of this
             module in order to have a better MRO class resolution...so...take
             it into account if you inherit from one of this classes.

.. versionadded:: 0.8.3
'''

from coherence.upnp.core.utils import ReverseProxyUriResource
from coherence.upnp.core import DIDLLite
from coherence.backend import BackendItem


class BackendBaseItem(BackendItem):
    '''
    This class is intended to be used as a base class for creating a custom
    backend item. It has the ability to support proxy or non-proxy items by
    using the property proxy_cls.

    .. warning:: ReverseProxyUriResource does not support https connections,
                 so...better stick to non-proxy if the target resource is in a
                 secure connection until... we grant support for https
                 connections.
    '''

    is_proxy = False
    '''If the item should be considered a ReverseProxyUriResource. This
    property is automatically set when the item is initialized'''

    location = None
    '''Represents a file path of our media file, or alternatively a FilePath or
    a ReverseProxyResource object. It will be set automatically based on the
    value of the class :attr:`proxy_cls` (if the property :attr:`is_proxy`
    equals to True).'''

    proxy_cls = ReverseProxyUriResource
    '''Define a class inherited from
    :class:`~coherence.upnp.core.utils.ReverseProxyUriResource`. This property
    will only be used if the property :attr:`is_proxy` equals True.

    .. warning:: ReverseProxyResource does not support https. If your
                 resources point to a secure site, it's recommended to
                 not enable the :attr:`BackendBaseStore.proxy` (disabled
                 by default)
    '''

    item = None
    '''Define the initialized :attr:`item_cls`. It will be set when the class
    :class:`BackendBaseItem` is initialized based on the attribute
    :attr:`item_cls`'''

    item_cls = DIDLLite.Item
    '''Define an atomic object from :class:`~coherence.upnp.core.DIDLLite.Item`
    to be used to initialize the :attr:`item`'''

    mimetype = ''
    '''The mimetype of your item'''

    def __init__(self, parent_id, item_id, urlbase, **kwargs):
        super(BackendBaseItem, self).__init__()

        self.id = item_id
        self.parent_id = parent_id
        self.name = self.title = \
            kwargs.get('title',
                       kwargs.get('name',
                                  'My Backend Item'))
        self.http_url = kwargs.get('url', None)

        if len(urlbase) and urlbase[-1] != '/':
            urlbase += '/'
        self.url = urlbase + str(self.id)

        if 'is_proxy' in kwargs:
            self.is_proxy = kwargs['is_proxy']
        if 'mimetype' in kwargs:
            self.mimetype = kwargs['mimetype']

        if self.is_proxy and self.proxy_cls is not None:
            self.location = self.proxy_cls(self.http_url)
        elif self.is_proxy:
            self.warning('BackendBaseItem was unable to create a Proxy '
                         'location, falling back to non proxy...')
            self.is_proxy = False

        self.item = self.item_cls(
            self.id, self.parent_id, self.name)
        self.item.attachments = {}
        self.item.title = self.title

    def get_name(self):
        return self.title

    def get_children(self, start=0, request_count=0):
        return []

    def get_child_count(self):
        return 0

    def get_path(self):
        if self.is_proxy:
            return self.location
        if self.http_url:
            return self.http_url
        return self.url

    def __repr__(self):
        return \
            f'<BackendBaseItem {self.id} {self.title}' \
            f' [parent id: {self.parent_id}]>'


class BackendVideoItem(BackendBaseItem):
    '''
    This Represents a Backend Video Item.
    '''
    item_cls = DIDLLite.VideoItem

    def __init__(self, parent_id, item_id, urlbase, **kwargs):
        super(BackendVideoItem, self).__init__(
            parent_id, item_id, urlbase, **kwargs)

        self.director = kwargs.get('director', None)
        self.actors = kwargs.get('actors', [])
        self.genres = kwargs.get('genres', [])
        self.description = kwargs.get('description', None)
        self.image = kwargs.get('image', None)

        self.item.director = self.director
        self.item.actors = self.actors
        self.item.genres = self.genres
        self.item.description = self.description
        self.item.albumArtURI = self.image

    def __repr__(self):
        return \
            f'<BackendVideoItem{self.id} title="{self.title}" ' \
            f'genres="{", ".join(self.genres)}" director="{self.director}">'


class BackendAudioItem(BackendBaseItem):
    '''
    This Represents an Audio Item. It supports those properties:
        - :attr:`artist`: The name of the artist
        - :attr:`album`: an instance of a
            :class:`~coherence.backends.models.containers.BackendMusicAlbum`
        - :attr:`genre`: The music genre for the audio
        - :attr:`playlist`: Playlist
    '''
    item_cls = DIDLLite.AudioItem

    def __init__(self, parent_id, item_id, urlbase, **kwargs):
        super(BackendAudioItem, self).__init__(
            parent_id, item_id, urlbase, **kwargs)

        self.artist = kwargs.get('artist', None)
        self.album = kwargs.get('album', None)
        self.genre = kwargs.get('genre', None)
        self.image = kwargs.get('image', None)
        self.playlist = kwargs.get('playlist', None)

        self.item.artist = self.artist
        self.item.album = self.album
        self.item.genre = self.genre
        self.item.playlist = self.playlist
        self.item.albumArtURI = self.image

    def __repr__(self):
        album = 'None' if not self.album else self.album.title
        return \
            f'<BackendAudioItem{self.id} title="{self.title}" ' \
            f'album={self.album}" genre="{self.genre}" ' \
            f'artist="{self.artist}" path="{self.get_path()}">'


class BackendMusicTrackItem(BackendAudioItem):
    '''
    This is like :class:`BackendAudioItem` but with a track number added.
    '''
    item_cls = DIDLLite.MusicTrack

    def __init__(self, parent_id, item_id, urlbase, **kwargs):
        super(BackendMusicTrackItem, self).__init__(
            parent_id, item_id, urlbase, **kwargs)

        self.track_number = kwargs.get('track_number', 1)

        self.item.originalTrackNumber = self.track_number

    def __repr__(self):
        album = 'None' if not self.album else self.album.title
        return \
            f'<BackendMusicTrackItem{self.id} title="{self.title}" ' \
            f'track="{self.track_number}" album={album}" ' \
            f'genre="{self.genre}" artist="{self.artist}" ' \
            f'path="{self.get_path()}">'


class BackendImageItem(BackendBaseItem):
    '''
    This Represents a Backend Image Item.
    '''
    item_cls = DIDLLite.ImageItem
    mimetype = ''

    def __init__(self, parent_id, item_id, urlbase, **kwargs):
        super(BackendImageItem, self).__init__(
            parent_id, item_id, urlbase, **kwargs)

        self.artist = kwargs.get('artist', None)
        self.rating = kwargs.get('rating', None)
        self.publisher = kwargs.get('publisher', None)
        self.rights = kwargs.get('rights', None)

        self.item.artist = self.artist
        self.item.rating = self.rating
        self.item.publisher = self.publisher
        self.item.rights = self.rights

    def __repr__(self):
        return \
            f'<BackendImageItem {self.id} artist="{self.artist}" ' \
            f'rating="{self.rating}" publisher="{self.publisher}">'


class BackendPhotoItem(BackendImageItem):
    '''
    This Represents a Backend Photo Item. Iis like :class:`BackendImageItem`
    but with additional attribute added :attr:`album`.
    '''
    item_cls = DIDLLite.Photo

    def __init__(self, parent_id, item_id, urlbase, **kwargs):
        super(BackendPhotoItem, self).__init__(
            parent_id, item_id, urlbase, **kwargs)

        self.album = kwargs.get('album', None)
        self.item.album = self.album

    def __repr__(self):
        return \
            f'<BackendPhotoItem {self.id} artist="{self.artist}" ' \
            f'album="{self.album}" rating="{self.rating}">'
