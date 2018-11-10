# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2010, Frank Scholz <dev@coherence-project.org>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
:class:`InternetGatewayDeviceClient`
------------------------------------

A class representing an embedded WAN's Device.
'''

from eventdispatcher import EventDispatcher, Property

from coherence import log
from coherence.upnp.devices.wan_device_client import WANDeviceClient


class InternetGatewayDeviceClient(EventDispatcher, log.LogAble):
    '''
    .. versionchanged:: 0.9.0

        * Introduced inheritance from EventDispatcher
        * The emitted events changed:

            - Coherence.UPnP.DeviceClient.detection_completed =>
              device_client_detection_completed

        * Changed class variable :attr:`detection_completed` to benefit
          from the EventDispatcher's properties
    '''
    logCategory = 'igd_client'

    detection_completed = Property(False)
    '''
    To know whenever the device detection has completed. Defaults to `False`
    and it will be set automatically to `True` by the class method
    :meth:`embedded_device_notified`.
    '''

    def __init__(self, device):
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)
        self.register_event(
            'device_client_detection_completed',
        )
        self.device = device
        self.device.bind(
            embedded_device_client_detection_completed=self.embedded_device_notified)  # noqa

        self.device_type = self.device.get_friendly_device_type()
        self.version = int(self.device.get_device_type_version())
        self.icons = device.icons

        self.wan_device = None

        try:
            wan_device = self.device.get_embedded_device_by_type(
                'WANDevice')[0]
            self.wan_device = WANDeviceClient(wan_device)
        except Exception as e:
            self.warning(f'Embedded WANDevice device not available, device not'
                         f' implemented properly according to the UPnP'
                         f' specification [error: {e}]')
            raise

        self.info(f'InternetGatewayDevice {device.get_friendly_name()}')

    def remove(self):
        self.info('removal of InternetGatewayDeviceClient started')
        if self.wan_device is not None:
            self.wan_device.remove()

    def embedded_device_notified(self, device):
        self.info(f'EmbeddedDevice {device} sent notification')
        if self.detection_completed:
            return
        self.detection_completed = True
        self.dispatch_event(
            'device_client_detection_completed',
            client=self, udn=self.device.udn)
