# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2006,2007 Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

import os.path

from coherence import log
from coherence.upnp.core.utils import StaticFile
from coherence.upnp.devices.media_server import RootDeviceXML
from coherence.upnp.devices.basics import DeviceHttpRoot, BasicDeviceMixin
from coherence.upnp.services.servers.av_transport_server import \
    AVTransportServer
from coherence.upnp.services.servers.connection_manager_server import \
    ConnectionManagerServer
from coherence.upnp.services.servers.rendering_control_server import \
    RenderingControlServer


class HttpRoot(DeviceHttpRoot):
    logCategory = 'mediarenderer'


class MediaRenderer(log.LogAble, BasicDeviceMixin):
    logCategory = 'mediarenderer'
    device_type = 'MediaRenderer'

    def __init__(self, coherence, backend, **kwargs):
        BasicDeviceMixin.__init__(self, coherence, backend, **kwargs)
        log.LogAble.__init__(self)

    def fire(self, backend, **kwargs):

        if not kwargs.get('no_thread_needed', False):
            ''' this could take some time, put it in a  thread to be sure
                it doesn't block as we can't tell for sure that every
                backend is implemented properly '''

            from twisted.internet import threads
            d = threads.deferToThread(backend, self, **kwargs)

            def backend_ready(backend):
                self.backend = backend

            def backend_failure(x):
                self.warning(
                    f'backend {backend} not installed, {self.device_type}'
                    f' activation aborted - {x.getErrorMessage()}')
                self.debug(x)

            d.addCallback(backend_ready)
            d.addErrback(backend_failure)

            # FIXME: we need a timeout here so if the signal we wait for
            # not arrives we'll can close down this device
        else:
            self.backend = backend(self, **kwargs)

    def init_complete(self, backend):
        if self.backend != backend:
            return
        self._services = []
        self._devices = []

        try:
            self.connection_manager_server = ConnectionManagerServer(self)
            self._services.append(self.connection_manager_server)
        except LookupError as msg:
            self.warning(f'ConnectionManagerServer {msg}')
            raise LookupError(msg)

        try:
            self.rendering_control_server = RenderingControlServer(self)
            self._services.append(self.rendering_control_server)
        except LookupError as msg:
            self.warning(f'RenderingControlServer {msg}')
            raise LookupError(msg)

        try:
            self.av_transport_server = AVTransportServer(self)
            self._services.append(self.av_transport_server)
        except LookupError as msg:
            self.warning(f'AVTransportServer {msg}')
            raise LookupError(msg)

        upnp_init = getattr(self.backend, 'upnp_init', None)
        if upnp_init:
            upnp_init()

        self.web_resource = HttpRoot(self)
        self.coherence.add_web_resource(str(self.uuid)[5:], self.web_resource)

        try:
            dlna_caps = self.backend.dlna_caps
        except AttributeError:
            dlna_caps = []

        version = self.version
        while version > 0:
            self.web_resource.putChild(
                f'description-{version}.xml'.encode('ascii'),
                RootDeviceXML(
                    self.coherence.hostname,
                    str(self.uuid),
                    self.coherence.urlbase,
                    device_type=self.device_type,
                    version=version,
                    # presentation_url='/'+str(self.uuid)[5:],
                    friendly_name=self.backend.name,
                    # model_description=f'Coherence UPnP A/V {self.device_type}',  # noqa
                    # model_name=f'Coherence UPnP A/V {self.device_type}',
                    services=self._services,
                    devices=self._devices,
                    icons=self.icons,
                    dlna_caps=dlna_caps))
            version -= 1

        self.web_resource.putChild(b'ConnectionManager',
                                   self.connection_manager_server)
        self.web_resource.putChild(b'RenderingControl',
                                   self.rendering_control_server)
        self.web_resource.putChild(b'AVTransport', self.av_transport_server)

        for icon in self.icons:
            if 'url' in icon:
                if icon['url'].startswith('file://'):
                    if os.path.exists(icon['url'][7:]):
                        self.web_resource.putChild(
                            os.path.basename(icon['url']).encode('ascii'),
                            StaticFile(icon['url'][7:],
                                       defaultType=icon['mimetype']))
                elif icon['url'] == '.face':
                    face_path = os.path.abspath(
                        os.path.join(os.path.expanduser('~'), '.face'))
                    if os.path.exists(face_path):
                        self.web_resource.putChild(
                            b'face-icon.png',
                            StaticFile(
                                face_path, defaultType=icon['mimetype']))
                else:
                    from pkg_resources import resource_filename
                    icon_path = os.path.abspath(
                        resource_filename(
                            __name__,
                            os.path.join('..', '..', '..', 'misc',
                                         'device-icons', icon['url'])))
                    if os.path.exists(icon_path):
                        self.web_resource.putChild(
                            icon['url'].encode('ascii'),
                            StaticFile(icon_path,
                                       defaultType=icon['mimetype']))

        self.register()
        self.warning(f'{self.backend.name} {self.device_type} '
                     f'({self.backend}) activated with {str(self.uuid)[5:]}')
