# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2005, Tim Potter <tpot@samba.org>
# Copyright 2006 John-Mark Gurney <gurney_j@resnet.uroegon.edu>
# Copyright (C) 2006 Fluendo, S.A. (www.fluendo.com).
# Copyright 2006,2007,2008,2009 Frank Scholz <coherence@beebits.net>
#
# Implementation of a SSDP server under Twisted Python.
#

import random
import socket
import time

from twisted.internet import reactor
from twisted.internet import task
from twisted.internet.protocol import DatagramProtocol
from twisted.web.http import datetimeToString
from twisted.test import proto_helpers

import coherence.extern.louie as louie
from coherence import log, SERVER_ID

SSDP_PORT = 1900
SSDP_ADDR = '239.255.255.250'


class SSDPServer(DatagramProtocol, log.LogAble):
    """A class implementing a SSDP server.  The notifyReceived and
    searchReceived methods are called when the appropriate type of
    datagram is received by the server."""
    logCategory = 'ssdp'

    def __init__(self, test=False, interface=''):
        # Create SSDP server
        log.LogAble.__init__(self)
        self.known = {}
        self._callbacks = {}
        self.test = test
        if not self.test:
            self.port = reactor.listenMulticast(
                SSDP_PORT, self,
                listenMultiple=True,
                interface=interface)

            self.port.joinGroup(SSDP_ADDR, interface=interface)

            self.resend_notify_loop = task.LoopingCall(self.resendNotify)
            self.resend_notify_loop.start(777.0, now=False)

            self.check_valid_loop = task.LoopingCall(self.check_valid)
            self.check_valid_loop.start(333.0, now=False)

        self.active_calls = []

    def shutdown(self):
        for call in reactor.getDelayedCalls():
            if call.func == self.send_it:
                call.cancel()
        if not self.test:
            if self.resend_notify_loop.running:
                self.resend_notify_loop.stop()
            if self.check_valid_loop.running:
                self.check_valid_loop.stop()
            '''Make sure we send out the byebye notifications.'''
            for st in self.known:
                if self.known[st]['MANIFESTATION'] == 'local':
                    self.doByebye(st)

    def datagramReceived(self, data, xxx_todo_changeme):
        """Handle a received multicast datagram."""
        self.debug('datagramReceived: {}'.format(data))
        (host, port) = xxx_todo_changeme
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        try:
            header, payload = data.split('\r\n\r\n')[:2]
        except ValueError as err:
            print(err)
            print('Arggg,', data)
            import pdb
            pdb.set_trace()

        lines = header.split('\r\n')
        cmd = lines[0].split(' ')
        lines = [x.replace(': ', ':', 1) for x in lines[1:]]
        lines = [x for x in lines if len(x) > 0]

        # TODO: Find  and fix where some of the header's keys are quoted.
        # This hack, allows to fix the quoted keys for the headers, introduced
        # at some point of the source code. I notice that the issue appears
        # when using FSStore plugin. But where?
        def fix_string(s, to_lower=True):
            for q in ["'", "\""]:
                while s.startswith(q):
                    s = s[1:]
            for q in ["'", "\""]:
                while s.endswith(q):
                    s = s[:-1]
            if to_lower:
                s = s.lower()
            return s
        headers = [x.split(':', 1) for x in lines]
        headers = \
            dict([(fix_string(x[0]),
                   fix_string(x[1], to_lower=False)) for x in headers])

        self.msg('SSDP command {} {} - from {}:{}'.format(
            cmd[0], cmd[1], host, port))
        self.debug('with headers: {}'.format(headers))
        if cmd[0] == 'M-SEARCH' and cmd[1] == '*':
            # SSDP discovery
            self.discoveryRequest(headers, (host, port))
        elif cmd[0] == 'NOTIFY' and cmd[1] == '*':
            # SSDP presence
            self.notifyReceived(headers, (host, port))
        else:
            self.warning('Unknown SSDP command {} {}'.format(cmd[0], cmd[1]))

        # make raw data available
        # send out the signal after we had a chance to register the device
        louie.send('UPnP.SSDP.datagram_received', None, data, host, port)

    def register(self, manifestation, usn, st, location,
                 server=SERVER_ID,
                 cache_control='max-age=1800',
                 silent=False,
                 host=None):
        """Register a service or device that this SSDP server will
        respond to."""

        self.info('Registering {} ({}) -> {}'.format(
            st, location, manifestation))
        self.debug('\t-searching usn: {}'.format(usn))

        try:
            self.known[usn] = {}
            self.known[usn]['USN'] = usn
            self.known[usn]['LOCATION'] = location
            self.known[usn]['ST'] = st
            self.known[usn]['EXT'] = ''
            self.known[usn]['SERVER'] = server
            self.known[usn]['CACHE-CONTROL'] = cache_control

            self.known[usn]['MANIFESTATION'] = manifestation
            self.known[usn]['SILENT'] = silent
            self.known[usn]['HOST'] = host
            self.known[usn]['last-seen'] = time.time()

            self.msg(self.known[usn])
            self.debug('\t-self.known: {}'.format(self.known))

            if manifestation == 'local':
                self.doNotify(usn)

            if st == 'upnp:rootdevice':
                louie.send(
                    'Coherence.UPnP.SSDP.new_device',
                    None, device_type=st, infos=self.known[usn])
                # self.callback("new_device", st, self.known[usn])
            # print('\t - ok all')
        except Exception as err:
            self.error('\t -> Error on registering service: '
                       '{} [error: "{}"]'.format(manifestation, err))

    def unRegister(self, usn):
        self.msg("Un-registering {}".format(usn))
        st = self.known[usn]['ST']
        if st == 'upnp:rootdevice':
            louie.send(
                'Coherence.UPnP.SSDP.removed_device',
                None, device_type=st, infos=self.known[usn])
            # self.callback("removed_device", st, self.known[usn])

        del self.known[usn]

    def isKnown(self, usn):
        return usn in self.known

    def notifyReceived(self, headers, xxx_todo_changeme1):
        """Process a presence announcement.  We just remember the
        details of the SSDP service announced."""
        (host, port) = xxx_todo_changeme1
        self.info('Notification from ({},{}) for {}'.format(
            host, port, headers['nt']))
        self.debug('Notification headers: {}'.format(headers))

        if headers['nts'] == 'ssdp:alive':
            try:
                self.known[headers['usn']]['last-seen'] = time.time()
                self.debug('updating last-seen for {}'.format(headers['usn']))
            except KeyError:
                self.register('remote', headers['usn'], headers['nt'],
                              headers['location'],
                              headers['server'], headers['cache-control'],
                              host=host)
        elif headers['nts'] == 'ssdp:byebye':
            if self.isKnown(headers['usn']):
                self.unRegister(headers['usn'])
        else:
            self.warning('Unknown subtype {} for notification type {}'.format(
                headers['nts'], headers['nt']))
        louie.send('Coherence.UPnP.Log', None, 'SSDP', host,
                   'Notify %s for %s' % (headers['nts'], headers['usn']))

    def send_it(self, response, destination, delay, usn):
        self.info('send discovery response delayed by '
                  '{} for {} to {}'.format(delay, usn, destination))
        r = response if isinstance(response, bytes) else \
            response.encode('ascii')
        d = destination if isinstance(destination, bytes) else \
            destination.encode('ascii')
        try:
            self.transport.write(r, d)
        except (AttributeError, socket.error) as msg:
            self.info('failure sending out byebye notification: '
                      '{}'.format(msg))

    def discoveryRequest(self, headers, xxx_todo_changeme2):
        """Process a discovery request.  The response must be sent to
        the address specified by (host, port)."""
        (host, port) = xxx_todo_changeme2
        self.info('Discovery request from ({},{}) for {}'.format(
            host, port, headers['st']))
        self.info('Discovery request for {}'.format(headers['st']))

        louie.send(
            'Coherence.UPnP.Log',
            None, 'SSDP', host, 'M-Search for %s' % headers['st'])

        # Do we know about this service?
        for i in list(self.known.values()):
            if i['MANIFESTATION'] == 'remote':
                continue
            if (headers['st'] == 'ssdp:all' and
                    i['SILENT'] is True):
                continue
            if (i['ST'] == headers['st'] or
                    headers['st'] == 'ssdp:all'):
                response = []
                response.append(b'HTTP/1.1 200 OK')

                for k, v in list(i.items()):
                    if k == 'USN':
                        usn = v
                    if k not in ('MANIFESTATION', 'SILENT', 'HOST'):
                        response.append(b'%r: %r' % (k, v))
                response.append(b'DATE: %r' % datetimeToString())

                response.extend((b'', b''))
                delay = random.randint(0, int(headers['mx']))

                reactor.callLater(
                    delay, self.send_it, b'\r\n'.join(response),
                    (host, port), delay, usn)

    def doNotify(self, usn):
        """Do notification"""

        if self.known[usn]['SILENT'] is True:
            return
        self.info('Sending alive notification for {}'.format(usn))
        # self.info('\t - self.known[usn]: {}'.format(self.known[usn]))

        resp = ['NOTIFY * HTTP/1.1',
                'HOST: %s:%d' % (SSDP_ADDR, SSDP_PORT),
                'NTS: ssdp:alive',
                ]
        stcpy = dict(iter(self.known[usn].items()))
        stcpy['NT'] = stcpy['ST']
        del stcpy['ST']
        del stcpy['MANIFESTATION']
        del stcpy['SILENT']
        del stcpy['HOST']
        del stcpy['last-seen']

        resp.extend([
            '%r: %r' % (k, v) for k, v in stcpy.items()])
        resp.extend(('', ''))
        r = '\r\n'.join(resp).encode('ascii')
        self.debug('doNotify content {}  [transport is: {}]'.format(
            r, self.transport))
        if not self.transport:
            try:
                self.warning('transport not initialized...'
                             'trying to initialize a FakeDatagramTransport')
                self.transport = proto_helpers.FakeDatagramTransport()
            except Exception as er:
                self.error('Cannot initialize transport: {}'.format(er))
        try:
            self.transport.write(r, (SSDP_ADDR, SSDP_PORT))
        except (AttributeError, socket.error) as msg:
            self.info('failure sending out alive notification: {}'.format(msg))

    def doByebye(self, usn):
        """Do byebye"""

        self.info('Sending byebye notification for %s', usn)

        resp = ['NOTIFY * HTTP/1.1',
                'HOST: %r:%r' % (SSDP_ADDR, SSDP_PORT),
                'NTS: ssdp:byebye',
                ]
        try:
            stcpy = dict(iter(self.known[usn].items()))
            stcpy['NT'] = stcpy['ST']
            del stcpy['ST']
            del stcpy['MANIFESTATION']
            del stcpy['SILENT']
            del stcpy['HOST']
            del stcpy['last-seen']
            resp.extend([
                '%r: %r' % (k, v) for k, v in stcpy.items()])
            resp.extend(('', ''))
            r = '\r\n'.join(resp).encode('ascii')
            self.debug('doByebye content %s', resp)
            if not self.transport:
                self.warning('transport not initialized...'
                             'trying to initialize a FakeDatagramTransport')
                self.transport = proto_helpers.FakeDatagramTransport()
                self.makeConnection(self.transport)
            try:
                self.transport.write(r, (SSDP_ADDR, SSDP_PORT))
            except (AttributeError, socket.error) as msg:
                self.info(
                    "failure sending out byebye notification: %r", msg)
        except KeyError as msg:
            self.debug("error building byebye notification: %r", msg)

    def resendNotify(self):
        for usn in self.known:
            if self.known[usn]['MANIFESTATION'] == 'local':
                self.doNotify(usn)

    def check_valid(self):
        """ check if the discovered devices are still ok, or
            if we haven't received a new discovery response
        """
        self.debug("Checking devices/services are still valid")
        removable = []
        for usn in self.known:
            if self.known[usn]['MANIFESTATION'] != 'local':
                _, expiry = self.known[usn]['CACHE-CONTROL'].split('=')
                expiry = int(expiry)
                now = time.time()
                last_seen = self.known[usn]['last-seen']
                self.debug('Checking if {} is still valid - last seen '
                           '{} (+{}), now {}'.format(
                               self.known[usn]['USN'], last_seen, expiry, now))
                if last_seen + expiry + 30 < now:
                    self.debug('Expiring: {}'.format(self.known[usn]))
                    if self.known[usn]['ST'] == 'upnp:rootdevice':
                        louie.send(
                            'Coherence.UPnP.SSDP.removed_device',
                            None, device_type=self.known[usn]['ST'],
                            infos=self.known[usn])
                    removable.append(usn)
        while len(removable) > 0:
            usn = removable.pop(0)
            del self.known[usn]

    def subscribe(self, name, callback):
        self._callbacks.setdefault(name, []).append(callback)

    def unsubscribe(self, name, callback):
        callbacks = self._callbacks.get(name, [])
        if callback in callbacks:
            callbacks.remove(callback)
        self._callbacks[name] = callbacks

    def callback(self, name, *args):
        for callback in self._callbacks.get(name, []):
            callback(*args)
