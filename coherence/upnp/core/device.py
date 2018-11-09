# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright (C) 2006 Fluendo, S.A. (www.fluendo.com).
# Copyright 2006, Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
Devices
=======

This module contains two classes describing UPnP devices.

:class:`Device`
---------------

The base class for all devices.

:class:`RootDevice`
-------------------

A device representing a root device.
'''

import time

from lxml import etree
from eventdispatcher import EventDispatcher, Property, ListProperty
from twisted.internet import defer

from coherence import log
from coherence.upnp.core import utils
from coherence.upnp.core.service import Service
from . import xml_constants

ns = xml_constants.UPNP_DEVICE_NS


class Device(EventDispatcher, log.LogAble):
    '''
    Represents a UPnP's device, but this is not a root device, it's the base
    class used for any device. See :class:`RootDevice` if you want a root
    device.

    .. versionchanged:: 0.9.0

        * Migrated from louie/dispatcher to EventDispatcher
        * The emitted events changed:

            - Coherence.UPnP.Device.detection_completed =>
              device_detection_completed
            - Coherence.UPnP.Device.remove_client =>
              device_remove_client

        * New events: device_service_notified, device_got_client
        * Changes some class variables to benefit from the EventDispatcher's
          properties:

            - :attr:`client`
            - :attr:`devices`
            - :attr:`services`
            - :attr:`client`
            - :attr:`detection_completed`
    '''
    logCategory = 'device'

    client = Property(None)
    '''
    Defined by :class:`~coherence.upnp.devices.controlpoint.ControlPoint`.
    It should be one of:

        - Initialized instance of a class
          :class:`~coherence.upnp.devices.media_server_client.MediaServerClient`
        - Initialized instance of a class
          :class:`~coherence.upnp.devices.media_renderer_client.MediaRendererClient`
        - Initialized instance of a class
          :class:`~coherence.upnp.devices.internet_gateway_device_client.InternetGatewayDeviceClient`

    Whenever a client is set an event will be sent notifying it by
    :meth:`on_client`.
    '''  # noqa

    icons = ListProperty([])
    '''A list of the device icons.'''

    devices = ListProperty([])
    '''A list of the device devices.'''

    services = ListProperty([])
    '''A list of the device services.'''

    detection_completed = Property(False)
    '''
    To know whenever the device detection has completed. Defaults to `False`
    and it will be set automatically to `True` by the class method
    :meth:`receiver`.
    '''

    def __init__(self, parent=None, udn=None):
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)
        self.register_event(
            'device_detection_completed',
            'device_remove_client',

            'device_service_notified',
            'device_got_client',
        )
        self.parent = parent
        self.udn = udn
        # self.uid = self.usn[:-len(self.st)-2]
        self.friendly_name = ''
        self.device_type = ''
        self.upnp_version = 'n/a'
        self.friendly_device_type = '[unknown]'
        self.device_type_version = 0

    def __repr__(self):
        return \
            f'embedded device {self.friendly_name} ' \
            f'{self.device_type}, parent {self.parent}'

    # def __del__(self):
    #    # print('Device removal completed')
    #    pass

    def as_dict(self):
        d = {'device_type': self.get_device_type(),
             'friendly_name': self.get_friendly_name(),
             'udn': self.get_id(),
             'services': [x.as_dict() for x in self.services]}
        icons = []
        for icon in self.icons:
            icons.append({'mimetype': icon['mimetype'], 'url': icon['url'],
                          'height': icon['height'], 'width': icon['width'],
                          'depth': icon['depth']})
        d['icons'] = icons
        return d

    def remove(self, *args):
        self.info(f'removal of  {self.friendly_name} {self.udn}')
        while len(self.devices) > 0:
            device = self.devices.pop()
            self.debug(f'try to remove {device}')
            device.remove()
        while len(self.services) > 0:
            service = self.services.pop()
            self.debug(f'try to remove {service}')
            service.remove()
        if self.client is not None:
            self.dispatch_event(
                'device_remove_client', self.udn, self.client)
            self.client = None
        # del self
        return True

    def receiver(self, *args, **kwargs):
        if self.detection_completed:
            return
        for s in self.services:
            if not s.detection_completed:
                return
            self.dispatch_event(
                'device_service_notified', service=s)
        if self.udn is None:
            return
        self.detection_completed = True
        if self.parent is not None:
            self.info(f'embedded device {self.friendly_name} '
                      f'{self.device_type} initialized, parent {self.parent}')
        self.dispatch_event('device_detection_completed', None, device=self)
        if self.parent is not None:
            self.dispatch_event(
                'device_detection_completed', self.parent, device=self)
        else:
            self.dispatch_event(
                'device_detection_completed', self, device=self)

    def service_detection_failed(self, device):
        self.remove()

    def get_id(self):
        return self.udn

    def get_uuid(self):
        return self.udn[5:]

    def get_embedded_devices(self):
        return self.devices

    def get_embedded_device_by_type(self, type):
        r = []
        for device in self.devices:
            if type == device.friendly_device_type:
                r.append(device)
        return r

    def get_services(self):
        return self.services

    def get_service_by_type(self, type):
        if not isinstance(type, (tuple, list)):
            type = [type, ]
        for service in self.services:
            _, _, _, service_class, version = service.service_type.split(':')
            if service_class in type:
                return service

    def add_service(self, service):
        '''
        Add a service to the device. Also we check if service already notified,
        and trigger the callback if needed. We also connect the device to
        service in case the service still not completed his detection in order
        that the device knows when the service has completed his detection.

        Args:
            service (object): A service which should be an initialized instance
                              of :class:`~coherence.upnp.core.service.Service`

        '''
        self.debug(f'add_service {service}')
        if service.detection_completed:
            self.receiver(service)
        service.bind(service_detection_completed=self.receiver,
                     service_detection_failed=self.service_detection_failed)
        self.services.append(service)

    # :fixme: This fails as Service.get_usn() is not implemented.
    def remove_service_with_usn(self, service_usn):
        for service in self.services:
            if service.get_usn() == service_usn:
                service.unbind(
                    service_detection_completed=self.receiver,
                    service_detection_failed=self.service_detection_failed)
                self.services.remove(service)
                service.remove()
                break

    def add_device(self, device):
        self.debug(f'Device add_device {device}')
        self.devices.append(device)

    def get_friendly_name(self):
        return self.friendly_name

    def get_device_type(self):
        return self.device_type

    def get_friendly_device_type(self):
        return self.friendly_device_type

    def get_markup_name(self):
        try:
            return self._markup_name
        except AttributeError:
            self._markup_name = \
                f'{self.friendly_device_type}:{self.device_type_version} ' \
                f'{self.friendly_name}'
            return self._markup_name

    def get_device_type_version(self):
        return self.device_type_version

    def set_client(self, client):
        self.client = client

    def get_client(self):
        return self.client

    def on_client(self, *args):
        '''
        Automatically triggered whenever a client is set or changed. Emmit
        an event notifying that the client has changed.

        .. versionadded:: 0.9.0
        '''
        self.dispatch_event(
            'device_got_client', self, client=self.client)

    def renew_service_subscriptions(self):
        ''' iterate over device's services and renew subscriptions '''
        self.info(f'renew service subscriptions for {self.friendly_name}')
        now = time.time()
        for service in self.services:
            self.info(f'check service {service.id} {service.get_sid()} '
                      f'{service.get_timeout()} {now}')
            if service.get_sid() is not None:
                if service.get_timeout() < now:
                    self.debug(f'wow, we lost an event subscription for '
                               f'{self.friendly_name} {service.get_id()}, '
                               f'maybe we need to rethink the loop time and '
                               f'timeout calculation?')
                if service.get_timeout() < now + 30:
                    service.renew_subscription()

        for device in self.devices:
            device.renew_service_subscriptions()

    def unsubscribe_service_subscriptions(self):
        '''Iterate over device's services and unsubscribe subscriptions '''
        sl = []
        for service in self.get_services():
            if service.get_sid() is not None:
                sl.append(service.unsubscribe())
        dl = defer.DeferredList(sl)
        return dl

    def parse_device(self, d):
        self.info(f'parse_device {d}')
        self.device_type = d.findtext(f'./{{{ns}}}deviceType')
        self.friendly_device_type, self.device_type_version = \
            self.device_type.split(':')[-2:]
        self.friendly_name = d.findtext(f'./{{{ns}}}friendlyName')
        self.udn = d.findtext(f'./{{{ns}}}UDN')
        self.info(f'found udn {self.udn} {self.friendly_name}')

        try:
            self.manufacturer = d.findtext(f'./{{{ns}}}manufacturer')
        except Exception:
            pass
        try:
            self.manufacturer_url = d.findtext(f'./{{{ns}}}manufacturerURL')
        except Exception:
            pass
        try:
            self.model_name = d.findtext(f'./{{{ns}}}modelName')
        except Exception:
            pass
        try:
            self.model_description = d.findtext(f'./{{{ns}}}modelDescription')
        except Exception:
            pass
        try:
            self.model_number = d.findtext(f'./{{{ns}}}modelNumber')
        except Exception:
            pass
        try:
            self.model_url = d.findtext(f'./{{{ns}}}modelURL')
        except Exception:
            pass
        try:
            self.serial_number = d.findtext(f'./{{{ns}}}serialNumber')
        except Exception:
            pass
        try:
            self.upc = d.findtext(f'./{{{ns}}}UPC')
        except Exception:
            pass
        try:
            self.presentation_url = d.findtext(f'./{{{ns}}}presentationURL')
        except Exception:
            pass

        try:
            for dlna_doc in d.findall(
                    './{urn:schemas-dlna-org:device-1-0}X_DLNADOC'):
                try:
                    self.dlna_dc.append(dlna_doc.text)
                except AttributeError:
                    self.dlna_dc = []
                    self.dlna_dc.append(dlna_doc.text)
        except Exception:
            pass

        try:
            for dlna_cap in d.findall(
                    './{urn:schemas-dlna-org:device-1-0}X_DLNACAP'):
                for cap in dlna_cap.text.split(','):
                    try:
                        self.dlna_cap.append(cap)
                    except AttributeError:
                        self.dlna_cap = []
                        self.dlna_cap.append(cap)
        except Exception:
            pass

        icon_list = d.find(f'./{{{ns}}}iconList')
        if icon_list is not None:
            from urllib.parse import urlparse
            url_base = '%s://%s' % urlparse(self.get_location())[:2]
            for icon in icon_list.findall(f'./{{{ns}}}icon'):
                try:
                    i = {}
                    i['mimetype'] = icon.find(f'./{{{ns}}}mimetype').text
                    i['width'] = icon.find(f'./{{{ns}}}width').text
                    i['height'] = icon.find(f'./{{{ns}}}height').text
                    i['depth'] = icon.find(f'./{{{ns}}}depth').text
                    i['realurl'] = icon.find(f'./{{{ns}}}url').text
                    i['url'] = self.make_fullyqualified(
                        i['realurl']).decode('utf-8')
                    self.icons.append(i)
                    self.debug(f'adding icon {i} for {self.friendly_name}')
                except Exception as e:
                    import traceback
                    self.debug(traceback.format_exc())
                    self.warning(
                        f'device {self.friendly_name} seems to have an invalid'
                        f' icon description, ignoring that icon [error: {e}]')

        serviceList = d.find(f'./{{{ns}}}serviceList')
        if serviceList is not None:
            for service in serviceList.findall(f'./{{{ns}}}service'):
                serviceType = service.findtext(f'{{{ns}}}serviceType')
                serviceId = service.findtext(f'{{{ns}}}serviceId')
                controlUrl = service.findtext(f'{{{ns}}}controlURL')
                eventSubUrl = service.findtext(f'{{{ns}}}eventSubURL')
                presentationUrl = service.findtext(f'{{{ns}}}presentationURL')
                scpdUrl = service.findtext(f'{{{ns}}}SCPDURL')
                # check if values are somehow reasonable
                if len(scpdUrl) == 0:
                    self.warning('service has no uri for its description')
                    continue
                if len(eventSubUrl) == 0:
                    self.warning('service has no uri for eventing')
                    continue
                if len(controlUrl) == 0:
                    self.warning('service has no uri for controling')
                    continue
                try:
                    self.add_service(
                        Service(serviceType, serviceId, self.get_location(),
                                controlUrl,
                                eventSubUrl, presentationUrl, scpdUrl, self))
                except Exception as e:
                    self.error(
                        f'Error on adding service: {service} [ERROR: {e}]')

            # now look for all sub devices
            embedded_devices = d.find(f'./{{{ns}}}deviceList')
            if embedded_devices is not None:
                for d in embedded_devices.findall(f'./{{{ns}}}device'):
                    embedded_device = Device(self)
                    self.add_device(embedded_device)
                    embedded_device.parse_device(d)

        self.receiver()

    def get_location(self):
        return self.parent.get_location()

    def get_usn(self):
        return self.parent.get_usn()

    def get_upnp_version(self):
        return self.parent.get_upnp_version()

    def get_urlbase(self):
        return self.parent.get_urlbase()

    def get_presentation_url(self):
        try:
            return self.make_fullyqualified(self.presentation_url)
        except Exception:
            return ''

    def get_parent_id(self):
        try:
            return self.parent.get_id()
        except Exception:
            return ''

    def make_fullyqualified(self, url):
        return self.parent.make_fullyqualified(url)

    def as_tuples(self):
        r = []

        def append(name, attribute):
            try:
                if isinstance(attribute, tuple):
                    if callable(attribute[0]):
                        v1 = attribute[0]()
                    else:
                        v1 = getattr(self, attribute[0])
                    if v1 in [None, 'None']:
                        return
                    if callable(attribute[1]):
                        v2 = attribute[1]()
                    else:
                        v2 = getattr(self, attribute[1])
                    if v2 in [None, 'None']:
                        return
                    r.append((name, (v1, v2)))
                    return
                elif callable(attribute):
                    v = attribute()
                else:
                    v = getattr(self, attribute)
                if v not in [None, 'None']:
                    r.append((name, v))
            except Exception as e:
                self.error(f'Device.as_tuples: {e}')
                import traceback
                self.debug(traceback.format_exc())

        try:
            r.append(('Location', (self.get_location(),
                                   self.get_location())))
        except Exception:
            pass
        try:
            append('URL base', self.get_urlbase)
        except Exception:
            pass
        try:
            r.append(('UDN', self.get_id()))
        except Exception:
            pass
        try:
            r.append(('Type', self.device_type))
        except Exception:
            pass
        try:
            r.append(('UPnP Version', self.upnp_version))
        except Exception:
            pass
        try:
            r.append(('DLNA Device Class', ','.join(self.dlna_dc)))
        except Exception:
            pass
        try:
            r.append(('DLNA Device Capability', ','.join(self.dlna_cap)))
        except Exception:
            pass
        try:
            r.append(('Friendly Name', self.friendly_name))
        except Exception:
            pass
        try:
            append('Manufacturer', 'manufacturer')
        except Exception:
            pass
        try:
            append('Manufacturer URL',
                   ('manufacturer_url', 'manufacturer_url'))
        except Exception:
            pass
        try:
            append('Model Description', 'model_description')
        except Exception:
            pass
        try:
            append('Model Name', 'model_name')
        except Exception:
            pass
        try:
            append('Model Number', 'model_number')
        except Exception:
            pass
        try:
            append('Model URL', ('model_url', 'model_url'))
        except Exception:
            pass
        try:
            append('Serial Number', 'serial_number')
        except Exception:
            pass
        try:
            append('UPC', 'upc')
        except Exception:
            pass
        try:
            append('Presentation URL',
                   ('presentation_url',
                    lambda: self.make_fullyqualified(
                        getattr(self, 'presentation_url'))))
        except Exception:
            pass

        for icon in self.icons:
            r.append(('Icon', (icon['realurl'],
                               self.make_fullyqualified(icon['realurl']),
                               {'Mimetype': icon['mimetype'],
                                'Width': icon['width'],
                                'Height': icon['height'],
                                'Depth': icon['depth']})))

        return r


class RootDevice(Device):
    '''
    Description for a root device.

    .. versionchanged:: 0.9.0

        * Migrated from louie/dispatcher to EventDispatcher
        * The emitted events changed:

            - Coherence.UPnP.RootDevice.detection_completed =>
              root_device_detection_completed
            - Coherence.UPnP.RootDevice.removed => root_device_removed
    '''

    root_detection_completed = Property(False)
    '''
    To know whenever the root device detection has completed. Defaults to
    `False` and it will be set automatically to `True` by the class method
    :meth:`device_detect`.
    '''

    def __init__(self, infos):
        self.usn = infos['USN']
        self.udn = infos.get('UDN', '')
        self.server = infos['SERVER']
        self.st = infos['ST']
        self.location = infos['LOCATION']
        self.manifestation = infos['MANIFESTATION']
        self.host = infos['HOST']
        Device.__init__(self, None)
        self.register_event(
            'root_device_detection_completed',
            'root_device_removed',
        )
        self.bind(detection_completed=self.device_detect)
        # we need to handle root device completion
        # these events could be our self or our children.
        self.parse_description()
        self.debug(f'RootDevice initialized: {self.location}')

    def __repr__(self):
        return \
            f'rootdevice {self.friendly_name} {self.udn} {self.st} ' \
            f'{self.host}, manifestation {self.manifestation}'

    def remove(self, *args):
        result = Device.remove(self, *args)
        self.dispatch_event('root_device_removed', self, usn=self.get_usn())
        return result

    def get_usn(self):
        return self.usn

    def get_st(self):
        return self.st

    def get_location(self):
        return self.location if isinstance(self.location, bytes) else \
            self.location.encode('ascii') if self.location else None

    def get_upnp_version(self):
        return self.upnp_version

    def get_urlbase(self):
        return self.urlbase if isinstance(self.urlbase, bytes) else \
            self.urlbase.encode('ascii') if self.urlbase else None

    def get_host(self):
        return self.host

    def is_local(self):
        if self.manifestation == 'local':
            return True
        return False

    def is_remote(self):
        if self.manifestation != 'local':
            return True
        return False

    def device_detect(self, *args, **kwargs):
        '''
        This method is automatically triggered whenever the property of the
        base class :attr:`Device.detection_completed` is set to `True`. Here we
        perform some more operations, before the :class:`RootDevice` emits
        an event notifying that the root device detection has completed.
        '''
        self.debug(f'device_detect {kwargs}')
        self.debug(f'root_detection_completed {self.root_detection_completed}')
        if self.root_detection_completed:
            return
        # our self is not complete yet

        self.debug(f'detection_completed {self.detection_completed}')
        if not self.detection_completed:
            return

        # now check child devices.
        self.debug(f'self.devices {self.devices}')
        for d in self.devices:
            self.debug(f'check device {d.detection_completed} {d}')
            if not d.detection_completed:
                return
        # now must be done, so notify root done
        self.root_detection_completed = True
        self.info(f'rootdevice {self.friendly_name} {self.st} {self.host} '
                  f'initialized, manifestation {self.manifestation}')
        self.dispatch_event(
            'root_device_detection_completed', device=self)

    def add_device(self, device):
        self.debug(f'RootDevice add_device {device}')
        self.devices.append(device)

    def get_devices(self):
        self.debug(f'RootDevice get_devices: {self.devices}')
        return self.devices

    def parse_description(self):

        def gotPage(x):
            self.debug(f'got device description from {self.location}')
            self.debug(f'data is {x}')
            data, headers = x
            xml_data = None
            try:
                xml_data = etree.fromstring(data)
            except Exception:
                self.warning(f'Invalid device description received from '
                             f'{self.location}')
                import traceback
                self.debug(traceback.format_exc())

            if xml_data is not None:
                tree = xml_data
                major = tree.findtext(f'./{{{ns}}}specVersion/{{{ns}}}major')
                minor = tree.findtext(f'./{{{ns}}}specVersion/{{{ns}}}minor')
                try:
                    self.upnp_version = '.'.join((major, minor))
                except Exception:
                    self.upnp_version = 'n/a'
                try:
                    self.urlbase = tree.findtext(f'./{{{ns}}}URLBase')
                except Exception:
                    import traceback
                    self.debug(traceback.format_exc())

                d = tree.find(f'./{{{ns}}}device')
                if d is not None:
                    self.parse_device(d)  # root device
            self.debug(f'device parsed successfully {self.location}')

        def gotError(failure, url):
            self.warning(f'error getting device description from {url}')
            self.info(failure)

        try:
            utils.getPage(
                self.location).addCallbacks(
                gotPage, gotError, None, None, [self.location], None)
        except Exception as e:
            self.error(f'Error on parsing device description: {e}')

    def make_fullyqualified(self, url):
        '''Be aware that this function returns a byte string'''
        self.info(f'make_fullyqualified: {url} [{type(url)}]')
        if isinstance(url, str):
            url = url.encode('ascii')
        if url.startswith(b'http://'):
            return url
        from urllib.parse import urljoin
        base = self.get_urlbase()
        if isinstance(base, str):
            base = base.encode('ascii')
        if base is not None:
            if base[-1] != b'/':
                base += b'/'
            r = urljoin(base, url)
        else:
            loc = self.get_location()
            if isinstance(loc, str):
                loc = loc.encode('ascii')
            r = urljoin(loc, url)
        return r
