# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Frank Scholz <coherence@beebits.net>

"""
Test cases for the L{Coherence base class}
"""

from unittest import mock

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.trial import unittest

from coherence.base import Coherence


class TestCoherence(unittest.TestCase):

    def setUp(self):
        self.log_level = 'error'
        self.coherence = Coherence(
            {'unittest': 'yes', 'logmode': self.log_level},
        )

    def tearDown(self):
        def cleaner(r):
            self.coherence.clear()
            return r

        dl = self.coherence.shutdown()
        dl.addBoth(cleaner)
        return dl

    def test_singleton(self):
        d = Deferred()

        c1 = Coherence({'unittest': 'no', 'logmode': 'error'})
        c2 = Coherence({'unittest': 'no', 'logmode': 'error'})
        c3 = Coherence({'unittest': 'no', 'logmode': 'error'})

        def shutdown(r, instance):
            return instance.shutdown()

        d.addCallback(shutdown, c1)
        d.addCallback(shutdown, c2)
        d.addCallback(shutdown, c3)

        reactor.callLater(3, d.callback, None)

        return d

    def test_log_level(self):
        self.assertEqual(self.coherence.log_level, self.log_level.upper())

    def test_log_file(self):
        self.assertEqual(self.coherence.log_file, None)

        # now set a config file and test it
        fake_file = '/fake_dir/fake_file.log'
        self.coherence.config['logging'] = {'logfile': fake_file}
        self.assertEqual(self.coherence.log_file, fake_file)

    @mock.patch('coherence.base.get_ip_address')
    def test_setup_hostname(self, mock_get_ip):
        fake_ip = '192.168.1.24'
        mock_get_ip.return_value = fake_ip
        self.coherence.config['interface'] = fake_ip

        # we expect to have an real ip address assigned by the router
        self.assertNotEqual(self.coherence.hostname, '127.0.0.1')
        # proceed to set a fake ip address and test the result
        self.coherence.setup_hostname()
        self.assertEqual(self.coherence.hostname, fake_ip)
        mock_get_ip.assert_called_once_with(fake_ip)
