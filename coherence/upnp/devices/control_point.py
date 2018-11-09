# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2006-2010, Frank Scholz <dev@coherence-project.org>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
Control Point
=============

:class:`DeviceQuery`
--------------------

A convenient class that allow us to create request queries to control point.

:class:`ControlPoint`
---------------------

Takes care of managing the different devices detected by our instance
of class :class:`~coherence.base.Coherence`.

:class:`XMLRPC`
---------------

A resource that implements XML-RPC.

.. note::
    XML-RPC is a remote procedure call (RPC) protocol which uses XML to encode
    its calls and HTTP as a transport mechanism. "XML-RPC" also refers
    generically to the use of XML for remote procedure call, independently
    of the specific protocol.

.. seealso::
    XML-RPC information extracted from: https://en.wikipedia.org/wiki/XML-RPC
'''

import traceback

from twisted.internet import reactor
from twisted.web import xmlrpc, client

from eventdispatcher import EventDispatcher, Property, ListProperty

from coherence import log
from coherence.upnp.core import service
from coherence.upnp.core.event import EventServer
from coherence.upnp.devices.internet_gateway_device_client import \
    InternetGatewayDeviceClient
from coherence.upnp.devices.media_renderer_client import MediaRendererClient
from coherence.upnp.devices.media_server_client import MediaServerClient


class DeviceQuery(EventDispatcher):
    '''
    .. versionchanged:: 0.9.0

       * Introduced inheritance from EventDispatcher
       * Changed class variable :attr:`fired` to benefit from the
         EventDispatcher's properties
    '''
    fired = Property(False)

    def __init__(self, type, pattern, callback, timeout=0, oneshot=True):
        EventDispatcher.__init__(self)
        self.type = type
        self.pattern = pattern
        self.callback = callback
        self.timeout = timeout
        self.oneshot = oneshot
        if self.type == 'uuid' and self.pattern.startswith('uuid:'):
            self.pattern = self.pattern[5:]
        if isinstance(self.callback, str):
            # print(f'DeviceQuery: register event {self.callback}')
            self.register_event(self.callback)

    def fire(self, device):
        if callable(self.callback):
            self.callback(device)
        elif isinstance(self.callback, str):
            self.dispatch_event(self.callback, device=device)
        self.fired = True

    def check(self, device):
        if self.fired and self.oneshot:
            return
        if (self.type == 'host' and
                device.host == self.pattern):
            self.fire(device)
        elif (self.type == 'friendly_name' and
              device.friendly_name == self.pattern):
            self.fire(device)
        elif (self.type == 'uuid' and
              device.get_uuid() == self.pattern):
            self.fire(device)


class ControlPoint(EventDispatcher, log.LogAble):
    '''
    .. versionchanged:: 0.9.0

        * Introduced inheritance from EventDispatcher, emitted events changed:

            - Coherence.UPnP.ControlPoint.{client.device_type}.detected =>
              control_point_client_detected'
            - Coherence.UPnP.ControlPoint.{client.device_type}.removed =>
              control_point_client_removed

        * Changed class variable :attr:`queries` to benefit from the
          EventDispatcher's properties
    .. warning::
        Be aware that some events are removed, with the new dispatcher we
        remove the detection for specific device type in flavour of a global
        detection.
    '''
    logCategory = 'controlpoint'

    queries = ListProperty([])

    def __init__(self, coherence, auto_client=None):
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)
        self.register_event(
            'control_point_client_detected',
            'control_point_client_removed',
        )

        if not auto_client:
            auto_client = ['MediaServer', 'MediaRenderer']
        self.coherence = coherence
        self.auto_client = auto_client
        self.coherence.bind(
            coherence_device_detection_completed=self.check_device,
            coherence_device_removed=self.remove_client)

        self.info('Coherence UPnP ControlPoint starting...')
        self.event_server = EventServer(self)
        self.coherence.add_web_resource('RPC2', XMLRPC(self))

        for device in self.get_devices():
            self.info(f'ControlPoint [check device]: {device}')
            self.check_device(device)

    def shutdown(self):
        for device in self.get_devices():
            self.coherence.unbind(
                coherence_device_detection_completed=self.check_device,
                coherence_device_removed=self.remove_client
            )
            if device.client is not None:
                device.client.unbind(
                    detection_completed=self.completed)

    def auto_client_append(self, device_type):
        if device_type in self.auto_client:
            return
        self.auto_client.append(device_type)
        for device in self.get_devices():
            self.check_device(device)

    def browse(self, device):
        self.info(f'ControlPoint.browse: {device}')
        device = self.coherence.get_device_with_usn(device.get_usn())
        if not device:
            return
        self.check_device(device)

    def process_queries(self, device):
        for query in self.queries:
            query.check(device)

    def add_query(self, query):
        for device in self.get_devices():
            query.check(device)
        if not query.fired and query.timeout == 0:
            query.callback(None)
        else:
            self.queries.append(query)

    @staticmethod
    def check_louie(receiver, signal, method='connect'):
        '''
        Check if the connect or disconnect method's arguments are valid in
        order to automatically convert to EventDispatcher's bind method.
        The old valid signals are:

            - Coherence.UPnP.ControlPoint.MediaServer.detected
            - Coherence.UPnP.ControlPoint.MediaServer.removed
            - Coherence.UPnP.ControlPoint.MediaRenderer.detected
            - Coherence.UPnP.ControlPoint.MediaRenderer.removed
            - Coherence.UPnP.ControlPoint.InternetGatewayDevice.detected
            - Coherence.UPnP.ControlPoint.InternetGatewayDevice.removed

        .. versionadded:: 0.9.0
        '''
        if not callable(receiver):
            raise Exception('The receiver should be callable in order to use'
                            ' the method {method}')
        if not signal:
            raise Exception(
                f'We need a signal in order to use method {method}')
        if not signal.startswith('Coherence.UPnP.ControlPoint.'):
            raise Exception('We need a signal an old signal starting with: '
                            '"Coherence.UPnP.ControlPoint."')

    def connect(self, receiver, signal=None, sender=None, weak=True):
        '''
        Wrapper method around the deprecated method louie.connect. It will
        check if the passed signal is supported by executing the method
        :meth:`check_louie`.

        .. warning:: This will probably be removed at some point, if you use
                     the connect method you should consider to migrate to the
                     new event system EventDispatcher.

        .. versionchanged:: 0.9.0
            Added EventDispatcher's compatibility for some basic signals
        '''
        self.check_louie(receiver, signal, 'connect')
        if signal.endswith('.detected'):
            self.coherence.bind(
                coherence_device_detection_completed=receiver)
        elif signal.endswith('.removed'):
            self.bind(
                control_point_client_removed=receiver)
        else:
            raise Exception(
                f'Unknown signal {signal}, we cannot bind that signal.')

    def disconnect(self, receiver, signal=None, sender=None, weak=True):
        '''
        Wrapper method around the deprecated method louie.disconnect. It will
        check if the passed signal is supported by executing the method
        :meth:`check_louie`.

        .. warning:: This will probably be removed at some point, if you use
                     the disconnect method you should migrate to the new event
                     system EventDispatcher.

        .. versionchanged:: 0.9.0
            Added EventDispatcher's compatibility for some basic signals
        '''
        self.check_louie(receiver, signal, 'disconnect')
        if signal.endswith('.detected'):
            self.coherence.unbind(
                coherence_device_detection_completed=receiver)
        elif signal.endswith('.removed'):
            self.unbind(
                control_point_client_removed=receiver)
        else:
            raise Exception(
                f'Unknown signal {signal}, we cannot unbind that signal.')

    def get_devices(self):
        return self.coherence.get_devices()

    def get_device_with_id(self, id):
        return self.coherence.get_device_with_id(id)

    def get_device_by_host(self, host):
        return self.coherence.get_device_by_host(host)

    def check_device(self, device):
        if device.client is None:
            self.info(f'found device {device.get_friendly_name()} of type '
                      f'{device.get_device_type()} - {device.client}')
            short_type = device.get_friendly_device_type()
            if short_type in self.auto_client and short_type is not None:
                self.info(
                    f'identified {short_type} {device.get_friendly_name()}')

                if short_type == 'MediaServer':
                    client = MediaServerClient(device)
                if short_type == 'MediaRenderer':
                    client = MediaRendererClient(device)
                if short_type == 'InternetGatewayDevice':
                    client = InternetGatewayDeviceClient(device)
                client.bind(detection_completed=self.completed)
                client.coherence = self.coherence

                device.set_client(client)

        if device.client.detection_completed:
            self.completed(device.client)
        self.process_queries(device)

    def completed(self, client, *args):
        self.info(f'sending signal Coherence.UPnP.ControlPoint.'
                  f'{client.device_type}.detected {client.device.udn}')
        self.dispatch_event(
            'control_point_client_detected',
            client=client, udn=client.device.udn)

    def remove_client(self, udn, client):
        self.dispatch_event(
            'control_point_client_removed', udn=udn)
        self.info(f'removed {client.device_type} '
                  f'{client.device.get_friendly_name()}')
        client.remove()

    def propagate(self, event):
        self.info(f'propagate: {event}')
        if event.get_sid() in service.subscribers:
            try:
                service.subscribers[event.get_sid()].process_event(event)
            except Exception as msg:
                self.debug(msg)
                self.debug(traceback.format_exc())
                pass

    def put_resource(self, url, path):
        def got_result(result):
            print(result)

        def got_error(result):
            print('error', result)

        try:
            f = open(path)
            data = f.read()
            f.close()
            headers = {
                b'Content-Type': b'application/octet-stream',
                b'Content-Length': bytes(str(len(data)), encoding='utf-8')
            }
            df = client.getPage(
                url, method=b'POST',
                headers=headers, postdata=data)
            df.addCallback(got_result)
            df.addErrback(got_error)
            return df
        except IOError:
            pass


class XMLRPC(xmlrpc.XMLRPC):

    def __init__(self, control_point):
        xmlrpc.XMLRPC.__init__(self)
        self.control_point = control_point
        self.allowNone = True

    def xmlrpc_list_devices(self):
        print('list_devices')
        r = []
        for device in self.control_point.get_devices():
            # print(device.get_friendly_name(), device.get_service_type(),
            #       device.get_location(), device.get_id())
            d = {'friendly_name': device.get_friendly_name(),
                 'device_type': device.get_device_type(),
                 'location': str(device.get_location()),
                 'id': str(device.get_id())}
            r.append(d)
        return r

    def xmlrpc_mute_device(self, device_id):
        print('mute')
        device = self.control_point.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            client.rendering_control.set_mute(desired_mute=1)
            return 'Ok'
        return 'Error'

    def xmlrpc_unmute_device(self, device_id):
        print('unmute', device_id)
        device = self.control_point.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            client.rendering_control.set_mute(desired_mute=0)
            return 'Ok'
        return 'Error'

    def xmlrpc_set_volume(self, device_id, volume):
        print('set volume')
        device = self.control_point.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            client.rendering_control.set_volume(desired_volume=volume)
            return 'Ok'
        return 'Error'

    def xmlrpc_play(self, device_id):
        print('play')
        device = self.control_point.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            client.av_transport.play()
            return 'Ok'
        return 'Error'

    def xmlrpc_pause(self, device_id):
        print('pause')
        device = self.control_point.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            client.av_transport.pause()
            return 'Ok'
        return 'Error'

    def xmlrpc_stop(self, device_id):
        print('stop')
        device = self.control_point.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            client.av_transport.stop()
            return 'Ok'
        return 'Error'

    def xmlrpc_next(self, device_id):
        print('next')
        device = self.control_point.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            next(client.av_transport)
            return 'Ok'
        return 'Error'

    def xmlrpc_previous(self, device_id):
        print('previous')
        device = self.control_point.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            client.av_transport.previous()
            return 'Ok'
        return 'Error'

    def xmlrpc_set_av_transport_uri(self, device_id, uri):
        print('set_av_transport_uri')
        device = self.control_point.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            client.av_transport.set_av_transport_uri(current_uri=uri)
            return 'Ok'
        return 'Error'

    def xmlrpc_create_object(self, device_id, container_id, arguments):
        print('create_object', arguments)
        device = self.control_point.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            client.content_directory.create_object(container_id, arguments)
            return 'Ok'
        return 'Error'

    def xmlrpc_import_resource(self, device_id, source_uri, destination_uri):
        print('import_resource', source_uri, destination_uri)
        device = self.control_point.get_device_with_id(device_id)
        if device is not None:
            client = device.get_client()
            client.content_directory.import_resource(source_uri,
                                                     destination_uri)
            return 'Ok'
        return 'Error'

    def xmlrpc_put_resource(self, url, path):
        print('put_resource', url, path)
        self.control_point.put_resource(url, path)
        return 'Ok'

    def xmlrpc_ping(self):
        print('ping')
        return 'Ok'


def startXMLRPC(control_point, port):
    from twisted.web import server
    r = XMLRPC(control_point)
    print(f'XMLRPC-API on port {port:d} ready')
    reactor.listenTCP(port, server.Site(r))


if __name__ == '__main__':

    config = {}
    config['logmode'] = 'warning'
    config['serverport'] = 30020
    from coherence.base import Coherence

    ctrl = ControlPoint(Coherence(config),
                        auto_client=[])

    def show_devices():
        print('show_devices')
        for d in ctrl.get_devices():
            print(d, d.get_id())

    def the_result(r):
        print('result', r, r.get_id())

    def query_devices():
        print('query_devices')
        ctrl.add_query(DeviceQuery('host', '192.168.0.1', the_result))

    def query_devices2():
        print('query_devices with timeout')
        ctrl.add_query(
            DeviceQuery('host', '192.168.0.1', the_result, timeout=10,
                        oneshot=False))

    def stop_reactor(*args):
        reactor.stop()
        print('Stoped reactor successfully')

    reactor.callLater(2, show_devices)
    reactor.callLater(3, query_devices)
    reactor.callLater(4, query_devices2)
    reactor.callLater(5, ctrl.add_query, DeviceQuery(
        'friendly_name', 'Coherence Test Content',
        the_result, timeout=10, oneshot=False))
    reactor.callLater(6, stop_reactor)

    reactor.run()
