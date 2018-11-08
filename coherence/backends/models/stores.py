# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2018, Pol Canelles <canellestudi@gmail.com>
'''
Backend models for BackendStore
-------------------------------

Backend stores to be subclassed. The base class `BackendBaseStore` inherits
from :class:`~coherence.backend.BackendStore`. The
:mod:`~coherence.backends.models.store` classes represents some basic stores
to create backend's media servers. The available backend stores are:

    - :class:`BackendBaseStore`: the base class for all the backend stores.
            .. note:: All the Backend items are stored into a class variable
                :attr:`BackendBaseStore.container` and it is a class of
                :class:`~coherence.backends.models.containers.BackendContainer`
    - :class:`BackendVideoStore`: media server for video items. The default
            backend items are instances of
            :class:`~coherence.backends.models.items.BackendVideoItem`
    - :class:`BackendAudioStore`: media server for audio items. The default
            backend items are instances of
            :class:`~coherence.backends.models.items.BackendAudioItem`
    - :class:`BackendImageStore`: media server for audio items. The default
            backend items are instances of
            :class:`~coherence.backends.models.items.BackendImageItem`

.. note:: Be aware that we use super to initialize all the classes of this
          module in order to have a better MRO class resolution...so...take it
          into account if you inherit from one of this classes.

.. versionadded:: 0.8.3
'''

from lxml import etree

from twisted.internet import task, reactor
from twisted.web import client

from coherence.backend import BackendStore
from coherence.backends.models.containers import BackendContainer
from coherence.backends.models.items import *


class BackendBaseStore(BackendStore):
    '''
    The Base class to create a server which will hold some kind of items.
    This class will do most of the work:
    download page set in root_url, find items based on root_find_items and also
    will create the right item type to add into your container.

    .. warning:: This class is intended to be used as a base class to create
                 a custom BackendStore, so...some variables must be set into
                 the corresponding inherited class. The mandatory variables
                 are: item_cls, item_type, root_url, root_find_items.
                 Also be sure to overwrite the method
                 :meth:`~coherence.backend_models.BackendBaseStore.parse_item`
                 in your inherited class.
    .. versionchanged:: 0.9.0
        Migrated from louie/dispatcher to EventDispatcher
    '''
    logCategory = 'BackendBaseStore'
    implements = ['MediaServer']

    upnp_protocols = []
    '''The upnp protocols that the server should be capable to manage.'''

    container_cls = BackendContainer
    '''The container class used to store your BackendItems.'''

    item_cls = BackendBaseItem
    '''The class used for your items.'''
    item_type = ''

    name = 'Backend Base Store'
    '''The name of the store.'''
    root_id = 0
    '''The id of the store.'''
    root_url = None
    '''The root url to parse.'''
    root_find_items = ''
    '''The xml's findall command to parse your items. For example, if your xml
    data/file looks like this::

        <root>
            <item>
                <name>Example item 1</name>
            </item>
            <item>
                <name>Example item 2</name>
            </item>
        </root>

    The :attr:`root_find_items` should be::

        root_find_items = './root/item'

    '''

    def __init__(self, server, *args, **kwargs):

        super(BackendBaseStore, self).__init__(server, **kwargs)

        for prop in [
                'item_cls', 'item_type',
                'root_url', 'root_find_items']:
            if prop in [None, '', [], {}]:
                raise Exception(
                    f'Error: The property for {self!r}.{prop}'
                    f' cannot be empty')

        if 'name' in kwargs:
            self.name = kwargs.get('name')

        self.refresh = int(kwargs.get('refresh', 8)) * (60 * 60)

        if kwargs.get('proxy', 'no') in [
                1, 'Yes', 'yes', 'True', 'true']:
            self.proxy = True
        else:
            self.proxy = False

        self.next_id = 1000

        self.items = {}
        self.container = self.container_cls(
            self.root_id, -1, self.name,
            store=self, storage_id=self.root_id)

        self.wmc_mapping = kwargs.get(
            'wmc_mapping', {'15': self.root_id})

        dfr = self.update_data()
        # first get the first bunch of data before sending init_completed

        def init_completed(*args):
            self.init_completed = True

        def init_failed(*args):
            print(f'init_failed: {args}')
            self.on_init_failed(*args)

        dfr.addCallback(init_completed)
        dfr.addErrback(init_failed)

    def queue_update(self, result):
        '''
        Schedules a refresh of the media server data.
        '''
        reactor.callLater(self.refresh, self.update_data)
        return result

    def update_data(self):
        self.info('BackendBaseStore.update_data: triggered')

        def deferred_fail(d):
            self.error(f"BackendBaseStore.update_data: {d}")
            self.debug(d.getTraceback())
            return d

        dfr = client.getPage(self.root_url)
        dfr.addCallback(etree.fromstring)
        dfr.addErrback(deferred_fail)
        dfr.addCallback(self.parse_data)
        dfr.addErrback(deferred_fail)
        dfr.addCallback(self.queue_update)
        return dfr

    def parse_data(self, root):
        '''
        Iterate over all items found inside the provided tree and parse each
        one of them.
        '''
        self.info(f'BackendBaseStore.parse_data: {root}')

        def iterate(r):
            for el in r.findall(self.root_find_items):
                data = self.parse_item(el)
                if data is None:
                    continue
                item = self.add_item(data)
                yield item

        return task.coiterate(iterate(root))

    def parse_item(self, item):
        '''
        Convenient method to extract data from an item.

        .. warning:: this method must be sub classed and must return a
                     dictionary which should hold the data that you want to be
                     set for your items.
        '''
        return {}

    def add_item(self, data):
        '''
        Creates and adds an instance of your defined item_cls into the
        `:attr:container_cls`. The item will be initialized with the provided
        data, collected from the method
        :meth:`~coherence.backend_modules.BackendBaseStore.parse_item`
        '''
        backend_item = self.item_cls(
            self.root_id, self.next_id, self.urlbase,
            is_proxy=self.proxy, **data)

        res = DIDLLite.Resource(
            backend_item.get_path(), self.item_type)
        backend_item.item.res.append(res)

        self.items[self.next_id] = backend_item
        self.container.children.append(backend_item)

        self.next_id += 1

        self.container.update_id += 1
        self.update_id += 1

        # Update the content_directory_server
        if self.server and hasattr(
                self.server, 'content_directory_server'):
            self.server.content_directory_server.set_variable(
                0, 'SystemUpdateID', self.update_id)
            value = (self.root_id, self.container.update_id)
            self.server.content_directory_server.set_variable(
                0, 'ContainerUpdateIDs', value)
        return backend_item

    def get_by_id(self, item_id):
        '''
        Get an item based on his id.
        '''
        self.debug(f'BackendBaseStore.get_by_id: {item_id}')
        if item_id in self.items:
            return self.items.get(item_id)
        if isinstance(item_id, str):
            item_id = item_id.split('@', 1)[0]
        elif isinstance(item_id, bytes):
            item_id = item_id.decode('utf-8').split('@', 1)[0]
        try:
            int_id = int(item_id)
            if int_id == self.root_id:
                return self.container
            else:
                return self.items.get(int_id, None)
        except Exception:
            return None

    def upnp_init(self):
        '''
        Define what kind of media content we do provide
        '''
        self.info(f'BackendBaseStore.upnp_init: server => {self.server}')
        if self.server:
            self.server.connection_manager_server.set_variable(
                0, 'SourceProtocolInfo',
                self.upnp_protocols)

    def __repr__(self):
        return self.__class__.__name__


class BackendVideoStore(BackendBaseStore):
    '''
    The Base class to create a server for Video items. This class supports most
    typical upnp video protocols. If you need some video protocol not listed,
    you can subclass with your protocols according to your needs.

    .. note:: See the base class :class:`BackendBaseStore` for more detailed
              information

    .. warning:: The default variable for item_type has been established to
                 'http-get:*:video/mp4:*'. Make sure to set the right video
                 protocol for your needs
    '''
    logCategory = 'BackendVideoStore'
    upnp_protocols = [
        'http-get:*:video/mp4:*',
        'http-get:*:video/mp4v:*',
        'http-get:*:video/mpeg:*',
        'http-get:*:video/mpegts:*',
        'http-get:*:video/matroska:*',
        'http-get:*:video/h264:*',
        'http-get:*:video/h265:*',
        'http-get:*:video/avi:*',
        'http-get:*:video/divx:*',
        'http-get:*:video/quicktime:*',
        'http-get:*:video/x-msvideo:*',
        'http-get:*:video/x-ms-wmv:*',
        'http-get:*:video/ogg:*',
    ]

    item_cls = BackendVideoItem
    item_type = 'http-get:*:video/mp4:*'

    name = 'Backend Video Store'


class BackendAudioStore(BackendBaseStore):
    '''
    The Base class to create a server for Audio items. This class supports most
    typical upnp audio protocols. If you need some audio protocol not listed,
    you can subclass with your protocols according to your needs.

    .. warning:: The default variable for item_type has been established to
                 'http-get:*:audio/mpeg:*' (which should be fine for mp3).
                 Make sure to set the right audio protocol for your needs.
    '''
    logCategory = 'BackendAudioStore'
    upnp_protocols = [
        'http-get:*:audio/mp4:*',
        'http-get:*:audio/mp4a:*',
        'http-get:*:audio/mpeg:*',
        'http-get:*:audio/x-wav:*',
        'http-get:*:audio/x-scpls:*',
        'http-get:*:audio/x-msaudio:*',
        'http-get:*:audio/x-ms-wma:*',
        'http-get:*:audio/flac:*',
        'http-get:*:audio/ogg:*',
    ]

    item_cls = BackendVideoItem
    item_type = 'http-get:*:audio/mpeg:*'

    name = 'Backend Audio Store'


class BackendImageStore(BackendBaseStore):
    '''
    The Base class to create a server for Image items. This class supports most
    typical upnp image protocols. If you need some image protocol not listed,
    you can subclass with your protocols according to your needs.

    .. warning:: The default variable for item_type has been established to
                 'http-get:*:audio/jpeg:*'. Make sure to set the right image
                 protocol for your needs.
    '''
    logCategory = 'BackendImageStore'
    upnp_protocols = [
        'http-get:*:image/jpeg:*',
        'http-get:*:image/jpg:*',
        'http-get:*:image/gif:*',
        'http-get:*:image/png:*',
    ]

    item_cls = BackendImageItem
    item_type = 'http-get:*:image/jpeg:*'

    name = 'Backend Image Store'
