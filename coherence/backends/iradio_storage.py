# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2007, Frank Scholz <coherence@beebits.net>
# Copyright 2009-2010, Jean-Michel Sizun <jmDOTsizunATfreeDOTfr>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
A ShoutCast radio media server for the Cohen3 UPnP Framework.

.. warning:: You need your own api key!!!
'''
from urllib.parse import urlsplit

from twisted.internet import reactor
from twisted.python.failure import Failure
from twisted.web import server

from coherence.backend import Container, \
    LazyContainer, AbstractBackendStore
from coherence.backends.models.items import BackendAudioItem
from coherence.upnp.core import DIDLLite
from coherence.upnp.core import utils
from coherence.upnp.core.DIDLLite import Resource


# SHOUT CAST URLS
SC_KEY = ''
SC_API_URL = 'http://api.shoutcast.com/legacy/'
SC_TUNEIN_URL = 'http://yp.shoutcast.com'
SC_URL_TOP_500 = '{api_url}Top500?k={key}'
SC_URL_GENRE_LIST = '{api_url}genrelist?k={key}'
SC_URL_GENRE = '{api_url}genresearch?k={key}&genre={genre}'
SC_URL_SEARCH = '{api_url}stationsearch?k={k}&search={search}&limit={limit}'

genre_families = {
    # genre hierarchy created from:
    #     http://forums.winamp.com/showthread.php?s=&threadid=303231
    'Alternative':
        ['Adult Alternative', 'Britpop', 'Classic Alternative',
         'College', 'Dancepunk', 'Dream Pop', 'Emo', 'Goth',
         'Grunge', 'Indie Pop', 'Indie Rock', 'Industrial', 'Lo-Fi',
         'Modern Rock', 'New Wave', 'Noise Pop', 'Post-Punk',
         'Power Pop', 'Punk', 'Ska', 'Xtreme'],
    'Blues':
        ['Acoustic Blues', 'Chicago Blues', 'Contemporary Blues',
         'Country Blues', 'Delta Blues', 'Electric Blues',
         'Cajun/Zydeco'],
    'Classical':
        ['Baroque', 'Chamber', 'Choral', 'Classical Period',
         'Early Classical', 'Impressionist', 'Modern', 'Opera',
         'Piano', 'Romantic', 'Symphony'],
    'Country':
        ['Alt-Country', 'Americana', 'Bluegrass', 'Classic Country',
         'Contemporary Bluegrass', 'Contemporary Country', 'Honky Tonk',
         'Hot Country Hits', 'Western'],
    'Easy Listening': ['Exotica', 'Light Rock', 'Lounge', 'Orchestral Pop',
                       'Polka', 'Space Age Pop'],
    'Electronic':
        ['Acid House', 'Ambient', 'Big Beat', 'Breakbeat', 'Dance',
         'Demo', 'Disco', 'Downtempo', 'Drum and Bass', 'Electro',
         'Garage', 'Hard House', 'House', 'IDM', 'Remixes', 'Jungle',
         'Progressive', 'Techno', 'Trance', 'Tribal', 'Trip Hop'],
    'Folk':
        ['Alternative Folk', 'Contemporary Folk', 'Folk Rock',
         'New Acoustic', 'Traditional Folk', 'World Folk'],
    'Themes':
        ['Adult', 'Best Of', 'Chill', 'Experimental', 'Female',
         'Heartache', 'LGBT', 'Love/Romance', 'Party Mix', 'Patriotic',
         'Rainy Day Mix', 'Reality', 'Sexy', 'Shuffle', 'Travel Mix',
         'Tribute', 'Trippy', 'Work Mix'],
    'Rap':
        ['Alternative Rap', 'Dirty South', 'East Coast Rap', 'Freestyle',
         'Hip Hop', 'Gangsta Rap', 'Mixtapes', 'Old School', 'Turntablism',
         'Underground Hip-Hop', 'West Coast Rap'],
    'Inspirational':
        ['Christian', 'Christian Metal', 'Christian Rap',
         'Christian Rock', 'Classic Christian',
         'Contemporary Gospel', 'Gospel', 'Praise/Worship',
         'Sermons/Services', 'Southern Gospel',
         'Traditional Gospel'],
    'International':
        ['African', 'Afrikaans', 'Arabic', 'Asian', 'Brazilian',
         'Caribbean', 'Celtic', 'European', 'Filipino', 'Greek',
         'Hawaiian/Pacific', 'Hindi', 'Indian', 'Japanese',
         'Jewish', 'Klezmer', 'Mediterranean', 'Middle Eastern',
         'North American', 'Polskie', 'Polska', 'Soca',
         'South American', 'Tamil', 'Worldbeat', 'Zouk'],
    'Jazz':
        ['Acid Jazz', 'Avant Garde', 'Big Band', 'Bop', 'Classic Jazz',
         'Cool Jazz', 'Fusion', 'Hard Bop', 'Latin Jazz', 'Smooth Jazz',
         'Swing', 'Vocal Jazz', 'World Fusion'],
    'Latin':
        ['Bachata', 'Banda', 'Bossa Nova', 'Cumbia', 'Latin Dance',
         'Latin Pop', 'Latin Rap/Hip-Hop', 'Latin Rock', 'Mariachi',
         'Merengue', 'Ranchera', 'Reggaeton', 'Regional Mexican', 'Salsa',
         'Tango', 'Tejano', 'Tropicalia'],
    'Metal':
        ['Black Metal', 'Classic Metal', 'Extreme Metal', 'Grindcore',
         'Hair Metal', 'Heavy Metal', 'Metalcore', 'Power Metal',
         'Progressive Metal', 'Rap Metal'],
    'New Age':
        ['Environmental', 'Ethnic Fusion', 'Healing',
         'Meditation', 'Spiritual'],
    'Decades':
        ['30s', '40s', '50s', '60s', '70s', '80s', '90s'],
    'Pop':
        ['Adult Contemporary', 'Barbershop', 'Bubblegum Pop', 'Dance Pop',
         'Idols', 'Oldies', 'JPOP', 'Soft Rock', 'Teen Pop', 'Top 40',
         'World Pop'],
    'R&B/Urban':
        ['Classic R&B', 'Contemporary R&B', 'Doo Wop', 'Funk',
         'Motown', 'Neo-Soul', 'Quiet Storm', 'Soul',
         'Urban Contemporary', 'Reggae', 'Contemporary Reggae',
         'Dancehall', 'Dub', 'Pop-Reggae', 'Ragga', 'Rock Steady',
         'Reggae Roots'],
    'Rock':
        ['Adult Album Alternative', 'British Invasion', 'Classic Rock',
         'Garage Rock', 'Glam', 'Hard Rock', 'Jam Bands', 'Piano Rock',
         'Prog Rock', 'Psychedelic', 'Rock & Roll', 'Rockabilly',
         'Singer/Songwriter', 'Surf'],
    'Seasonal/Holiday':
        ['Anniversary', 'Birthday', 'Christmas', 'Halloween',
         'Hanukkah', 'Honeymoon', 'Valentine', 'Wedding',
         'Winter'],
    'Soundtracks':
        ['Anime', 'Bollywood', 'Kids', 'Original Score',
         'Showtunes', 'Video Game Music'],
    'Talk':
        ['Comedy', 'Community', 'Educational', 'Government', 'News',
         'Old Time Radio', 'Other Talk', 'Political', 'Public Radio',
         'Scanner', 'Spoken Word', 'Sports', 'Technology', 'Hardcore',
         'Eclectic', 'Instrumental'],
    'Misc': [],
}

synonym_genres = {
    # TODO: extend list with entries from 'Misc' which are clearly the same
    '24h': ['24h', '24hs'],
    '80s': ['80s', '80er'],
    'Acid Jazz': ['Acid', 'Acid Jazz'],
    'Adult': ['Adult', 'Adulto'],
    'Alternative': ['Alt', 'Alternativa', 'Alternative', 'Alternativo'],
    'Francais': ['Francais', 'French'],
    'Heavy Metal': ['Heavy Metal', 'Heavy', 'Metal'],
    'Hip Hop': ['Hip', 'Hop', 'Hippop', 'Hip Hop'],
    'Islam': ['Islam', 'Islamic'],
    'Italy': ['Italia', 'Italian', 'Italiana', 'Italo', 'Italy'],
    'Latina': ['Latin', 'Latina', 'Latino'],
}

useless_title_content = [
    # TODO: extend list with title expressions which are clearly useless
    ' - [SHOUTcast.com]'
]

useless_genres = [
    # TODO: extend list with entries from 'Misc' which are clearly useless
    'genres', 'go', 'here',
    'Her', 'Hbwa'
]


class PlaylistStreamProxy(utils.ReverseProxyUriResource):
    '''
    proxies audio streams published as M3U playlists
    (typically the case for shoutcast streams)
    '''
    logCategory = 'PlaylistStreamProxy'

    def __init__(self, uri):
        super(PlaylistStreamProxy, self).__init__(uri)

    def requestFinished(self, result):
        ''' self.connection is set in utils.ReverseProxyResource.render '''
        if self.connection is not None:
            self.connection.transport.loseConnection()

    def render(self, request):

        if self.uri is None:
            def got_playlist(result):
                if result is None:
                    # print(
                    #     'Error to retrieve playlist - nothing retrieved')
                    return self.requestFinished(result)
                result = result[0].split(b'\n')
                for line in result:
                    if line.startswith(b'File1='):
                        self.uri = line[6:]
                        break
                if self.uri is None:
                    # print(
                    #     'Error to retrieve playlist - '
                    #     'inconsistent playlist file')
                    return self.requestFinished(result)
                request.uri = self.uri
                return self.render(request)

            def got_error(error):
                print(f'Error to retrieve playlist - '
                      f'unable to retrieve data [ERROR: {error}]')
                return None

            playlist_url = self.uri
            d = utils.getPage(playlist_url, timeout=20)
            d.addCallbacks(got_playlist, got_error)
            return server.NOT_DONE_YET

        if request.clientproto == 'HTTP/1.1':
            self.connection = request.getHeader(b'connection')
            if self.connection:
                tokens = list(map(str.lower, self.connection.split(b' ')))
                if b'close' in tokens:
                    d = request.notifyFinish()
                    d.addBoth(self.requestFinished)
        else:
            d = request.notifyFinish()
            d.addBoth(self.requestFinished)
        return super(PlaylistStreamProxy, self).render(request)


class IRadioItem(BackendAudioItem):
    '''
    A backend audio item object which represents an Shoutcast  Radio.
    This class will hold all information regarding the radio stream.

    .. versionchanged:: 0.8.3
       Refactored using the class
       :class:`~coherence.backends.models.items.BackendAudioItem`
    '''
    is_proxy = False
    proxy_cls = PlaylistStreamProxy
    item_cls = DIDLLite.AudioBroadcast

    def __init__(self, parent_id, item_id, urlbase, **kwargs):
        super(IRadioItem, self).__init__(
            parent_id, item_id, urlbase, **kwargs)
        protocols = ('DLNA.ORG_PN=MP3',
                     'DLNA.ORG_CI=0',
                     'DLNA.ORG_OP=01',
                     'DLNA.ORG_FLAGS=01700000000000000000000000000000')
        res = Resource(
            self.url, f'http-get:*:{self.mimetype}:{";".join(protocols)}')
        res.size = 0  # None
        self.item.res.append(res)


class IRadioStore(AbstractBackendStore):
    logCategory = 'iradio'

    implements = ['MediaServer']

    genre_parent_items = {}  # will list the parent genre for every given genre

    def __init__(self, server, **kwargs):
        AbstractBackendStore.__init__(self, server, **kwargs)

        self.name = kwargs.get('name', 'iRadioStore')
        self.refresh = int(kwargs.get('refresh', 60)) * 60

        self.shoutcast_ws_url = self.config.get(
            'genrelist',
            SC_URL_GENRE_LIST.format(
                api_url=SC_API_URL, key=SC_KEY))

        # set root item
        root_item = Container(None, self.name)
        self.set_root_item(root_item)

        # set root-level genre family containers and populate the genre_
        # parent_items dict from the family hierarchy information
        for family, genres in list(genre_families.items()):
            family_item = self.append_genre(root_item, family)
            if family_item is not None:
                self.genre_parent_items[family] = root_item
                for genre in genres:
                    self.genre_parent_items[genre] = family_item

        # retrieve asynchronously the list of genres from
        # the souhtcast server genres not already attached to
        # a family will be attached to the 'Misc' family
        self.retrieveGenreList_attemptCount = 0
        deferredRoot = self.retrieveGenreList()

        # will be fired when the genre list is retrieved
        # self.init_completed()

    def append_genre(self, parent, genre):
        if genre in useless_genres:
            return None
        if genre in synonym_genres:
            same_genres = synonym_genres[genre]
        else:
            same_genres = [genre]
        title = genre
        family_item = LazyContainer(parent, title, genre, self.refresh,
                                    self.retrieveItemsForGenre,
                                    genres=same_genres, per_page=1)

        # TODO: Use a specific get_child items sorter
        # in order to get the sub-genre containers first
        family_item.sorting_method = 'name'

        parent.add_child(family_item, external_id=genre)
        return family_item

    def __repr__(self):
        return self.__class__.__name__

    def upnp_init(self):
        self.current_connection_id = None

        self.wmc_mapping = {'4': self.get_root_id()}

        if self.server:
            self.server.connection_manager_server.set_variable(
                0, 'SourceProtocolInfo',
                ['http-get:*:audio/mpeg:*',
                 'http-get:*:audio/x-scpls:*'],
                default=True)

    # populate a genre container (parent) with the sub-genre containers
    # and corresponding IRadio (list retrieved from the shoutcast server)
    def retrieveItemsForGenre(self, parent, genres, per_page=1, offset=0,
                              page=0):
        genre = genres[page]
        if page < len(genres) - 1:
            parent.childrenRetrievingNeeded = True
        url_genre = SC_URL_GENRE.format(
            api_url=SC_API_URL, key=SC_KEY,
            genre=genre.replace(' ', '%20'))

        if genre in genre_families:
            family_genres = genre_families[genre]
            for family_genre in family_genres:
                self.append_genre(parent, family_genre)

        def got_page(result):
            self.info(f'connection to ShoutCast service '
                      f'successful for genre: {genre}')
            result = utils.parse_xml(result, encoding='utf-8')
            tunein = result.find('tunein')
            if tunein is not None:
                tunein = tunein.get('base', '/sbin/tunein-station.pls')
            prot, host_port, path, _, _ = urlsplit(url_genre)
            tunein = SC_TUNEIN_URL + tunein

            stations = {}
            for stationResult in result.findall('station'):
                mimetype = stationResult.get('mt')
                station_id = stationResult.get('id')
                bitrate = stationResult.get('br')
                name = stationResult.get('name')
                # remove useless substrings (eg. '[Shoutcast.com]' ) from title
                for substring in useless_title_content:
                    name = name.replace(substring, '')
                lower_name = name.lower()
                url = f'{tunein}?id={stationResult.get("id")}'

                sameStation = stations.get(lower_name)
                if sameStation is None or bitrate > sameStation['bitrate']:
                    station = {'name': name,
                               'station_id': station_id,
                               'mimetype': mimetype,
                               'id': station_id,
                               'url': url,
                               'bitrate': bitrate}
                    stations[lower_name] = station

            for station in list(stations.values()):
                item = IRadioItem(
                    int(parent.get_id()), int(station.get('station_id')), '/',
                    title=station.get('name'),
                    url=utils.to_bytes(station.get('url')),
                    mimetype=station.get('mimetype'), is_proxy=True)
                parent.add_child(item, external_id=station_id)

            return True

        def got_error(error):
            self.warning(
                f'connection to ShoutCast service failed: {url_genre}')
            self.debug(f'{error.getTraceback()}')
            parent.childrenRetrievingNeeded = True  # we retry
            return Failure(f'Unable to retrieve stations for genre {genre}')

        d = utils.getPage(url_genre)
        d.addCallbacks(got_page, got_error)
        return d

    # retrieve the whole list of genres from the shoutcast server
    # to complete the population of the genre families classification
    # (genres not previously classified are put into the 'Misc' family)
    # ...and fire mediaserver init completion
    def retrieveGenreList(self):

        def got_page(result):
            if self.retrieveGenreList_attemptCount == 0:
                self.info('Connection to ShoutCast service '
                          'successful for genre listing')
            else:
                self.warning(
                    f'Connection to ShoutCast service successful for genre '
                    f'listing after {self.retrieveGenreList_attemptCount} '
                    f'attempts.')
            result = utils.parse_xml(result, encoding='utf-8')

            genres = {}
            main_synonym_genre = {}
            for main_genre, sub_genres in list(synonym_genres.items()):
                genres[main_genre] = sub_genres
                for genre in sub_genres:
                    main_synonym_genre[genre] = main_genre

            for genre in result.findall('genre'):
                name = genre.get('name')
                if name not in main_synonym_genre:
                    genres[name] = [name]
                    main_synonym_genre[name] = name

            for main_genre, sub_genres in list(genres.items()):
                if main_genre not in self.genre_parent_items:
                    genre_families['Misc'].append(main_genre)

            self.init_completed()

        def got_error(error):
            self.warning(f'connection to ShoutCast service for '
                         f'genre listing failed - Will retry! {error}')
            self.debug(f'{error.getTraceback()!r}')
            self.retrieveGenreList_attemptCount += 1
            reactor.callLater(5, self.retrieveGenreList)

        d = utils.getPage(self.shoutcast_ws_url)
        d.addCallback(got_page)
        d.addErrback(got_error)
        return d
