# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2006, Frank Scholz <coherence@beebits.net>

'''
Receiver registrar service
'''

from twisted.web import resource

from coherence.upnp.core import service
from coherence.upnp.core.soap_service import UPnPPublisher
from coherence.upnp.core.utils import to_string


class FakeMediaReceiverRegistrarBackend:

    def upnp_IsAuthorized(self, *args, **kwargs):
        r = {'Result': 1}
        return r

    def upnp_IsValidated(self, *args, **kwargs):
        r = {'Result': 1}
        return r

    def upnp_RegisterDevice(self, *args, **kwargs):
        ''' in parameter RegistrationReqMsg '''
        RegistrationReqMsg = kwargs['RegistrationReqMsg']
        # FIXME: check with WMC and WMP
        r = {'RegistrationRespMsg': 'WTF should be in here?'}
        return r


class MediaReceiverRegistrarControl(service.ServiceControl, UPnPPublisher):

    def __init__(self, server):
        service.ServiceControl.__init__(self)
        UPnPPublisher.__init__(self)
        self.service = server
        self.variables = server.get_variables()
        self.actions = server.get_actions()


class MediaReceiverRegistrarServer(service.ServiceServer, resource.Resource):
    implementation = 'optional'

    def __init__(self, device, backend=None):
        self.device = device
        if backend is None:
            backend = self.device.backend
        resource.Resource.__init__(self)
        self.version = 1
        self.namespace = 'microsoft.com'
        self.id_namespace = 'microsoft.com'
        service.ServiceServer.__init__(self, 'X_MS_MediaReceiverRegistrar',
                                       self.version, backend)
        self.device_description_tmpl = 'xbox-description-1.xml'

        self.control = MediaReceiverRegistrarControl(self)
        self.putChild(b'scpd.xml', service.scpdXML(self, self.control))
        self.putChild(b'control', self.control)

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
            <title>Cohen3 (MediaReceiverRegistrarServer)</title>
            <link rel="stylesheet" type="text/css" href="/styles/main.css" />
        </head>
        <h5>
            <img class="logo-icon" src="/server-images/coherence-icon.svg">
            </img>Root of the MediaReceiverRegistrar</h5>
        <div class="list"><ul>{self.listchilds(request.uri)}</ul></div>
        </html>'''
        return html.encode('ascii')
