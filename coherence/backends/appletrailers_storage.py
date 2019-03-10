# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Benjamin Kampmann <ben.kampmann@googlemail.com>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
AppleTrailersStore
------------------

This is a Media Backend that allows you to access the Trailers from Apple.com.

Example to run from python script::

    from coherence.base import Coherence
    from twisted.internet import reactor

    coherence = Coherence(
        {'logmode': 'info',
         'plugin': {'backend': 'AppleTrailersStore',
                    'name': 'Cohen3 AppleTrailersStore',
                    'proxy': 'no',
                    },
         }
    )
    reactor.run()

Example to run from console::

    cohen3 --plugin=backend:AppleTrailersStore,proxy:no

.. note:: you need the cohen 3 package installed to run the plugin from
          a console.

.. versionchanged:: 0.8.3
   The Container class has been removed
'''

from coherence.upnp.core import DIDLLite
from coherence.upnp.core.utils import ReverseProxyUriResource
from coherence.backends.models.items import BackendVideoItem
from coherence.backends.models.stores import BackendVideoStore


class AppleTrailerProxy(ReverseProxyUriResource):
    '''
    Tha AppleTrailerProxy  ia a Resource that takes
    care to render the result gotten from our server
    :class:`~coherence.backends.appletrailers_storage.AppleTrailersStore`

    .. warning:: The ReverseProxyUriResource is not able to handle https
                 requests, so... better stick to non proxy until properly
                 handled.
    '''

    def __init__(self, uri):
        super(AppleTrailerProxy, self).__init__(uri)

    def render(self, request):
        request.requestHeaders.setRawHeaders(
            b'user-agent',
            [b'QuickTime/7.6.2 (qtver=7.6.2;os=Windows NT 5.1Service Pack 3)'])
        return super(AppleTrailerProxy, self).render(request)


class Trailer(BackendVideoItem):
    '''
    A backend item object which represents an Apple Trailer.
    This class will hold all information regarding the trailer.

    .. versionchanged:: 0.8.3
       Refactored using the class
       :class:`~coherence.backends.models.items.BackendVideoItem`
    '''
    is_proxy = False
    proxy_cls = AppleTrailerProxy
    mimetype = 'video/quicktime'

    def __init__(self, parent_id, item_id, urlbase, **kwargs):
        super(Trailer, self).__init__(
            parent_id, item_id, urlbase, **kwargs)

        self.runtime = kwargs.get('runtime', None)
        self.rating = kwargs.get('rating', None)
        self.post_date = kwargs.get('post_date', None)
        self.release_date = kwargs.get('release_date', None)
        self.studio = kwargs.get('studio', None)

        self.title = f'{self.name} [{self.release_date}]'


class AppleTrailersStore(BackendVideoStore):
    '''
    The media server for Apple Trailers.

    .. versionchanged:: 0.8.3
       Refactored using the class
       :class:`~coherence.backends.models.stores.BackendVideoStore`
    '''
    logCategory = 'apple_trailers'
    implements = ['MediaServer']

    upnp_protocols = [
        'http-get:*:video/quicktime:*',
        'http-get:*:video/mp4:*']

    root_url = b'http://www.apple.com/trailers/home/xml/current.xml'
    root_find_items = './movieinfo'
    root_id = 0

    item_cls = Trailer
    item_type = 'http-get:*:video/quicktime:*'

    def parse_item(self, item):
        info_keys = {
            'info/title': 'title',
            'info/director': 'director',
            'info/runtime': 'runtime',
            'info/rating': 'rating',
            'info/postdate': 'post_date',
            'info/releasedate': 'release_date',
            'info/studio': 'studio',
            'info/description': 'description',
            'poster/location': 'image',
            'preview/large': 'url',
            'cast/name': 'actors',
            'genre/name': 'genres',
        }
        has_multiple_values = ['cast/name', 'genre/name']

        data = {'id': item.get('id')}
        for search_key, key in info_keys.items():
            v = None
            if search_key not in has_multiple_values:
                v = item.find(f'./{search_key}').text
            else:
                lv = item.findall(f'./{search_key}')
                if isinstance(lv, list):
                    v = [e.text for e in lv]
            if v not in [None, '']:
                data[key] = v

        duration = None
        if 'runtime' in data:
            hours = 0
            minutes = 0
            seconds = 0
            duration = data['runtime']
            try:
                hours, minutes, seconds = duration.split(':')
            except ValueError:
                try:
                    minutes, seconds = duration.split(':')
                except ValueError:
                    seconds = duration
            duration = f'{int(hours):d}:{int(minutes):02d}:{int(seconds):02d}'
        data['duration'] = duration
        try:
            data['video_size'] = item.find(
                './preview/large').get('filesize', None)
        except Exception:
            data['video_size'] = None
        return data

    def add_item(self, data):
        # print('add_item: {}'.format(data))
        trailer = super(AppleTrailersStore, self).add_item(data)

        trailer.item.res.duration = data['duration']

        # Todo: maybe this should be refactored into BackendVideoStore?
        if self.server.coherence.config.get('transcoding', 'no') == 'yes':
            dlna_pn = 'DLNA.ORG_PN=AVC_TS_BL_CIF15_AAC'
            dlna_tags = DIDLLite.simple_dlna_tags[:]
            dlna_tags[2] = 'DLNA.ORG_CI=1'
            url = self.urlbase + str(trailer.id) + '?transcoded=mp4'
            new_res = DIDLLite.Resource(
                url,
                f'http-get:*:{"video/mp4"}:{";".join([dlna_pn] + dlna_tags)}')
            new_res.size = None
            new_res.duration = data['duration']
            trailer.item.res.append(new_res)

            dlna_pn = 'DLNA.ORG_PN=JPEG_TN'
            dlna_tags = DIDLLite.simple_dlna_tags[:]
            dlna_tags[2] = 'DLNA.ORG_CI=1'
            dlna_tags[3] = 'DLNA.ORG_FLAGS=00f00000000000000000000000000000'
            url = self.urlbase + str(
                trailer.id) + '?attachment=poster&transcoded=thumb&type=jpeg'
            new_res = DIDLLite.Resource(
                url,
                f'http-get:*:{"image/jpeg"}:{";".join([dlna_pn] + dlna_tags)}')
            new_res.size = None
            # new_res.resolution = '160x160'
            trailer.item.res.append(new_res)
            if not hasattr(trailer.item, 'attachments'):
                trailer.item.attachments = {}
            trailer.item.attachments['poster'] = (data['image'])  # noqa pylint: disable=E1101

        return trailer
