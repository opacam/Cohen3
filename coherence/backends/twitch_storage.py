# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2015, https://github.com/unintended

'''
A backend to access twitch.tv streams.

To enable personalized features (e.g. 'Following' streams),
add 'access_token' key into your config file:

  1. Click the link below to automatically request an access token for your
     account:

     `Go twitch's 'get access token' page
     <https://api.twitch.tv/kraken/oauth2/authorize?response_type=token&
     client_id=37684tuwyxmogmtduz6lz0jdtf0acob&redirect_uri=
     http://localhost&scope=user_read>`_

  2. After authorization you will be redirected to http://localhost with
     access token in fragment part, e.g:

        **http://localhost/#access_token=
        <YOUR_ACCESS_TOKEN_IS_HERE> &scope=user_read**

  3. Copy the token and paste in TwitchStore section of your config file:

        access_token = <YOUR_ACCESS_TOKEN (step 2)>
'''

import json
import urllib.error
import urllib.parse
import urllib.request

import livestreamer
from dateutil import parser as dateutil_parser
from twisted.internet import threads
from twisted.python.failure import Failure
from twisted.web import server, http
from twisted.web.resource import Resource
from twisted.web.static import NoRangeStaticProducer

from coherence.backend import AbstractBackendStore, Container, BackendItem, \
    LazyContainer
from coherence.log import LogAble
from coherence.upnp.core import utils, DIDLLite

MPEG_MIME = 'video/mpeg'

TWITCH_API_URL = 'https://api.twitch.tv/kraken'


class LiveStreamerProxyResource(Resource, LogAble):
    logCategory = 'twitch_store'

    def __init__(self, url, stream_id, content_type=MPEG_MIME):
        Resource.__init__(self)
        LogAble.__init__(self)
        self.url = url
        self.stream_id = stream_id
        self.content_type = content_type

    def render_GET(self, request):
        self.debug(f'serving {request.method} request from '
                   f'{request.getClientIP()} for {request.uri}')

        def stream_opened(fd):
            producer = NoRangeStaticProducer(request, fd)
            producer.start()

        def got_streams(streams):
            if self.stream_id not in streams:
                self.warning(f'stream not found for '
                             f'{self.url}@{self.stream_id}')
                request.setResponseCode(http.NOT_FOUND)
                request.write(b'')
                return

            request.setHeader(b'Content-Type',
                              self.content_type.encode('ascii'))
            request.setResponseCode(http.OK)

            if request.method == b'HEAD':
                request.write(b'')
                return

            d_open_stream = threads.deferToThread(streams[self.stream_id].open)
            d_open_stream.addCallback(stream_opened)

        d_get_streams = threads.deferToThread(livestreamer.streams, self.url)
        d_get_streams.addCallback(got_streams)

        return server.NOT_DONE_YET


class TwitchLazyContainer(LazyContainer):
    logCategory = 'twitch_store'

    def __init__(self, parent, title, limit=None, **kwargs):
        super(TwitchLazyContainer, self).__init__(parent, title, **kwargs)

        self.childrenRetriever = self._retrieve_children
        self.refresh = 60
        self.children_url = None
        self.limit = limit

    def result_handler(self, result, **kwargs):
        return True

    def _retrieve_children(self, parent=None, **kwargs):
        if self.children_url is None:
            return

        kwargs.update({'limit': self.limit})
        kwargs = {k: v for k, v in list(kwargs.items()) if v is not None}

        url = '%s?%s' % (self.children_url, urllib.parse.urlencode(
            kwargs)) if kwargs else self.children_url

        d = utils.getPage(url)
        d.addCallbacks(self._got_page, self._got_error)
        return d

    def _got_page(self, result):
        self.info('connection to twitch service successful for game list')
        result = json_loads(result)
        return self.result_handler(result)

    def _got_error(self, error):
        self.warning(
            f'connection to twitch.tv service failed: {self.children_url}')
        self.debug(f'{error.getTraceback()}')
        self.childrenRetrievingNeeded = True  # we retry
        return Failure('Unable to retrieve game list')


class GamesContainer(TwitchLazyContainer):
    def __init__(self, parent, title='Games', description=None, limit=None,
                 children_limit=None, **kwargs):
        super(GamesContainer, self).__init__(parent, title, limit=limit,
                                             **kwargs)
        self.description = description

        self.children_url = f'{TWITCH_API_URL}/games/top'
        self.sorting_method = 'viewers'
        self.children_limit = children_limit

    def result_handler(self, result, **kwargs):
        for game_info in result['top']:
            game_name = game_info['game']['name']
            item = StreamsContainer(
                self, game_name,
                viewers=game_info['viewers'],
                channels=game_info['channels'],
                cover_url=game_info['game']['box']['large'],
                game=game_name,
                limit=self.children_limit)
            # item.description = f'{game_info["viewers"]:d} viewers'
            self.add_child(item, external_id=game_info['game']['_id'])
        return True


class StreamsContainer(TwitchLazyContainer):
    URL = '%s/streams/'

    def __init__(self, parent, title, viewers=0, channels=0, streams_url=URL,
                 cover_url=None, **kwargs):
        super(StreamsContainer, self).__init__(parent, title, **kwargs)
        self.viewers = viewers
        self.channels = channels

        self.children_url = streams_url % TWITCH_API_URL
        self.cover_url = cover_url
        self.sorting_method = 'viewers'

    def result_handler(self, result, **kwargs):
        for stream in result['streams']:
            created_at = dateutil_parser.parse(stream['created_at'])
            item = TwitchStreamItem(
                stream['channel']['display_name'],
                stream['channel']['url'],
                status=stream['channel']['status'],
                viewers=stream['viewers'],
                preview_url=stream['preview']['medium'],
                created_at=created_at)
            self.add_child(item, external_id=f'stream{stream["_id"]:d}')
        return True


class TwitchStreamItem(BackendItem):
    logCategory = 'twitch_store'

    def __init__(self, title, url, status=None, viewers=0, created_at=None,
                 preview_url=None):
        BackendItem.__init__(self)
        self.name = title
        self.status = status
        self.mimetype = MPEG_MIME
        self.created_at = created_at
        self.viewers = viewers
        self.url = url
        self.preview_url = preview_url
        self.location = LiveStreamerProxyResource(url, 'best')
        self.parent = None

    def get_item(self):
        if self.item is None:
            upnp_id = self.get_id()
            upnp_parent_id = self.parent.get_id()

            self.item = DIDLLite.VideoItem(upnp_id, upnp_parent_id, self.name)
            self.item.description = self.status
            self.item.longDescription = self.status
            self.item.date = self.created_at
            self.item.albumArtURI = self.preview_url

            res = DIDLLite.Resource(self.url, f'http-get:*:{MPEG_MIME}:#')
            self.item.res.append(res)
        return self.item

    def get_id(self):
        return self.storage_id

    def get_url(self):
        return self.url

    def replace_by(self, item):
        # TODO update fields
        return True


class TwitchStore(AbstractBackendStore):
    logCategory = 'twitch_store'

    implements = ['MediaServer']

    wmc_mapping = {'16': 1000}

    description = ('twitch.tv', 'twitch.tv', None)

    options = [
        {'option': 'name',
         'text': 'Server Name:',
         'type': 'string',
         'default': 'twitch.tv',
         'help': 'the name under this MediaServer shall '
                 'show up with on other UPnP clients'},
        {'option': 'access_token',
         'text': 'OAuth Access Token:',
         'type': 'string',
         'default': '',
         'help': 'access token to show personalized list of followed streams'},
        {'option': 'version',
         'text': 'UPnP Version:',
         'type': 'int',
         'default': 2,
         'enum': (2, 1),
         'help': 'the highest UPnP version this MediaServer shall support',
         'level': 'advance'},
        {'option': 'uuid',
         'text': 'UUID Identifier:',
         'type': 'string',
         'default': 'twitch_tv',
         'help': 'the unique (UPnP) identifier for this MediaServer',
         'level': 'advance'}]

    def __init__(self, server, **kwargs):
        AbstractBackendStore.__init__(self, server, **kwargs)

        self.name = self.config.get('name', 'twitch.tv')
        self.uuid = self.config.get('uuid', 'twitch_tv')
        self.access_token = self.config.get('access_token')

        self.init_completed()

    def __repr__(self):
        return self.__class__.__name__

    def upnp_init(self):
        if self.server:
            self.server.connection_manager_server.set_variable(
                0, 'SourceProtocolInfo',
                [f'http-get:*:{MPEG_MIME}:*'],
                default=True)
        # root item
        root_item = Container(None, self.name)
        self.set_root_item(root_item)

        # 'Following' directory
        settings = self.config.get('Following', {})
        if self.access_token and settings.get('active') != 'no':
            games_dir = StreamsContainer(
                root_item,
                title=settings.get('name') or 'Following',
                streams_url='%s/streams/followed',
                limit=settings.get('limit', 25),
                oauth_token=self.access_token)
            root_item.add_child(games_dir)

        # 'Games' directory
        settings = self.config.get('TopGames', {})
        if settings.get('active') != 'no':
            games_dir = GamesContainer(
                root_item,
                title=settings.get('name', 'Top Games'),
                limit=settings.get('limit', 10),
                children_limit=settings.get('children_limit', 25))
            root_item.add_child(games_dir)

        # 'Top Streams' directory
        settings = self.config.get('TopStreams', {})
        if settings.get('active') != 'no':
            games_dir = StreamsContainer(
                root_item,
                title=settings.get('name', 'Top Streams'),
                limit=settings.get('limit', 25))
            root_item.add_child(games_dir)


def json_loads(data):
    if isinstance(data, (list, tuple)):
        data = data[0]
    return json.loads(data)
