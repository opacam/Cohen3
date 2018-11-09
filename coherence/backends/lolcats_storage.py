# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Benjamin Kampmann <ben.kampmann@googlemail.com>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
LolcatsStore
------------

This is a Media Backend that allows you to access the cool and cute pictures
from lolcats.com.
'''

import re

from coherence.backends.models.items import BackendImageItem
from coherence.backends.models.stores import BackendImageStore
from coherence.upnp.core.utils import parse_with_lxml
from coherence.upnp.core import DIDLLite


class LolCatsImage(BackendImageItem):
    '''
    LolCatsImage represents the description for our items which will be
    images, it inherits from
    :class:`~coherence.backends.models.items.BackendImageItem`.

    .. versionchanged:: 0.8.3
        Class has been renamed into camel-case format
        Refactored using the class
         :class:`~coherence.backends.models.items.BackendImageItem`
    '''
    mimetype = 'image/jpeg'

    def __init__(self, parent_id, item_id, urlbase, **kwargs):
        super(LolCatsImage, self).__init__(
            parent_id, item_id, urlbase, **kwargs)

        res = DIDLLite.Resource(
            self.location, f'http-get:*:{self.mimetype}:*')
        res.size = None  # FIXME: we should have a size here
        self.item.res.append(res)


class LolcatsStore(BackendImageStore):
    '''
    The media server for Lolcats.com.

    .. versionchanged:: 0.8.3
       Refactored using the class
       :class:`~coherence.backends.models.stores.BackendVideoStore`
    '''
    logCategory = 'lolcats'
    implements = ['MediaServer']

    upnp_protocols = [
        'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_TN;'
        'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
        'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_SM;'
        'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
        'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_MED;'
        'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
        'http-get:*:image/jpeg:DLNA.ORG_PN=JPEG_LRG;'
        'DLNA.ORG_OP=01;DLNA.ORG_FLAGS=00f00000000000000000000000000000',
        'http-get:*:image/jpeg:*']

    root_url = b'https://icanhas.cheezburger.com/lolcats/rss'
    root_find_items = './channel/item'
    root_id = 0

    item_cls = LolCatsImage
    item_type = 'http-get:*:image/jpeg:*'

    last_updated = ''

    def parse_data(self, root):
        pub_date = root.find('./channel/lastBuildDate').text
        if pub_date == self.last_updated:
            return
        self.last_updated = pub_date

        self.container.children = []
        self.items = {}

        return super(LolcatsStore, self).parse_data(root)

    def parse_item(self, item):
        title = item.find('title').text
        title = re.sub('(\u2018|\u2019)', '\'', title)

        try:
            img_html = item.find(
                '{http://purl.org/rss/1.0/modules/content/}encoded').text
            img_xml = parse_with_lxml(img_html)
        except Exception as e:
            self.error('Error on searching lol cat image: {}'.format(e))
            self.debug(f'\t - parser fails on:\n{img_html}\n')
            return None

        url = img_xml.find('img').get('src', None)
        if url is None:
            return None

        data = {
            'title': title,
            'url': url,
        }
        return data
