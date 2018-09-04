# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Frank Scholz <coherence@beebits.net>

# Dimming service

from twisted.web import resource

from coherence.upnp.core import service
from coherence.upnp.core.soap_service import UPnPPublisher


class DimmingControl(service.ServiceControl, UPnPPublisher):

    def __init__(self, server):
        service.ServiceControl.__init__(self)
        UPnPPublisher.__init__(self)
        self.service = server
        self.variables = server.get_variables()
        self.actions = server.get_actions()


class DimmingServer(service.ServiceServer, resource.Resource):
    logCategory = 'dimming_server'

    def __init__(self, device, backend=None):
        self.device = device
        if backend is None:
            backend = self.device.backend
        resource.Resource.__init__(self)
        service.ServiceServer.__init__(self, 'Dimming', self.device.version,
                                       backend)

        self.control = DimmingControl(self)
        self.putChild(self.scpd_url, service.scpdXML(self, self.control))
        self.putChild(self.control_url, self.control)
