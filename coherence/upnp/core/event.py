# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright (C) 2006 Fluendo, S.A. (www.fluendo.com).
# Copyright 2006,2007,2008,2009 Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
Events
======

This module contains several classes related to UPnP events.

:class:`EventServer`
--------------------

A class inherited from :class:`twisted.web.resource.Resource` representing an
event's server with dispatch events capabilities via EventsDispatcher.

:class:`EventSubscriptionServer`
--------------------------------

This class is the server part on the device side. It listens to subscribe
requests and registering the subscriber to send event messages to the device.

:class:`Event`
--------------

A dictionary representing an UPnP's Event.

:class:`EventProtocol`
----------------------

The Event's Protocol.

:class:`NotificationProtocol`
-----------------------------

The Notification protocol used to by :meth:`send_notification`.
'''

import time
from urllib.parse import urlsplit

from lxml import etree
from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol, ClientCreator, _InstanceFactory
from twisted.web import resource
from twisted.web.http import datetimeToString

from eventdispatcher import EventDispatcher

from coherence import log, SERVER_ID
from coherence.upnp.core.utils import (
    to_bytes, to_string, parse_http_response)

global hostname, web_server_port
hostname = None
web_server_port = None


class EventServer(EventDispatcher, resource.Resource, log.LogAble):
    '''
    .. versionchanged:: 0.9.0

        * Migrated from louie/dispatcher to EventDispatcher
        * The emitted events changed:

            - UPnP.Event.Server.message_received =>
              event_server_message_received
    '''
    logCategory = 'event_server'

    def __init__(self, control_point):
        log.LogAble.__init__(self)
        resource.Resource.__init__(self)
        EventDispatcher.__init__(self)
        self.register_event(
            'event_server_message_received'
        )
        self.coherence = control_point.coherence
        self.control_point = control_point
        self.coherence.add_web_resource('events',
                                        self)
        global hostname, web_server_port
        hostname = self.coherence.hostname
        web_server_port = self.coherence.web_server_port
        self.info('EventServer ready...')

    def render_NOTIFY(self, request):
        self.info(
            f'EventServer received notify from {request.client}, '
            f'code: {request.code:d}')
        data = request.content.getvalue()
        request.setResponseCode(200)

        command = {'method': request.method, 'path': request.path}
        headers = request.responseHeaders
        self.dispatch_event(
            'event_server_message_received',
            command, headers, data)

        if request.code != 200:
            self.info(f'data: {data}')
        else:
            self.debug(f'data: {data}')
            headers = request.getAllHeaders()
            sid = headers[b'sid']
            try:
                tree = etree.fromstring(data)
            except (SyntaxError, AttributeError):
                self.warning(
                    f'malformed event notification from {request.client}')
                self.debug(f'data: {data}')
                request.setResponseCode(400)
                return ''

            event = Event(sid, tree, raw=data)
            if len(event) != 0:
                self.control_point.propagate(event)
        return ''


class EventSubscriptionServer(EventDispatcher, resource.Resource, log.LogAble):
    '''
    This class is the server part on the device side. It listens
    to subscribe requests and registers the subscriber to send
    event messages to this device.
    If an unsubscribe request is received, the subscription is cancelled
    and no more event messages will be sent.

    we receive a subscription request like::

        {'callback':
            '<http://192.168.213.130:9083/BYvZMzfTSQkjHwzOThaP/ConnectionManager>',
         'host': '192.168.213.107:30020',
         'nt': 'upnp:event',
         'content-length': '0',
         'timeout': 'Second-300'}

    modify the callback value::

        callback = callback[1:len(callback)-1]

    and pack it into a subscriber dict::

        {'uuid:oAQbxiNlyYojCAdznJnC':
            {
            'callback':
            '<http://192.168.213.130:9083/BYvZMzfTSQkjHwzOThaP/ConnectionManager>',
            'created': 1162374189.257338,
            'timeout': 'Second-300',
            'sid': 'uuid:oAQbxiNlyYojCAdznJnC'}}

    .. versionchanged:: 0.9.0

        * Migrated from louie/dispatcher to EventDispatcher
        * The emitted events changed:

            - UPnP.Event.Client.message_received =>
              event_client_message_received
    '''  # noqa
    logCategory = 'event_subscription_server'

    def __init__(self, service):
        resource.Resource.__init__(self)
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)
        self.register_event(
            'event_client_message_received'
        )
        self.service = service
        self.subscribers = service.get_subscribers()
        try:
            self.backend_name = self.service.backend.name
        except AttributeError:
            self.backend_name = self.service.backend

    def render_SUBSCRIBE(self, request):
        self.info(
            f'EventSubscriptionServer {self.service.id} ({self.backend_name}) '
            f'received subscribe request from {request.client}, '
            f'code: {request.code:d}')
        data = request.content.getvalue()
        request.setResponseCode(200)

        command = {'method': request.method, 'path': request.path}
        headers = request.responseHeaders
        self.dispatch_event(
            'event_client_message_received',
            command, headers, data)

        if request.code != 200:
            self.debug(f'data: {data}')
        else:
            headers = request.getAllHeaders()
            if b'sid' in headers and headers[b'sid'] in self.subscribers:
                s = self.subscribers[headers[b'sid']]
                s['timeout'] = headers[b'timeout']
                s['created'] = time.time()
            elif b'callback' not in headers:
                request.setResponseCode(404)
                request.setHeader(b'SERVER', to_bytes(SERVER_ID))
                request.setHeader(b'CONTENT-LENGTH', to_bytes(0))
                return b''
            else:
                from .uuid import UUID
                sid = UUID()
                c = to_string(
                    headers[b'callback'][1:len(headers[b'callback']) - 1])
                s = {'sid': to_string(sid),
                     'callback':
                         c,
                     'seq': 0,
                     'timeout': to_string(headers[b'timeout']),
                     'created': time.time()}
                self.service.new_subscriber(s)
            request.setHeader(b'SID', to_bytes(s['sid']))

            # wrong example in the UPnP UUID spec?
            # request.setHeader(b'Subscription-ID', sid)

            request.setHeader(b'TIMEOUT', to_bytes(s['timeout']))
            request.setHeader(b'SERVER', to_bytes(SERVER_ID))
            request.setHeader(b'CONTENT-LENGTH', to_bytes(0))
        return b''

    def render_UNSUBSCRIBE(self, request):
        self.info(
            f'EventSubscriptionServer {self.service.id} ({self.backend_name}) '
            f'received unsubscribe request from {request.client}, '
            f'code: {request.code:d}')
        data = request.content.getvalue()
        request.setResponseCode(200)

        command = {'method': request.method, 'path': request.path}
        headers = request.responseHeaders
        self.dispatch_event(
            'event_client_message_received',
            command, headers, data)

        if request.code != 200:
            self.debug(f'data: {data}')
        else:
            headers = request.getAllHeaders()
            self.subscribers.pop(headers[b'sid'], None)
            # print self.subscribers
        return ''


class Event(dict, log.LogAble):
    logCategory = 'event'
    ns = 'urn:schemas-upnp-org:event-1-0'

    def __init__(self, sid, elements=None, raw=None):
        dict.__init__(self)
        log.LogAble.__init__(self)
        self._sid = sid
        self.raw = raw
        if elements is not None:
            self.from_elements(elements)

    def get_sid(self):
        return self._sid

    def from_elements(self, elements):
        for prop in elements.findall(f'{{{self.ns}}}property'):
            self._update_event(prop)
        if len(self) == 0:
            self.warning('event notification without property elements')
            self.debug(f'data: {self.raw}')
            for prop in elements.findall('property'):
                self._update_event(prop)

    def _update_event(self, prop):
        for var in prop.getchildren():
            tag = var.tag
            idx = tag.find('}') + 1
            value = var.text
            if value is None:
                value = ''
            self.update({tag[idx:]: value})


class EventProtocol(Protocol, log.LogAble):
    logCategory = 'event_protocol'

    def __init__(self, service, action):
        log.LogAble.__init__(self)
        self.service = service
        self.action = action

    def teardown(self):
        self.transport.loseConnection()
        self.service.event_connection = None

    def connectionMade(self):
        self.timeout_checker = reactor.callLater(30, self.teardown)

    def dataReceived(self, data):
        try:
            self.timeout_checker.cancel()
        except Exception:
            pass
        self.info('response received from the Service Events HTTP server ')
        # self.debug(data)
        cmd, headers = parse_http_response(data)
        self.debug(f'{cmd} {headers}')
        if int(cmd[1]) != 200:
            self.warning(f'response with error code {cmd[1]!r} '
                         f'received upon our {self.action!r} request')
            # XXX get around devices that return an
            # error on our event subscribe request
            self.service.process_event({})
        else:
            try:
                self.service.set_sid(headers['sid'])
                timeout = headers['timeout']
                self.debug(f'{headers["sid"]} {headers["timeout"]}')
                if timeout == 'infinite':
                    self.service.set_timeout(
                        time.time() + 4294967296)  # FIXME: that's lame
                elif timeout.startswith('Second-'):
                    timeout = int(timeout[len('Second-'):])
                    self.service.set_timeout(timeout)
            except Exception as e:
                self.warning(f'EventProtocol.dataReceived: {e}')
        self.teardown()

    def connectionLost(self, reason):
        try:
            self.timeout_checker.cancel()
        except Exception:
            pass
        self.debug(
            f'connection closed {reason} from the Service Events HTTP server')


def unsubscribe(service, action='unsubscribe'):
    return subscribe(service, action)


def subscribe(service, action='subscribe'):
    '''
    send a subscribe/renewal/unsubscribe request to a service
    return the device response
    '''

    logger = log.get_logger('event_protocol')
    logger.info(f'event.subscribe, action: {action}')

    service_base = service.get_base_url().decode('utf-8')
    _, host_port, path, _, _ = urlsplit(service_base)
    if host_port.find(':') != -1:
        host, port = tuple(host_port.split(':'))
        port = int(port)
    else:
        host = host_port
        port = 80

    def send_request(p, action):
        logger.info(f'event.subscribe.send_request {p}, '
                    f'action: {action} {service.get_event_sub_url()}')
        _, _, event_path, _, _ = urlsplit(service.get_event_sub_url())
        if action == 'subscribe':
            timeout = service.timeout
            if timeout == 0:
                timeout = 1800
            request = [f'SUBSCRIBE {to_string(event_path)} HTTP/1.1',
                       f'HOST: {host}:{port:d}',
                       f'TIMEOUT: Second-{timeout:d}',
                       ]
            service.event_connection = p
        else:
            request = [f'UNSUBSCRIBE {to_string(event_path)} HTTP/1.1',
                       f'HOST: {host}:{port:d}',
                       ]

        if service.get_sid():
            request.append(f'SID: {service.get_sid()}')
        else:
            # XXX use address and port set in the coherence instance
            # ip_address = p.transport.getHost().host
            global hostname, web_server_port
            # print hostname, web_server_port
            url = f'http://{hostname}:{web_server_port:d}/events'
            request.append(f'CALLBACK: <{url}>')
            request.append('NT: upnp:event')

        request.append(f'Date: {to_string(datetimeToString())}')
        request.append('Content-Length: 0')
        request.append('')
        request.append('')
        request = '\r\n'.join(request).encode('ascii')
        logger.debug(f'event.subscribe.send_request {request} {p}')
        try:
            p.transport.writeSomeData(request)
        except AttributeError:
            logger.info(f'transport for event {action} already gone')
        # logger.debug('event.subscribe.send_request ', request)
        # return d

    def got_error(failure, action):
        logger.info(f'error on {action} request with {service.get_base_url()}')
        logger.debug(failure)

    def teardown_connection(c, d):
        logger.info('event.subscribe.teardown_connection')
        del d
        del c

    def prepare_connection(service, action):
        logger.info(f'event.subscribe.prepare_connection action: '
                    f'{action} {service.event_connection}')
        if service.event_connection is None:
            c = ClientCreator(reactor, EventProtocol, service=service,
                              action=action)
            logger.info(f'event.subscribe.prepare_connection: {host} {port}')
            d = c.connectTCP(host, port)
            d.addCallback(send_request, action=action)
            d.addErrback(got_error, action)
            # reactor.callLater(3, teardown_connection, c, d)
        else:
            d = defer.Deferred()
            d.addCallback(send_request, action=action)
            d.callback(service.event_connection)
            # send_request(service.event_connection, action)
        return d

    ''' FIXME:
        we need to find a way to be sure that our unsubscribe calls get through
        on shutdown
        reactor.addSystemEventTrigger(
            'before', 'shutdown', prepare_connection, service, action)
    '''

    # logger.debug('event.subscribe finished')
    return prepare_connection(service, action)


class NotificationProtocol(Protocol, log.LogAble):
    logCategory = 'notification_protocol'

    def connectionMade(self):
        self.timeout_checker = reactor.callLater(
            30, lambda: self.transport.loseConnection())

    def dataReceived(self, data):
        try:
            self.timeout_checker.cancel()
        except Exception:
            pass
        if isinstance(data, bytes):
            d = str(data)
        else:
            d = data
        cmd, headers = parse_http_response(d)
        self.debug(f'notification response received {cmd} {headers}')
        try:
            if int(cmd[1]) != 200:
                self.warning(f'response with error code {cmd[1]!r}'
                             f' received upon our notification')
        except (IndexError, ValueError):
            self.debug(
                'response without error code received upon our notification')
        self.transport.loseConnection()

    def connectionLost(self, reason):
        try:
            self.timeout_checker.cancel()
        except Exception:
            pass
        self.debug(f'connection closed {reason}')


def send_notification(s, xml):
    '''
    send a notification a subscriber
    return its response
    '''
    logger = log.get_logger('notification_protocol')
    # logger.debug('\t-send_notification s is: {}'.format(s))
    # logger.debug('\t-send_notification xml is: {}'.format(xml))

    _, host_port, path, _, _ = urlsplit(s['callback'])
    # logger.debug('\t-send_notification host_port is: {}'.format(host_port))
    # logger.debug('\t-send_notification path is: {}'.format(path))
    path = to_string(path)
    host_port = to_string(host_port)
    if path == '':
        path = '/'
    if host_port.find(':') != -1:
        host, port = tuple(host_port.split(':'))
        port = int(port)
    else:
        host = host_port
        port = 80

    def send_request(p, port_item):
        request = [f'NOTIFY {path} HTTP/1.1',
                   f'HOST:  {host}:{port}',
                   f'SEQ:  {s["seq"]}',
                   'CONTENT-TYPE:  text/xml;charset="utf-8"',
                   f'SID:  {s["sid"]}',
                   'NTS:  upnp:propchange',
                   'NT:  upnp:event',
                   f'Content-Length: {len(xml)}',
                   ''
                   ]
        request = [to_bytes(x) for x in request]
        request.append(xml)
        request = b'\r\n'.join(request)
        logger.info(f'send_notification.send_request to '
                    f'{s["sid"]} {s["callback"]}')
        logger.info(f'request: {request}')
        s['seq'] += 1
        if s['seq'] > 0xffffffff:
            s['seq'] = 1
        p.transport.write(request)
        port_item.disconnect()

    def got_error(failure, port_item):
        port_item.disconnect()
        logger.info(
            f'error sending notification to {s["sid"]} {s["callback"]}')
        logger.debug(failure)

    d = defer.Deferred()
    f = _InstanceFactory(reactor, NotificationProtocol(), d)
    port_item = reactor.connectTCP(
        host, port, f, timeout=30, bindAddress=None)

    d.addCallback(send_request, port_item)
    d.addErrback(got_error, port_item)

    return d, port_item
