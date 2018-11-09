# -*- coding: utf-8 -*-

# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright 2008, Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
Basics
======

This module contains two classes which will be used as a base classes which
will be useful to create our device classes: MediaRenderer and MediaServer.

:class:`DeviceHttpRoot`
-----------------------

Inherits from :class:`twisted.web.resource.Resource` and is used as a a base
class by class the :class:`~coherence.upnp.devices.media_renderer.HttpRoot`.

:class:`BasicDeviceMixin`
-------------------------

This is an EventDispatcher object used as a base class by the classes
:class:`~coherence.upnp.devices.media_renderer.MediaRenderer` and
:class:`~coherence.upnp.devices.media_server.MediaServer`. It contains some
methods that will help us to initialize the backend as well as the methods
:meth:`BasicDeviceMixin.register` and :meth:`BasicDeviceMixin.unregister` which
will take care to register/unregister our device.
'''

import os.path

from twisted.python import util
from twisted.web import resource, static
from twisted.internet import reactor

from eventdispatcher import EventDispatcher, Property

from coherence.upnp.core.utils import to_string
from coherence import log


class DeviceHttpRoot(resource.Resource, log.LogAble):
    logCategory = 'basicdevice'

    def __init__(self, server):
        resource.Resource.__init__(self)
        log.LogAble.__init__(self)
        self.server = server

    def getChildWithDefault(self, path, request):
        self.info(
            f'DeviceHttpRoot {self.server.device_type} getChildWithDefault '
            f'{path} {request.uri} {request.client}')
        self.info(request.getAllHeaders())
        if not isinstance(path, bytes):
            path = path.encode('ascii')
        if path in self.children:
            return self.children[path]
        if request.uri == b'/':
            return self
        return self.getChild(path, request)

    def getChild(self, name, request):
        self.info(f'DeviceHttpRoot {name} getChild {request}')
        if not isinstance(name, bytes):
            name = name.encode('ascii')
        ch = None
        if ch is None:
            p = util.sibpath(__file__.encode('ascii'), name)
            if os.path.exists(p):
                ch = static.File(p)
        self.info(f'DeviceHttpRoot ch {ch}')
        return ch

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
            <title>Cohen3 (DeviceHttpRoot)</title>
            <link rel="stylesheet" type="text/css" href="/styles/main.css" />
        </head>
        <h5>
            <img class="logo-icon" src="/server-images/coherence-icon.svg">
            </img>
            Root of the {self.server.backend.name} {self.server.device_type}
        </h5>
        <div class="list"><ul>{self.listchilds(request.uri)}</ul></div>
        </html>'''
        return html.encode('ascii')


# class RootDeviceXML(static.Data):
#   def __init__(self, hostname, uuid, urlbase,
#                xmlns='urn:schemas-upnp-org:device-1-0',
#                device_uri_base='urn:schemas-upnp-org:device',
#                device_type='BasicDevice',
#                version=2,
#                friendly_name='Coherence UPnP BasicDevice',
#                manufacturer='beebits.net',
#                manufacturer_url='http://coherence.beebits.net',
#                model_description='Coherence UPnP BasicDevice',
#                model_name='Coherence UPnP BasicDevice',
#                model_number=__version__,
#                model_url='http://coherence.beebits.net',
#                serial_number='0000001',
#                presentation_url='',
#                services=None,
#                devices=None,
#                icons=None,
#                dlna_caps=None):
#         uuid = str(uuid)
#         root = ET.Element('root')
#         root.attrib['xmlns'] = xmlns
#         device_type_uri = ':'.join(
#             (device_uri_base, device_type, str(version)))
#         e = ET.SubElement(root, 'specVersion')
#         ET.SubElement(e, 'major').text = '1'
#         ET.SubElement(e, 'minor').text = '0'
#         #ET.SubElement(root, 'URLBase').text = urlbase + uuid[5:] + '/'
#
#         d = ET.SubElement(root, 'device')
#
#         if device_type == 'MediaServer':
#             x = ET.SubElement(d, 'dev:X_DLNADOC')
#             x.text = 'DMS-1.50'
#             x = ET.SubElement(d, 'dev:X_DLNADOC')
#             x.text = 'M-DMS-1.50'
#         elif device_type == 'MediaRenderer':
#             x = ET.SubElement(d, 'dev:X_DLNADOC')
#             x.text = 'DMR-1.50'
#             x = ET.SubElement(d, 'dev:X_DLNADOC')
#             x.text = 'M-DMR-1.50'
#
#         if len(dlna_caps) > 0:
#             if isinstance(dlna_caps, basestring):
#                 dlna_caps = [dlna_caps]
#             for cap in dlna_caps:
#                 x = ET.SubElement(d, 'dev:X_DLNACAP')
#                 x.text = cap
#
#         ET.SubElement(d, 'deviceType').text = device_type_uri
#         ET.SubElement(d, 'friendlyName').text = friendly_name
#         ET.SubElement(d, 'manufacturer').text = manufacturer
#         ET.SubElement(d, 'manufacturerURL').text = manufacturer_url
#         ET.SubElement(d, 'modelDescription').text = model_description
#         ET.SubElement(d, 'modelName').text = model_name
#         ET.SubElement(d, 'modelNumber').text = model_number
#         ET.SubElement(d, 'modelURL').text = model_url
#         ET.SubElement(d, 'serialNumber').text = serial_number
#         ET.SubElement(d, 'UDN').text = uuid
#         ET.SubElement(d, 'UPC').text = ''
#         ET.SubElement(d, 'presentationURL').text = presentation_url
#
#         if len(services):
#             e = ET.SubElement(d, 'serviceList')
#             for service in services:
#                 id = service.get_id()
#                 s = ET.SubElement(e, 'service')
#                 try:
#                     namespace = service.namespace
#                 except:
#                     namespace = 'schemas-upnp-org'
#                 if(hasattr(service, 'version') and
#                     service.version < version):
#                     v = service.version
#                 else:
#                     v = version
#                 ET.SubElement(s, 'serviceType').text = \
#                     f'urn:{namespace}:service:{id}:{int(v):d}'
#                 try:
#                     namespace = service.id_namespace
#                 except:
#                     namespace = 'upnp-org'
#                 ET.SubElement(s, 'serviceId').text = \
#                     f'urn:{namespace}:serviceId:{id}'
#                 ET.SubElement(s, 'SCPDURL').text = \
#                     '/' + uuid[5:] + '/' + id + '/' + service.scpd_url
#                 ET.SubElement(s, 'controlURL').text = \
#                     '/' + uuid[5:] + '/' + id + '/' + service.control_url
#                 ET.SubElement(s, 'eventSubURL').text = \
#                     '/' + uuid[5:] + '/' + id + '/' + \
#                     service.subscription_url
#
#         if len(devices):
#             e = ET.SubElement(d, 'deviceList')
#
#         if len(icons):
#             e = ET.SubElement(d, 'iconList')
#             for icon in icons:
#
#                 icon_path = ''
#                 if icon.has_key('url'):
#                     if icon['url'].startswith('file://'):
#                         icon_path = icon['url'][7:]
#                     elif icon['url'] == '.face':
#                         icon_path = os.path.join(
#                             os.path.expanduser('~'), '.face')
#                     else:
#                         from pkg_resources import resource_filename
#                         icon_path = os.path.abspath(
#                             resource_filename(
#                                 __name__,
#                                 os.path.join(
#                                     '..', '..', '..', 'misc',
#                                     'device-icons', icon['url'])))
#
#                 if os.path.exists(icon_path):
#                     i = ET.SubElement(e, 'icon')
#                     for k, v in icon.items():
#                         if k == 'url':
#                             if v.startswith('file://'):
#                                 ET.SubElement(i, k).text = \
#                                     '/' + uuid[5:] + '/' + \
#                                     os.path.basename(v)
#                                 continue
#                             elif v == '.face':
#                                 ET.SubElement(i, k).text = \
#                                     '/' + uuid[5:] + '/' + 'face-icon.png'
#                                 continue
#                             else:
#                                 ET.SubElement(i, k).text = \
#                                     '/' + uuid[5:] + '/' + \
#                                     os.path.basename(v)
#                                 continue
#                         ET.SubElement(i, k).text = str(v)
#         #if self.has_level(LOG_DEBUG):
#         #    indent( root)
#
        # self.xml = '''<?xml version="1.0" encoding="utf-8"?>''' + \
        #            ET.tostring(root, encoding='utf-8')
#         static.Data.__init__(self, self.xml, 'text/xml')


class BasicDeviceMixin(EventDispatcher):
    '''
    This is used as a base class for the following classes:

        - :class:`~coherence.upnp.devices.media_renderer.MediaRenderer`
        - :class:`~coherence.upnp.devices.media_server.MediaServer`

    It contains some methods that will help us to initialize the backend
    (:meth:`on_backend`, :meth:`init_complete` and :meth:`init_failed`). There
    is no need to call those methods, because it will be automatically
    triggered based on the backend status.

    .. versionchanged:: 0.9.0

       * Introduced inheritance from EventDispatcher
       * Changed class variable :attr:`backend` to benefit from the
         EventDispatcher's properties
    '''

    backend = Property(None)
    '''The device's backend. When this variable is filled it will automatically
    trigger the method :meth:`on_backend`.
    '''

    def __init__(self, coherence, backend, **kwargs):
        EventDispatcher.__init__(self)
        self.coherence = coherence
        if not hasattr(self, 'version'):
            self.version = int(
                kwargs.get('version', self.coherence.config.get('version', 2)))

        try:
            self.uuid = str(kwargs['uuid'])
            if not self.uuid.startswith('uuid:'):
                self.uuid = 'uuid:' + self.uuid
        except KeyError:
            from coherence.upnp.core.uuid import UUID
            self.uuid = UUID()

        urlbase = str(self.coherence.urlbase)
        if urlbase[-1] != '/':
            urlbase += '/'
        self.urlbase = urlbase + str(self.uuid)[5:]

        kwargs['urlbase'] = self.urlbase
        self.icons = kwargs.get('iconlist', kwargs.get('icons', []))
        if len(self.icons) == 0:
            if 'icon' in kwargs:
                if isinstance(kwargs['icon'], dict):
                    self.icons.append(kwargs['icon'])
                else:
                    self.icons = kwargs['icon']

        reactor.callLater(0.2, self.fire, backend, **kwargs)

    def on_backend(self, *arsg):
        '''
        This function is automatically triggered whenever the :attr:`backend`
        class variable changes. Here we connect the backend initialization
        with the device.

        .. versionadded:: 0.9.0
        '''
        if self.backend is None:
            return
        if self.backend.init_completed:
            self.init_complete(self.backend)
        self.backend.bind(
            backend_init_completed=self.init_complete,
            backend_init_failed=self.init_failed,
        )

    def init_complete(self, backend):
        # This must be overwritten in subclass
        pass

    def init_failed(self, backend, msg):
        if self.backend != backend:
            return
        self.warning(f'backend not installed, {self.device_type} '
                     f'activation aborted - {msg.getErrorMessage()}')
        self.debug(msg)
        try:
            del self.coherence.active_backends[str(self.uuid)]
        except KeyError:
            pass

    def register(self):
        s = self.coherence.ssdp_server
        uuid = str(self.uuid)
        host = self.coherence.hostname
        self.msg(f'{self.device_type} register')
        # we need to do this after the children are there,
        # since we send notifies
        s.register(
            'local',
            f'{uuid}::upnp:rootdevice',
            'upnp:rootdevice',
            self.coherence.urlbase + uuid[5:] + '/' +
            f'description-{self.version:d}.xml',
            host=host)

        s.register(
            'local',
            uuid,
            uuid,
            self.coherence.urlbase + uuid[5:] + '/' +
            f'description-{self.version:d}.xml',
            host=host)

        version = self.version
        while version > 0:
            if version == self.version:
                silent = False
            else:
                silent = True
            s.register(
                'local',
                f'{uuid}::urn:schemas-upnp-org:device:{self.device_type}:{version:d}',  # noqa
                f'urn:schemas-upnp-org:device:{self.device_type}:{version:d}',
                self.coherence.urlbase + uuid[5:] + '/' +
                f'description-{version:d}.xml',
                silent=silent,
                host=host)
            version -= 1

        for service in self._services:
            device_version = self.version
            service_version = self.version
            if hasattr(service, 'version'):
                service_version = service.version
            silent = False

            while service_version > 0:
                try:
                    namespace = service.namespace
                except AttributeError:
                    namespace = 'schemas-upnp-org'

                device_description_tmpl = f'description-{device_version:d}.xml'
                if hasattr(service, 'device_description_tmpl'):
                    device_description_tmpl = service.device_description_tmpl

                s.register(
                    'local',
                    f'{uuid}::urn:{namespace}:service:{service.id}:{service_version:d}',  # noqa
                    f'urn:{namespace}:service:{service.id}:{service_version:d}',  # noqa
                    self.coherence.urlbase + uuid[5:] +
                    '/' + device_description_tmpl,
                    silent=silent,
                    host=host)

                silent = True
                service_version -= 1
                device_version -= 1

    def unregister(self):

        if self.backend is not None and hasattr(self.backend, 'release'):
            self.backend.release()

        if not hasattr(self, '_services'):
            ''' seems we never made it to actually
                completing that device
            '''
            return

        for service in self._services:
            try:
                service.check_subscribers_loop.stop()
            except Exception as e1:
                ms = f'BasicDeviceMixin.unregister: {e1}'
                if hasattr(self, 'warning'):
                    self.warning(ms)
                else:
                    print('WARNING: ', ms)
            if hasattr(service, 'check_moderated_loop') and \
                    service.check_moderated_loop is not None:
                try:
                    service.check_moderated_loop.stop()
                except Exception as e2:
                    ms = f'BasicDeviceMixin.unregister: {e2}'
                    if hasattr(self, 'warning'):
                        self.warning(ms)
                    else:
                        print('WARNING: ', ms)
            if hasattr(service, 'release'):
                service.release()
            if hasattr(service, '_release'):
                service._release()

        s = self.coherence.ssdp_server
        uuid = str(self.uuid)
        self.coherence.remove_web_resource(uuid[5:])

        version = self.version
        while version > 0:
            s.doByebye(
                f'{uuid}::urn:schemas-upnp-org:device:{self.device_type}:{version:d}')  # noqa
            for service in self._services:
                if hasattr(service, 'version') and service.version < version:
                    continue
                try:
                    namespace = service.namespace
                except AttributeError:
                    namespace = 'schemas-upnp-org'
                s.doByebye(
                    f'{uuid}::urn:{namespace}:service:{service.id}:{version:d}'
                )

            version -= 1

        s.doByebye(uuid)
        s.doByebye(f'{uuid}::upnp:rootdevice')
