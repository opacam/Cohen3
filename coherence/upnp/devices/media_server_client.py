# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2006, Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
:class:`MediaServerClient`
--------------------------

A class representing an media server client device.
'''

from eventdispatcher import EventDispatcher, Property

from coherence import log
from coherence.upnp.services.clients.av_transport_client import \
    AVTransportClient
from coherence.upnp.services.clients.connection_manager_client import \
    ConnectionManagerClient
from coherence.upnp.services.clients.content_directory_client import \
    ContentDirectoryClient


class MediaServerClient(EventDispatcher, log.LogAble):
    '''
    .. versionchanged:: 0.9.0

        * Introduced inheritance from EventDispatcher
        * The emitted events changed:

            - Coherence.UPnP.DeviceClient.detection_completed =>
              device_client_detection_completed

        * Changed some class variable to benefit from the EventDispatcher's
          properties:

            - :attr:`detection_completed`
            - :attr:`content_directory`

    '''
    logCategory = 'ms_client'

    detection_completed = Property(False)
    '''
    To know whenever the device detection has completed. Defaults to `False`
    and it will be set automatically to `True` by the class method
    :meth:`service_notified`.
    '''

    content_directory = Property(None)

    def __init__(self, device):
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)
        self.register_event(
            'device_client_detection_completed',
        )

        self.device = device
        self.device.bind(device_service_notified=self.service_notified)
        self.device_type = self.device.get_friendly_device_type()

        self.version = int(self.device.get_device_type_version())
        self.icons = device.icons
        self.scheduled_recording = None
        self.connection_manager = None
        self.av_transport = None

        for service in self.device.get_services():
            if service.get_type() in [
                    'urn:schemas-upnp-org:service:ContentDirectory:1',
                    'urn:schemas-upnp-org:service:ContentDirectory:2']:
                self.content_directory = ContentDirectoryClient(service)
            if service.get_type() in [
                    'urn:schemas-upnp-org:service:ConnectionManager:1',
                    'urn:schemas-upnp-org:service:ConnectionManager:2']:
                self.connection_manager = ConnectionManagerClient(service)
            if service.get_type() in [
                    'urn:schemas-upnp-org:service:AVTransport:1',
                    'urn:schemas-upnp-org:service:AVTransport:2']:
                self.av_transport = AVTransportClient(service)
            if service.detection_completed:
                self.service_notified(service)

        self.info(f'MediaServer {device.get_friendly_name()}')
        if self.content_directory:
            self.info('ContentDirectory available')
        else:
            self.warning(
                'ContentDirectory not available, device not implemented'
                ' properly according to the UPnP specification')
            return
        if self.connection_manager:
            self.info('ConnectionManager available')
        else:
            self.warning(
                'ConnectionManager not available, device not implemented'
                ' properly according to the UPnP specification')
            return
        if self.av_transport:
            self.info('AVTransport (optional) available')
        if self.scheduled_recording:
            self.info('ScheduledRecording (optional) available')

    def remove(self):
        self.info('removal of MediaServerClient started')
        if self.content_directory is not None:
            self.content_directory.remove()
        if self.connection_manager is not None:
            self.connection_manager.remove()
        if self.av_transport is not None:
            self.av_transport.remove()
        if self.scheduled_recording is not None:
            self.scheduled_recording.remove()

    def service_notified(self, service):
        self.info(f'notified about {service}')
        if self.detection_completed:
            return
        if self.content_directory is not None:
            if not hasattr(self.content_directory.service,
                           'last_time_updated'):
                return
            if self.content_directory.service.last_time_updated is None:
                return
        if self.connection_manager is not None:
            if not hasattr(self.connection_manager.service,
                           'last_time_updated'):
                return
            if self.connection_manager.service.last_time_updated is None:
                return
        if self.av_transport is not None:
            if not hasattr(self.av_transport.service, 'last_time_updated'):
                return
            if self.av_transport.service.last_time_updated is None:
                return
        if self.scheduled_recording is not None:
            if not hasattr(self.scheduled_recording.service,
                           'last_time_updated'):
                return
            if self.scheduled_recording.service.last_time_updated is None:
                return
        self.detection_completed = True
        self.dispatch_event(
            'device_client_detection_completed',
            client=self, udn=self.device.udn)
        self.info(f'detection_completed for {self}')

    def state_variable_change(self, variable, usn):
        self.info('%(name)r changed from %(old_value)r to %(value)r',
                  vars(variable))

    def print_results(self, results):
        self.info(f'results= {results}')

    def process_meta(self, results):
        for k, v in results.items():
            dfr = self.content_directory.browse(k, 'BrowseMetadata')
            dfr.addCallback(self.print_results)
