# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2007, Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
Backend
=======

A set of base classes related with backends.

:class:`Backend`
----------------

The base class for all backends.

:class:`BackendStore`
---------------------

The base class for all MediaServer backend stores.

:class:`AbstractBackendStore`
-----------------------------

Inherits from :class:`BackendStore` and extends his capabilities.

:class:`BackendItem`
--------------------

The base class for all MediaServer backend items.

:class:`Container`
------------------

The base class for all containers. Actually his base class is the `BackendItem`
with a few modifications which extends his capabilities to store backend items.

:class:`LazyContainer`
----------------------

Inherits from :class:`Container` and extends his capabilities.

:class:`BackendRssMixin`
------------------------

A base class intended to be implemented into a subclass which creates a
deferred chain to retrieve a RDF file, parse it, extract the metadata and
reschedule itself.

.. note::
    RDF (Resource Description Framework) is a family of World Wide Web
    Consortium specifications originally designed as a metadata data model.

.. seealso::
    RDF extended information at wikipedia:
    https://en.wikipedia.org/wiki/Resource_Description_Framework
'''

import time
from operator import attrgetter
from abc import ABCMeta, abstractmethod

from lxml import etree

from eventdispatcher import (
    EventDispatcher, Property,
    ListProperty, DictProperty,
    StringProperty)

from coherence import log
from coherence.extern.simple_plugin import Plugin
from coherence.upnp.core import DIDLLite
from coherence.upnp.core.utils import getPage


class Backend(EventDispatcher, log.LogAble, Plugin):
    '''In the :class:`Backend` class we initialize the very basic stuff
    needed to create a Backend and registers some basic events needed to
    be successfully detected by our server.

    The init method for a backend, should probably most of the time be
    overwritten when the init is done and send a signal to its device. We
    can send this signal via two methods, depending on the nature of our
    backend. For instance, if we want that the backend to be notified
    without fetching any data we could simply set the attribute
    :attr:`init_completed` equal to True at the end of our init method of
    the backend, but in some cases, we will want to send this signal after
    some deferred call returns a result...in that case we should process
    slightly differently, you can see how to do that at the end of the
    init method of the class
    :class:`~coherence.backends.models.stores.BackendBaseStore`.

    After that, the device will then setup, announce itself and should
    call to the backend's method :meth:`upnp_init`.

    .. versionchanged:: 0.9.0

        * Introduced inheritance from EventDispatcher
        * The emitted events changed:

            - Coherence.UPnP.Backend.init_completed => backend_init_completed

        * Added new event: backend_init_failed
        * Added new method :meth:`on_init_failed`
        * Moved class method `init_completed` to `on_init_completed` and added
          class variable :attr:`init_completed`

    .. note::
        We can also use this init class to do whatever is necessary with
        the stuff we can extract from the config dict, connect maybe to an
        external data-source and start up the backend or if there are any UPnP
        service actions (Like maybe upnp_Browse for the CDS Browse action),
        that can't be handled by the service classes itself, or need some
        special adjustments for the backend, they probably will need to be
        defined into the method :meth:`__init__`.
    '''

    logCategory = 'backend'

    implements = []
    '''A list of the device classe like:

        ['MediaServer','MediaRenderer']
    '''

    init_completed = Property(False)
    '''To know whenever the backend init has completed. This has to be done in
    the actual backend, maybe it has to wait for an answer from an external
    data-source first...so...the backend should set this variable to `True`,
    then the method :meth:`on_init_completed` will be automatically
    triggered dispatching an event announcing that the backend has been
    initialized.'''

    def __init__(self, server, *args, **kwargs):
        '''
        Args:
            server (object): This usually should be an instance of our main
                class :class:`~coherence.base.Coherence` (the UPnP device
                that's hosting our backend).
            *args (list): A list with extra arguments for the backend. This,
                must be implemented into the subclass (if needed).
            **kwargs (dict): An unpacked dictionary with the backend's
                configuration.
        '''

        self.config = kwargs
        self.server = server

        EventDispatcher.__init__(self)
        log.LogAble.__init__(self)
        Plugin.__init__(self)
        self.register_event(
            'backend_init_completed',
            'backend_init_failed'
        )

    def on_init_completed(self, *args, **kwargs):
        '''
        Inform Coherence that this backend is ready for announcement. This
        method just accepts any form of arguments as we don't under which
        circumstances it is called.
        '''
        self.dispatch_event('backend_init_completed', backend=self, **kwargs)

    def on_init_failed(self, *args, **kwargs):
        '''
        Inform Coherence that this backend has failed.

        .. versionadded:: 0.9.0
        '''
        self.dispatch_event('backend_init_failed', backend=self, **kwargs)

    def upnp_init(self):
        '''
        This method gets called after the device is fired, here all
        initializations of service related state variables should happen, as
        the services aren't available before that point.
        '''
        pass


class BackendStore(Backend):
    '''
    The base class for all MediaServer backend stores. Inherits from class
    :class:`Backend` and extends his capabilities to make easy to create
    a Backend Store by setting an initial wmc mapping, and defining some
    attributes and methods needed by a Backend Store.
    '''

    __metaclass__ = ABCMeta

    logCategory = 'backend_store'

    def __init__(self, server, *args, **kwargs):
        '''
        Args:
            server (object): This usually should be an instance of our main
                class :class:`~coherence.base.Coherence` (the UPnP device
                that's hosting our backend).
            *args (list): A list with extra arguments for the backend. This,
                must be implemented into the subclass (if needed).
            **kwargs (dict): An unpacked dictionary with the backend's
                configuration.
        .. note::
            In case we want so serve something via the MediaServer web backend,
            the class :class:`BackendItem` should pass an URI assembled of
            urlbase + '/' + id to the
            :class:`~coherence.upnp.core.DIDLLite.Resource`.

        .. warning::
            Remember to sent the event init_completed via setting to `True`
            the attribute :attr:`init_completed`. Check the base class
            :class:`Backend` for instructions about how to do it.
        '''
        Backend.__init__(self, server, *args, **kwargs)
        self.update_id = 0

        self.urlbase = kwargs.get('urlbase', '')
        if not self.urlbase.endswith('/'):
            self.urlbase += '/'

        self.wmc_mapping = {'4': '4', '5': '5', '6': '6', '7': '7', '14': '14',
                            'F': 'F',
                            '11': '11', '16': '16', 'B': 'B', 'C': 'C',
                            'D': 'D',
                            '13': '13', '17': '17',
                            '8': '8', '9': '9', '10': '10', '15': '15',
                            'A': 'A', 'E': 'E'}

        self.wmc_mapping.update({'4': lambda: self._get_all_items(0),
                                 '8': lambda: self._get_all_items(0),
                                 'B': lambda: self._get_all_items(0),
                                 })

    def release(self):
        '''If anything needs to be cleaned up upon shutdown of this backend,
        this is the place for it. Should be overwritten in subclass.'''
        pass

    def _get_all_items(self, id):
        '''A helper method to get all items as a response to some XBox 360
        UPnP Search action probably never be used as the backend will overwrite
        the wmc_mapping with more appropriate methods.
        '''
        items = []
        item = self.get_by_id(id)
        if item is not None:
            containers = [item]
            while len(containers) > 0:
                container = containers.pop()
                if container.mimetype not in ['root', 'directory']:
                    continue
                for child in container.get_children(0, 0):
                    if child.mimetype in ['root', 'directory']:
                        containers.append(child)
                    else:
                        items.append(child)
        return items

    @abstractmethod
    def get_by_id(self, id):
        '''
        Args:
            id (object): is the id property of our DIDLLite item

        Returns:
            - None when no matching item for that id is found,
            - a BackendItem,
            - or a Deferred

        Called by the CDS or the MediaServer web.

        .. note::
            if this MediaServer implements containers that can share their
            content, like 'all tracks', 'album' and 'album_of_artist' (they all
            have the same track item as content), then the id may be passed by
            the CDS like this:

                'id@container' or 'id@container@container@container...'

            therefore a

            .. code-block:: python

                if isinstance(id, basestring):
                    id = id.split('@',1)
                    id = id[0]

            may be appropriate as the first thing to do when entering this
            method.
        '''
        return None


class BackendItem(EventDispatcher, log.LogAble):
    '''This is the base class for all MediaServer backend items.

    Most of the time we collect the necessary data for an UPnP
    ContentDirectoryService Container or Object and instantiate it into the
    :meth:`__init__`

    .. code-block:: python

        self.item = DIDLLite.Container(id,parent_id,name,...)

    or

    .. code-block:: python

        self.item = DIDLLite.MusicTrack(id,parent_id,name,...)

    To make that a valid UPnP CDS Object it needs one or more
    DIDLLite. :class:`~coherence.upnp.core.DIDLLite.Resource`

    .. code-block:: python

        self.item.res = []
        res = DIDLLite.Resource(url, f'http-get:*:{mimetype}:*')
        res.size = size
        self.item.res.append(res)

    .. note:: url should be the urlbase of our backend + '/' + our id.

    .. versionchanged:: 0.9.0

        * Introduced inheritance from EventDispatcher
        * Moved class variable :attr:`update_id` to class
          :attr:`Container.update_id`
        * Added class variable :attr:`mimetype` to benefit from the
          EventDispatcher's properties
    '''

    logCategory = 'backend_item'

    name = 'backend_item_name'
    '''the basename of a file, the album title, the artists name...is expected
    to be unicode'''

    location = None
    '''the filepath of our media file, or alternatively a FilePath or
    a ReverseProxyResource object'''

    cover = None
    '''if we have some album art image, let's put the filepath or
    link into here'''

    store = None
    '''The backend store.'''
    storage_id = None
    '''The id of the backend store.'''

    item = None
    '''Usually an atomic object from
    :class:`~coherence.upnp.core.DIDLLite.Item` or derived.'''

    mimetype = StringProperty('')
    '''The mimetype variable describes the protocol info for the object.'''

    def __init__(self, *args, **kwargs):
        EventDispatcher.__init__(self)
        log.LogAble.__init__(self)

    def get_children(self, start=0, end=0):
        '''
        Called by the CDS and the MediaServer web.

        Args:
            start (int): the start.
            end (int): the end.

        Returns:
            - a list of its childs, from start to end.
            - or a Deferred
        '''
        pass

    def get_child_count(self):
        '''
        Called by the CDS.

        Returns:
            - the number of its childs - len(childs)
            - or a Deferred
        '''
        pass

    def get_item(self):
        '''
        Called by the CDS and the MediaServer web.

        Returns:
            - an UPnP ContentDirectoryServer DIDLLite object
            - or a Deferred
        '''
        return self.item

    def get_name(self):
        '''
        Called by the MediaServer web.

        Returns:
            the name of the item, it is always expected to be in unicode.
        '''
        return self.name

    def get_path(self):
        '''
        Called by the MediaServer web.

        Returns:
            the filepath where to find the media file that this item does
            refer to.
        '''
        return self.location

    def get_cover(self):
        '''
        Called by the MediaServer web.

        Returns:
            the filepath where to find the album art file

        .. note:: only needed when we have created for that item an
            albumArtURI property that does point back to us.
        '''
        return self.cover

    def __repr__(self):
        return f'{self.__class__.__name__}[{self.get_name()}]'


class BackendRssMixin:

    def __init__(self):
        pass

    def update_data(self, rss_url, container=None):
        '''Creates a deferred chain to retrieve the rdf file, parse and extract
        the metadata and reschedule itself.'''

        def fail(f):
            # TODO fix loggable thing
            self.info(f'fail {f}')
            self.debug(f.getTraceback())
            return f

        dfr = getPage(rss_url)
        dfr.addCallback(etree.fromstring)
        dfr.addErrback(fail)
        dfr.addCallback(self.parse_data, container)
        dfr.addErrback(fail)
        dfr.addBoth(self.queue_update, rss_url, container)
        return dfr

    def parse_data(self, xml_data, container):
        '''Extract media info and create BackendItems'''
        pass

    def queue_update(self, error_or_failure, rss_url, container):
        from twisted.internet import reactor
        reactor.callLater(self.refresh, self.update_data, rss_url, container)


class Container(BackendItem):
    '''
    Represents a backend item which will contains backend items inside.

    .. versionchanged:: 0.9.0

        * Added static class variable :attr:`update_id`
        * Changed some variables to benefit from the EventDispatcher's
          properties:

            - :attr:`children`
            - :attr:`children_ids`
            - :attr:`children_by_external_id`
            - :attr:`parent`
    '''

    update_id = Property(0)
    '''It represents the update id of thhe container. This should be
    incremented on every modification of the UPnP ContentDirectoryService
    Container, as we do in methods :meth:`add_child` and :meth:`remove_child`.
    '''

    children = ListProperty([])
    '''A list of the backend items.'''
    children_ids = DictProperty({})
    '''A dictionary of the backend items by his id.'''
    children_by_external_id = DictProperty({})
    '''A dictionary of the backend items by his external id.'''

    parent = Property(None)
    '''The parent object for this class.'''
    parent_id = -1
    '''The id of the parent object. This will be automatically set whenever
    we set the attribute :attr:`parent`.
    '''

    mimetype = 'directory'
    '''The mimetype variable describes the protocol info for the object. In a
    :class:`Container` this should be set to value `directory` or `root`.
    '''

    def __init__(self, parent, title):
        BackendItem.__init__(self)

        self.parent = parent
        self.name = title

        self.sorted = False
        self.sorting_method = 'name'

    def on_parent(self, parent):
        if self.parent is not None:
            self.parent_id = self.parent.get_id()

    def register_child(self, child, external_id=None):
        id = self.store.append_item(child)
        child.url = self.store.urlbase + str(id)
        child.parent = self
        if external_id is not None:
            child.external_id = external_id
            self.children_by_external_id[external_id] = child

    def add_child(self, child, external_id=None, update=True):
        self.register_child(child, external_id)
        if self.children is None:
            self.children = []
        self.children.append(child)
        self.sorted = False
        if update:
            self.update_id += 1

    def remove_child(self, child, external_id=None, update=True):
        self.children.remove(child)
        self.store.remove_item(child)
        if update:
            self.update_id += 1
        if external_id is not None:
            child.external_id = None
            del self.children_by_external_id[external_id]

    def get_children(self, start=0, end=0):
        if not self.sorted:
            self.children = sorted(
                self.children,
                key=attrgetter(self.sorting_method))
            self.sorted = True
        if end != 0:
            return self.children[start:end]
        return self.children[start:]

    def get_child_count(self):
        if self.children is None:
            return 0
        return len(self.children)

    def get_path(self):
        return self.store.urlbase + str(self.storage_id)

    def get_item(self):
        if self.item is None:
            self.item = DIDLLite.Container(self.storage_id, self.parent_id,
                                           self.name)
        self.item.childCount = len(self.children)
        return self.item

    def get_name(self):
        return self.name

    def get_id(self):
        return self.storage_id

    def get_update_id(self):
        return self.update_id


class LazyContainer(Container):
    logCategory = 'lazyContainer'

    def __init__(self, parent, title, external_id=None, refresh=0,
                 childrenRetriever=None, **kwargs):
        Container.__init__(self, parent, title)

        self.childrenRetrievingNeeded = True
        self.childrenRetrievingDeferred = None
        self.childrenRetriever = childrenRetriever
        self.children_retrieval_campaign_in_progress = False
        self.childrenRetriever_params = kwargs
        self.childrenRetriever_params['parent'] = self
        self.has_pages = ('per_page' in self.childrenRetriever_params)

        self.external_id = None
        self.external_id = external_id

        self.retrieved_children = {}

        self.last_updated = 0
        self.refresh = refresh

    def replace_by(self, item):
        if self.external_id is not None and item.external_id is not None:
            return self.external_id == item.external_id
        return True

    def add_child(self, child, external_id=None, update=True):
        if self.children_retrieval_campaign_in_progress is True:
            self.retrieved_children[external_id] = child
        else:
            Container.add_child(self, child, external_id=external_id,
                                update=update)

    def update_children(self, new_children, old_children):
        children_to_be_removed = {}
        children_to_be_replaced = {}
        children_to_be_added = {}

        # Phase 1
        # let's classify the item between items to be removed,
        # to be updated or to be added
        self.debug(
            f'Refresh pass 1:{len(new_children):d} {len(old_children):d}')
        for id, item in list(old_children.items()):
            children_to_be_removed[id] = item
        for id, item in list(new_children.items()):
            if id in old_children:
                # print(id, 'already there')
                children_to_be_replaced[id] = old_children[id]
                del children_to_be_removed[id]
            else:
                children_to_be_added[id] = new_children[id]

        # Phase 2
        # Now, we remove, update or add the relevant items
        # to the list of items
        self.debug(
            f'Refresh pass 2: {len(children_to_be_removed):d} '
            f'{len(children_to_be_replaced):d} {len(children_to_be_added):d}')
        # Remove relevant items from Container children
        for id, item in list(children_to_be_removed.items()):
            self.remove_child(item, external_id=id, update=False)
        # Update relevant items from Container children
        for id, item in list(children_to_be_replaced.items()):
            old_item = item
            new_item = new_children[id]
            replaced = False
            if hasattr(old_item, 'replace_by'):
                replaced = old_item.replace_by(new_item)
            if replaced is False:
                # print('No replacement possible:
                #       we remove and add the item again')
                self.remove_child(old_item, external_id=id, update=False)
                self.add_child(new_item, external_id=id, update=False)
        # Add relevant items to COntainer children
        for id, item in list(children_to_be_added.items()):
            self.add_child(item, external_id=id, update=False)

        self.update_id += 1

    def start_children_retrieval_campaign(self):
        self.last_updated = time.time()
        self.retrieved_children = {}
        self.children_retrieval_campaign_in_progress = True

    def end_children_retrieval_campaign(self, success=True):
        self.children_retrieval_campaign_in_progress = False
        if success is True:
            self.update_children(self.retrieved_children,
                                 self.children_by_external_id)
            self.update_id += 1
        self.last_updated = time.time()
        self.retrieved_children = {}

    def retrieve_children(self, start=0, page=0):

        def items_retrieved(result, page, start_offset):
            if self.childrenRetrievingNeeded is True:
                new_offset = len(self.retrieved_children)
                return self.retrieve_children(
                    new_offset, page + 1)  # we try the next page
            return self.retrieved_children

        self.childrenRetrievingNeeded = False
        if self.has_pages is True:
            self.childrenRetriever_params['offset'] = start
            self.childrenRetriever_params['page'] = page
        d = self.childrenRetriever(**self.childrenRetriever_params)
        d.addCallback(items_retrieved, page, start)
        return d

    def retrieve_all_children(self, start=0, request_count=0):

        def all_items_retrieved(result):
            self.end_children_retrieval_campaign(True)
            return super(LazyContainer, self).get_children(
                start, request_count)

        def error_while_retrieving_items(error):
            self.end_children_retrieval_campaign(False)
            return super(LazyContainer, self).get_children(
                start, request_count)

        self.start_children_retrieval_campaign()
        if self.childrenRetriever is not None:
            d = self.retrieve_children(start)
            if start == 0:
                d.addCallbacks(all_items_retrieved,
                               error_while_retrieving_items)
            return d
        else:
            self.end_children_retrieval_campaign()
            return self.children

    def get_children(self, start=0, request_count=0):

        # Check if an update is needed since last update
        current_time = time.time()
        delay_since_last_updated = current_time - self.last_updated
        period = self.refresh
        if (period > 0) and (delay_since_last_updated > period):
            self.info(f'Last update is older than {period:d} s -> update data')
            self.childrenRetrievingNeeded = True

        if self.childrenRetrievingNeeded is True:
            return self.retrieve_all_children(start, request_count)
        return Container.get_children(self, start, request_count)


ROOT_CONTAINER_ID = 0
SEED_ITEM_ID = 1000


class AbstractBackendStore(BackendStore):
    def __init__(self, server, **kwargs):
        BackendStore.__init__(self, server, **kwargs)
        self.next_id = SEED_ITEM_ID
        self.store = {}

    def len(self):
        return len(self.store)

    def set_root_item(self, item):
        return self.append_item(item, storage_id=ROOT_CONTAINER_ID)

    def get_root_id(self):
        return ROOT_CONTAINER_ID

    def get_root_item(self):
        return self.get_by_id(ROOT_CONTAINER_ID)

    def append_item(self, item, storage_id=None):
        if storage_id is None:
            storage_id = self.getnextID()
        self.store[storage_id] = item
        item.storage_id = storage_id
        item.store = self
        return storage_id

    def remove_item(self, item):
        del self.store[item.storage_id]
        item.storage_id = -1
        item.store = None

    def get_by_id(self, id):
        if isinstance(id, str):
            id = id.split('@', 1)
            id = id[0].split('.')[0]
        try:
            return self.store[int(id)]
        except (ValueError, KeyError):
            pass
        return None

    def getnextID(self):
        ret = self.next_id
        self.next_id += 1
        return ret

    def __repr__(self):
        return self.__class__.__name__
