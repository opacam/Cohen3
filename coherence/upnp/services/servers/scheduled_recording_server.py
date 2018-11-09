# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2009, Frank Scholz <coherence@beebits.net>

'''
ScheduledRecording service
==========================
'''

from twisted.web import resource

from coherence.upnp.core import service
from coherence.upnp.core.soap_service import UPnPPublisher
from coherence.upnp.core.utils import to_string


class ScheduledRecordingControl(service.ServiceControl, UPnPPublisher):

    def __init__(self, server):
        service.ServiceControl.__init__(self)
        UPnPPublisher.__init__(self)
        self.service = server
        self.variables = server.get_variables()
        self.actions = server.get_actions()


class ScheduledRecordingServer(service.ServiceServer, resource.Resource):
    implementation = 'optional'

    def __init__(self, device, backend=None):
        self.device = device
        if backend is None:
            backend = self.device.backend
        resource.Resource.__init__(self)
        self.version = 1
        service.ServiceServer.__init__(
            self, 'ScheduledRecording', self.version, backend)

        self.control = ScheduledRecordingControl(self)
        self.putChild(self.scpd_url, service.scpdXML(self, self.control))
        self.putChild(self.control_url, self.control)

    def listchilds(self, uri):
        uri = to_string(uri)
        cl = ''
        for c in self.children:
            c = to_string(c)
            cl += f'<li><a href={uri}/{c}>{c}</a></li>'
        return cl

    def render(self, request):
        html = f'''\
        <html>
        <head>
            <title>Cohen3 (ScheduledRecordingServer)</title>
            <link rel="stylesheet" type="text/css" href="/styles/main.css" />
        </head>
        <h5>
            <img class="logo-icon" src="/server-images/coherence-icon.svg">
            </img>Root of the ScheduledRecording</h5>
        <div class="list"><ul>{self.listchilds(request.uri)}</ul></div>
        </html>'''
        return html.encode('ascii')
