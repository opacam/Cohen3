# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2022 Tom Parker-Shemilt <palfrey@tevps.net>

"""
Test cases for L{upnp.backends.mediadb_storage}
"""

from twisted.python.filepath import FilePath
from twisted.trial import unittest

import coherence.log
from coherence.backends import mediadb_storage

coherence.log.init()


class TestMediaDBStorage(unittest.TestCase):

    def setUp(self):
        self.tmp_content = FilePath(self.mktemp())
        self.tmp_content.makedirs()
        self.storage = mediadb_storage.MediaStore(None, name='my media',
                                          content=self.tmp_content.path,
                                          urlbase='http://fsstore-host/xyz',
                                          enable_inotify=False)

    def tearDown(self):
        self.tmp_content.remove()
        pass

    def test_ContentLen(self):
        self.assertEqual(len(self.storage.content), 1)
        self.assertEqual(len(self.storage.store), 1)
        self.assertEqual(self.storage.len(), 1)