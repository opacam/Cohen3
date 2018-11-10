# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2010, Frank Scholz <dev@coherence-project.org>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
:class:`WANConnectionDeviceClient`
----------------------------------

A class representing an WAN connection client device.
'''

from eventdispatcher import EventDispatcher, Property

from coherence import log
from coherence.upnp.services.clients.wan_ip_connection_client import \
    WANIPConnectionClient
from coherence.upnp.services.clients.wan_ppp_connection_client import \
    WANPPPConnectionClient


class WANConnectionDeviceClient(EventDispatcher, log.LogAble):
    '''
    .. versionchanged:: 0.9.0

        * Introduced inheritance from EventDispatcher
        * The emitted events changed:

            - Coherence.UPnP.EmbeddedDeviceClient.detection_completed =>
              embedded_device_client_detection_completed

        * Changed class variable :attr:`detection_completed` to benefit
          from the EventDispatcher's properties
    '''
    logCategory = 'igd_client'

    detection_completed = Property(False)
    '''
    To know whenever the wan device detection has completed. Defaults to
    `False` and it will be set automatically to `True` by the class method
    :meth:`service_notified`.
    '''

    def __init__(self, device):
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)
        self.register_event(
            'embedded_device_client_detection_completed',
        )
        self.device = device
        self.device.bind(service_notified=self.service_notified)
        self.device_type = self.device.get_friendly_device_type()

        self.version = int(self.device.get_device_type_version())
        self.icons = device.icons

        self.wan_ip_connection = None
        self.wan_ppp_connection = None

        for service in self.device.get_services():
            if service.get_type() in [
                    'urn:schemas-upnp-org:service:WANIPConnection:1']:
                self.wan_ip_connection = WANIPConnectionClient(service)
            if service.get_type() in [
                    'urn:schemas-upnp-org:service:WANPPPConnection:1']:
                self.wan_ppp_connection = WANPPPConnectionClient(service)
        self.info(f'WANConnectionDevice {device.get_friendly_name()}')
        if self.wan_ip_connection:
            self.info('WANIPConnection service available')
        if self.wan_ppp_connection:
            self.info('WANPPPConnection service available')

    def remove(self):
        self.info('removal of WANConnectionDeviceClient started')
        if self.wan_ip_connection is not None:
            self.wan_ip_connection.remove()
        if self.wan_ppp_connection is not None:
            self.wan_ppp_connection.remove()

    def service_notified(self, service):
        self.info(f'Service {service} sent notification')
        if self.detection_completed:
            return
        if self.wan_ip_connection is not None:
            if not hasattr(self.wan_ip_connection.service,
                           'last_time_updated'):
                return
            if self.wan_ip_connection.service.last_time_updated is None:
                return
        if self.wan_ppp_connection is not None:
            if not hasattr(self.wan_ppp_connection.service,
                           'last_time_updated'):
                return
            if self.wan_ppp_connection.service.last_time_updated is None:
                return
        self.detection_completed = True
        self.dispatch_event(
            'embedded_device_client_detection_completed', self)
