# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2006, Frank Scholz <coherence@beebits.net>

from coherence.upnp.services.clients.connection_manager_client import ConnectionManagerClient
from coherence.upnp.services.clients.content_directory_client import ContentDirectoryClient
from coherence.upnp.services.clients.av_transport_client import AVTransportClient

from coherence import log

import coherence.extern.louie as louie


class MediaServerClient(log.Loggable):
    logCategory = 'ms_client'

    def __init__(self, device):
        log.Loggable.__init__(self)
        self.device = device
        self.device_type = self.device.get_friendly_device_type()
        self.version = int(self.device.get_device_type_version())
        self.icons = device.icons
        self.scheduled_recording = None
        self.content_directory = None
        self.connection_manager = None
        self.av_transport = None

        self.detection_completed = False

        louie.connect(self.service_notified, signal='Coherence.UPnP.DeviceClient.Service.notified', sender=self.device)

        for service in self.device.get_services():
            if service.get_type() in ["urn:schemas-upnp-org:service:ContentDirectory:1",
                                      "urn:schemas-upnp-org:service:ContentDirectory:2"]:
                self.content_directory = ContentDirectoryClient(service)
            if service.get_type() in ["urn:schemas-upnp-org:service:ConnectionManager:1",
                                      "urn:schemas-upnp-org:service:ConnectionManager:2"]:
                self.connection_manager = ConnectionManagerClient(service)
            if service.get_type() in ["urn:schemas-upnp-org:service:AVTransport:1",
                                      "urn:schemas-upnp-org:service:AVTransport:2"]:
                self.av_transport = AVTransportClient(service)

        self.info("MediaServer %s", self.device.get_friendly_name())
        if self.content_directory:
            self.info("ContentDirectory available")
        else:
            self.warning("ContentDirectory not available, device not implemented properly according to the UPnP specification")
            return
        if self.connection_manager:
            self.info("ConnectionManager available")
        else:
            self.warning("ConnectionManager not available, device not implemented properly according to the UPnP specification")
            return
        if self.av_transport:
            self.info("AVTransport (optional) available")
        if self.scheduled_recording:
            self.info("ScheduledRecording (optional) available")

    def remove(self):
        self.info("removal of MediaServerClient started")
        if self.content_directory is not None:
            self.content_directory.remove()
        if self.connection_manager is not None:
            self.connection_manager.remove()
        if self.av_transport is not None:
            self.av_transport.remove()
        if self.scheduled_recording is not None:
            self.scheduled_recording.remove()

    def service_notified(self, service):
        self.info('notified about %r', service)
        if self.detection_completed:
            return
        if self.content_directory is not None:
            if not hasattr(self.content_directory.service, 'last_time_updated'):
                return
            if self.content_directory.service.last_time_updated is None:
                return
        if self.connection_manager is not None:
            if not hasattr(self.connection_manager.service, 'last_time_updated'):
                return
            if self.connection_manager.service.last_time_updated is None:
                return
        if self.av_transport is not None:
            if not hasattr(self.av_transport.service, 'last_time_updated'):
                return
            if self.av_transport.service.last_time_updated is None:
                return
        if self.scheduled_recording is not None:
            if not hasattr(self.scheduled_recording.service, 'last_time_updated'):
                return
            if self.scheduled_recording.service.last_time_updated is None:
                return
        self.detection_completed = True
        louie.send('Coherence.UPnP.DeviceClient.detection_completed', None, client=self, udn=self.device.udn)
        self.info('detection_completed for %r', self)

    def state_variable_change(self, variable, usn):
        self.info('%(name)r changed from %(old_value)r to %(value)r', vars(variable))

    def print_results(self, results):
        self.info("results= %s", results)

    def process_meta(self, results):
        for k, v in results.items():
            dfr = self.content_directory.browse(k, "BrowseMetadata")
            dfr.addCallback(self.print_results)
