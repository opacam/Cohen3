# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2010, Frank Scholz <dev@coherence-project.org>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
:class:`WANDeviceClient`
------------------------

A class representing an embedded device with a WAN client.
'''

from eventdispatcher import EventDispatcher, Property

from coherence import log
from coherence.upnp.devices.wan_connection_device_client import \
    WANConnectionDeviceClient
from coherence.upnp.services.clients.wan_common_interface_config_client import\
    WANCommonInterfaceConfigClient


class WANDeviceClient(EventDispatcher, log.LogAble):
    '''
    .. versionchanged:: 0.9.0

        * Introduced inheritance from EventDispatcher
        * The emitted events changed:

            - Coherence.UPnP.EmbeddedDeviceClient.detection_completed =>
              embedded_device_client_detection_completed

        * Changed some class variable to benefit from the EventDispatcher's
          properties:

            - :attr:`embedded_device_detection_completed`
            - :attr:`service_detection_completed`

    '''
    logCategory = 'wan_device_client'

    embedded_device_detection_completed = Property(False)
    '''
    To know whenever the embedded device detection has completed. Defaults to
    `False` and it will be set automatically to `True` by the class method
    :meth:`embedded_device_notified`.
    '''

    service_detection_completed = Property(False)
    '''
    To know whenever the service detection has completed. Defaults to `False`
    and it will be set automatically to `True` by the class method
    :meth:`service_notified`.
    '''

    def __init__(self, device):
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)
        self.register_event(
            'embedded_device_client_detection_completed',
        )

        self.device = device
        self.device.bind(
            embedded_device_client_detection_completed=self.embedded_device_notified,  # noqa
            service_notified=self.service_notified
        )
        self.device_type = self.device.get_friendly_device_type()

        self.version = int(self.device.get_device_type_version())
        self.icons = device.icons

        self.wan_connection_device = None
        self.wan_common_interface_connection = None

        try:
            wan_connection_device = \
                self.device.get_embedded_device_by_type(
                    'WANConnectionDevice')[0]
            self.wan_connection_device = WANConnectionDeviceClient(
                wan_connection_device)
        except Exception as er:
            self.warning(
                f'Embedded WANConnectionDevice device not available, device '
                f'not implemented properly according to the UPnP '
                f'specification [ERROR: {er}]')
            raise

        for service in self.device.get_services():
            if service.get_type() in [
                    'urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1']:
                self.wan_common_interface_connection = \
                    WANCommonInterfaceConfigClient(service)

        self.info(f'WANDevice {device.get_friendly_name()}')

    def remove(self):
        self.info('removal of WANDeviceClient started')
        if self.wan_common_interface_connection is not None:
            self.wan_common_interface_connection.remove()
        if self.wan_connection_device is not None:
            self.wan_connection_device.remove()

    def embedded_device_notified(self, device):
        self.info(f'EmbeddedDevice {device} sent notification')
        if self.embedded_device_detection_completed:
            return

        self.embedded_device_detection_completed = True
        if self.embedded_device_detection_completed is True and \
                self.service_detection_completed is True:
            self.dispatch_event(
                'embedded_device_client_detection_completed', self)

    def service_notified(self, service):
        self.info(f'Service {service} sent notification')
        if self.service_detection_completed:
            return
        if self.wan_common_interface_connection is not None:
            if not hasattr(self.wan_common_interface_connection.service,
                           'last_time_updated'):
                return
            if self.wan_common_interface_connection.\
                    service.last_time_updated is None:
                return
        self.service_detection_completed = True
        if self.embedded_device_detection_completed is True and \
                self.service_detection_completed is True:
            self.dispatch_event(
                'embedded_device_client_detection_completed', self)
