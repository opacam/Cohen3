# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2022 Tom Parker-Shemilt <palfrey@tevps.net>

"""
Test cases for L{upnp.backends.mediadb_storage}
"""

import os
import time
from twisted.python.filepath import FilePath
from twisted.trial import unittest

import coherence.log
from coherence.backends import mediadb_storage

coherence.log.init()


class TestMediaDBStorage(unittest.TestCase):

    def setUp(self):
        self.tmp_content = FilePath(self.mktemp())
        self.tmp_content.makedirs()        
        songs = os.path.join(os.path.dirname(__file__), "..", "content")
        self.storage = mediadb_storage.MediaStore(
            None,
            name='my media',
            mediadb=os.path.join(self.tmp_content.path, "media.db"),
            medialocation=songs
        )
        self.storage.info(songs)        

    def tearDown(self):
        pass

    def test_ContentLen(self):
        self.storage.upnp_init()
        for x in range(10):
            if self.storage.db.query(mediadb_storage.Track).count() == 1:
                break
            self.storage.info(f"waiting {x}")
            time.sleep(1)
        self.assertEqual(self.storage.db.query(mediadb_storage.Track).count(), 1)