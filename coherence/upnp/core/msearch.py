# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php
#
# Copyright (C) 2006 Fluendo, S.A. (www.fluendo.com).
# Copyright 2006, Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
:class:`MSearch`
----------------

A class representing a protocol for datagram-oriented transport, e.g. UDP.
'''

import socket
import time

from twisted.internet import reactor
from twisted.internet import task
from twisted.internet.protocol import DatagramProtocol

from eventdispatcher import EventDispatcher

from coherence.upnp.core import utils
from coherence import log

SSDP_PORT = 1900
SSDP_ADDR = '239.255.255.250'


class MSearch(EventDispatcher, DatagramProtocol, log.LogAble):
    '''
    .. versionchanged:: 0.9.0

        * Migrated from louie/dispatcher to EventDispatcher
        * The emitted events changed:

            - UPnP.SSDP.datagram_received => datagram_received
    '''
    logCategory = 'msearch'

    def __init__(self, ssdp_server, test=False):
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)
        self.register_event(
            'datagram_received',
        )
        self.ssdp_server = ssdp_server
        if not test:
            self.port = reactor.listenUDP(0, self)

            self.double_discover_loop = task.LoopingCall(self.double_discover)
            self.double_discover_loop.start(120.0)

    def datagramReceived(self, data, xxx_todo_changeme):
        (host, port) = xxx_todo_changeme
        if isinstance(data, bytes):
            data = data.decode('utf-8')

        cmd, headers = utils.parse_http_response(data)
        self.info(f'datagramReceived from {host}:{port:d}, '
                  f'protocol {cmd[0]} code {cmd[1]}')
        if cmd[0].startswith('HTTP/1.') and cmd[1] == '200':
            self.msg(f'for {headers["usn"]}')
            if not self.ssdp_server.isKnown(headers['usn']):
                self.info(f'register as remote {headers["usn"]}, '
                          f'{headers["st"]}, {headers["location"]}')
                self.ssdp_server.register(
                    'remote',
                    headers['usn'], headers['st'],
                    headers['location'],
                    headers['server'],
                    headers['cache-control'],
                    host=host)
            else:
                self.ssdp_server.known[headers['usn']][
                    'last-seen'] = time.time()
                self.debug(f'updating last-seen for {headers["usn"]}')

        # make raw data available
        # send out the signal after we had a chance to register the device
        self.dispatch_event('datagram_received', data, host, port)

    def double_discover(self):
        '''Because it's worth it (with UDP's reliability)'''
        self.info('send out discovery for ssdp:all')
        self.discover()
        self.discover()

    def discover(self):
        req = ['M-SEARCH * HTTP/1.1',
               f'HOST: {SSDP_ADDR}:{SSDP_PORT:d}',
               'MAN: "ssdp:discover"',
               'MX: 5',
               'ST: ssdp:all',
               '', '']
        req = '\r\n'.join(req).encode('ascii')

        try:
            self.transport.write(req, (SSDP_ADDR, SSDP_PORT))
        except socket.error as msg:
            self.info(f'failure sending out the discovery message: {msg}')
