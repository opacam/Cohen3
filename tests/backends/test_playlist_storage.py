# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2018 Pol Canelles <canellestudi@gmail.com>

"""
Test cases for L{upnp.backends.playlist_storage}
"""
from twisted.trial import unittest

from coherence.backend import Container
from coherence.backends.playlist_storage import PlaylistStore, PlaylistItem

URL_M3U = 'https://gist.githubusercontent.com/random-robbie/' \
          'e56919b5603ecc87af885391e7331657/raw/' \
          '65661a4e6fa8c706cc8fe1cf7c553927e5cf62a7/BBC.m3u'


class TestPlaylistStorage(unittest.TestCase):

    def setUp(self):
        self.playlist = PlaylistStore(
            None,
            playlist_url=URL_M3U
            )

    def test_Content(self):
        def got_result(r):
            # print('got result: %r results found' % len(r))

            # Test content length
            self.assertEqual(len(r), 30)
            self.assertEqual(len(self.playlist.store), 31)
            self.assertEqual(self.playlist.len(), 31)

            # Test items
            self.assertIsInstance(self.playlist.store[0], Container)
            self.assertIsInstance(self.playlist.store[1000], PlaylistItem)

            # Test playlist item
            playlist_item = self.playlist.store[1000]
            print(playlist_item.__dict__)
            self.assertEqual(playlist_item.stream_url[0:4], 'http')
            self.assertEqual(playlist_item.get_url(), '/1000')
            self.assertEqual(playlist_item.get_id(), 1000)

            # Test audio/video/image item
            media_item = playlist_item.get_item()
            self.assertEqual(media_item.parentID, 0)
            self.assertEqual(media_item.id, 1000)
            self.assertIsInstance(media_item.title, str)
            self.assertGreater(len(media_item.title), 0)

        def got_error(r):
            print('got_error: %r' % r)
            self.assertEqual(len(r), 30)

        d = self.playlist.upnp_init()
        d.addCallback(got_result)
        d.addErrback(got_error)
        return d
