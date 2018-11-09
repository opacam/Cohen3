# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2014, Hartmut Goebel <h.goebel@goebel-consult.de>

"""
Test cases for L{upnp.core.sspd}
"""

import time

from twisted.test import proto_helpers
from twisted.trial import unittest

from coherence.upnp.core import ssdp

SSDP_PORT = 1900
SSDP_ADDR = '239.255.255.250'

USN_1 = 'uuid:e711a4bf::upnp:rootdevice'
SSDP_NOTIFY_1 = (
    b'NOTIFY * HTTP/1.1',
    b'Host:239.255.255.250:1900',
    b'NT:upnp:rootdevice',
    b'NTS:ssdp:alive',
    b'Location:http://10.10.222.94:2869/upnp?content=uuid:e711a4bf',
    b'USN: ' + USN_1.encode('ascii'),
    b'Cache-Control: max-age=1842',
    b'Server:Microsoft-Windows-NT/5.1 UPnP/1.0 UPnP-Device-Host/1.0',
)


class TestSSDP(unittest.TestCase):

    def setUp(self):
        self.proto = ssdp.SSDPServer(test=True)
        self.tr = proto_helpers.FakeDatagramTransport()
        self.proto.makeConnection(self.tr)

    def test_ssdp_notify(self):
        self.assertEqual(self.proto.known, {})
        data = b'\r\n'.join(SSDP_NOTIFY_1) + b'\r\n\r\n'
        self.proto.datagramReceived(data, ('10.20.30.40', 1234))
        self.assertTrue(self.proto.isKnown(USN_1))
        self.assertFalse(self.proto.isKnown(USN_1 * 2))
        service = self.proto.known[USN_1]
        del service['last-seen']
        self.assertEqual(service, {
            'HOST': '10.20.30.40',
            'ST': 'upnp:rootdevice',
            'LOCATION': 'http://10.10.222.94:2869/upnp?content=uuid:e711a4bf',
            'USN': 'uuid:e711a4bf::upnp:rootdevice',
            'CACHE-CONTROL': 'max-age=1842',
            'SERVER': 'Microsoft-Windows-NT/5.1 UPnP/1.0 UPnP-Device-Host/1.0',
            'MANIFESTATION': 'remote',
            'SILENT': False,
            'EXT': '',
        })

    def test_ssdp_notify_does_not_send_reply(self):
        data = b'\r\n'.join(SSDP_NOTIFY_1) + b'\r\n\r\n'
        self.proto.datagramReceived(data, ('127.0.0.1', 1234))
        self.assertEqual(self.tr.written, [])

    def test_ssdp_notify_updates_timestamp(self):
        data = b'\r\n'.join(SSDP_NOTIFY_1) + b'\r\n\r\n'
        self.proto.datagramReceived(data, ('10.20.30.40', 1234))
        service1 = self.proto.known[USN_1]
        last_seen1 = service1['last-seen']
        time.sleep(0.5)
        self.proto.datagramReceived(data, ('10.20.30.40', 1234))
        service2 = self.proto.known[USN_1]
        last_seen2 = service1['last-seen']
        self.assertIs(service1, service2)
        self.assertLess(last_seen1, last_seen2 + 0.5)

    def test_doNotify(self):
        data = b'\r\n'.join(SSDP_NOTIFY_1) + b'\r\n\r\n'
        self.proto.datagramReceived(data, ('10.20.30.40', 1234))
        self.assertEqual(self.tr.written, [])
        self.proto.doNotify('uuid:e711a4bf::upnp:rootdevice')
        expected = [
            b'\r\n',
            b'CACHE-CONTROL: max-age=1842\r\n',
            b'EXT: \r\n',
            b'HOST: 239.255.255.250:1900\r\n',
            b'LOCATION: http://10.10.222.94:2869/upnp?content=uuid:e711a4bf\r\n',
            b'NOTIFY * HTTP/1.1\r\n',
            b'NT: upnp:rootdevice\r\n',
            b'NTS: ssdp:alive\r\n',
            b'SERVER: Microsoft-Windows-NT/5.1 UPnP/1.0 UPnP-Device-Host/1.0\r\n',
            b'USN: uuid:e711a4bf::upnp:rootdevice\r\n']
        self.assertEqual(len(self.tr.written), 1)
        data, (host, port) = self.tr.written[0]
        self.assertEqual(
            (host, port),
            (SSDP_ADDR, SSDP_PORT))
        recieved = data.splitlines(True)
        self.assertEqual(
            sorted(recieved),
            sorted(expected))

    def test_doByebye(self):
        data = b'\r\n'.join(SSDP_NOTIFY_1) + b'\r\n\r\n'
        self.proto.datagramReceived(data, ('10.20.30.40', 1234))
        self.assertEqual(self.tr.written, [])
        self.proto.doByebye('uuid:e711a4bf::upnp:rootdevice')
        expected = [
            b'\r\n',
            b'CACHE-CONTROL: max-age=1842\r\n',
            b'EXT: \r\n',
            b'HOST: 239.255.255.250:1900\r\n',
            b'LOCATION: http://10.10.222.94:2869/upnp?content=uuid:e711a4bf\r\n',
            b'NOTIFY * HTTP/1.1\r\n',
            b'NT: upnp:rootdevice\r\n',
            b'NTS: ssdp:byebye\r\n',
            b'SERVER: Microsoft-Windows-NT/5.1 UPnP/1.0 UPnP-Device-Host/1.0\r\n',
            b'USN: uuid:e711a4bf::upnp:rootdevice\r\n']
        self.assertEqual(len(self.tr.written), 1)
        data, (host, port) = self.tr.written[0]
        self.assertEqual(
            (host, port),
            (SSDP_ADDR, SSDP_PORT))
        recieved = data.splitlines(True)
        self.assertEqual(
            sorted(recieved),
            sorted(expected))
