# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Benjamin Kampmann <ben.kampmann@googlemail.com>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
TEDStore
--------

Another simple rss based Media Server, this time for TED.com content.

Example to run from python script::

    from coherence.base import Coherence
    from twisted.internet import reactor

    coherence = Coherence(
        {'logmode': 'info',
         'plugin': {'backend': 'TEDStore',
                    'name': 'Cohen3 TEDStore'
                    },
         }
    )
    reactor.run()

Example to run from console::

    cohen3 --plugin=backend:TEDStore

.. note:: you need the cohen 3 package installed to run the plugin from
          a console.

.. versionchanged:: 0.8.3
'''

from coherence.backends.models.items import BackendVideoItem
from coherence.backends.models.stores import BackendVideoStore


class TedTalk(BackendVideoItem):
    '''
    The Backend Item.

    .. versionchanged:: 0.8.3
       Refactored using the class
       :class:`~coherence.backends.models.items.BackendVideoItem`
    '''
    mimetype = 'video/mp4'

    def __init__(self, parent_id, item_id, urlbase, **kwargs):
        super(TedTalk, self).__init__(
            parent_id, item_id, urlbase, **kwargs)

        self.item.res.size = kwargs.get('size', None)
        self.item.res.duration = kwargs.get('duration', None)


class TEDStore(BackendVideoStore):
    '''
    The Backend Store.

    .. versionchanged:: 0.8.3
       Refactored using the class
       :class:`~coherence.backends.models.stores.BackendVideoStore`
    '''
    logCategory = 'ted_store'
    implements = ['MediaServer']

    name = 'TEDTalks'

    upnp_protocols = [
        'http-get:*:video/quicktime:*',
        'http-get:*:video/mp4:*',
    ]

    root_url = b'http://feeds.feedburner.com/tedtalks_video?format=xml'
    root_find_items = './channel/item'
    root_id = 0

    item_cls = TedTalk
    item_type = 'http-get:*:video/mp4:*'

    last_updated = None

    def parse_data(self, root):
        pub_date = root.find('./channel/lastBuildDate').text
        if pub_date == self.last_updated:
            return

        self.last_updated = pub_date
        return super(TEDStore, self).parse_data(root)

    def parse_item(self, item):
        # FIXME: move these to generic constants somewhere
        mrss = './{http://search.yahoo.com/mrss/}'
        itunes = './{http://www.itunes.com/dtds/podcast-1.0.dtd}'

        url_item = mrss + 'content'
        duration = itunes + 'duration'
        summary = itunes + 'summary'

        data = {
            'name': item.find(
                './title').text.replace('TEDTalks : ', ''),
            'summary': item.find(summary).text,
            'duration': item.find(duration).text
        }

        try:
            media_entry = item.find(url_item)
            data['url'] = media_entry.get('url', None)
            data['size'] = media_entry.get('fileSize', None)
            data['mimetype'] = media_entry.get('type', None)
        except IndexError:
            return None
        return data
