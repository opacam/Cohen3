# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php

# Copyright (C) 2006 Fluendo, S.A. (www.fluendo.com).
# Copyright 2006, Frank Scholz <coherence@beebits.net>
# Copyright 2018, Pol Canelles <canellestudi@gmail.com>

'''
Services
========

This module contains several classes related to services:

:class:`Service`
----------------

Object representing a device's service.

:class:`ServiceServer`
----------------------

A Service's server.

:class:`scpdXML`
----------------

A `twisted.web.resource.Resource` representing xml's data for SCPD.

.. note:: SCPD is a Service Control Point Definition, for defining the actions
          offered by the various services in a UPnP's network.

:class:`ServiceControl`
-----------------------

Object to control service's SOAP actions.
'''

import os
import time
from urllib.parse import urlparse

from lxml import etree
from twisted.internet import defer, reactor
from twisted.internet import task
from twisted.python import failure, util
from twisted.web import static

from eventdispatcher import EventDispatcher, Property

from coherence import log
from coherence.upnp.core import action
from coherence.upnp.core import event
from coherence.upnp.core import utils
from coherence.upnp.core import variable
from coherence.upnp.core.event import EventSubscriptionServer
from coherence.upnp.core.soap_proxy import SOAPProxy
from coherence.upnp.core.soap_service import errorCode
from coherence.upnp.core.xml_constants import UPNP_SERVICE_NS

global subscribers
subscribers = dict()

NS_UPNP_ORG_EVENT_1_0 = 'urn:schemas-upnp-org:event-1-0'


def subscribe(service):
    subscribers[service.get_sid()] = service


def unsubscribe(service):
    subscribers.pop(service.get_sid(), None)


class Service(EventDispatcher, log.LogAble):
    '''
    This class represents a Device's service. Emits events which will be
    received by class :class:`~coherence.upnp.core.device.Device`.

    .. versionchanged:: 0.9.0

        * Migrated from louie/dispatcher to EventDispatcher
        * The emitted events changed:

            - Coherence.UPnP.Service.detection_completed =>
              service_detection_completed
            - Coherence.UPnP.Service.detection_failed =>
              service_detection_failed
            - Coherence.UPnP.DeviceClient.Service.Event.processed =>
              service_event_processed
            - Coherence.UPnP.DeviceClient.Service.notified =>
              service_notified

        * changed class variable :attr:`detection_completed` to benefit from
          the EventDispatcher's properties

    .. note:: This class initializes some events outside this class. This is
              done this way to make easier to make connections between
              this service and the module :mod:`~coherence.dbus_service`,
              which uses some events triggered by
              :class:`~coherence.upnp.core.variable.StateVariable`. The
              mentioned events are (old => new):

                  - Coherence.UPnP.StateVariable.changed =>
                    state_variable_changed
                  - Coherence.UPnP.StateVariable.{var name}.changed =>
                    state_variable_{var name}_changed

    .. warning:: This class is special regarding EventDispatcher, because some
                events are initialized outside this class by the class
                :class:`~coherence.upnp.core.variable.StateVariable`.
    '''

    logCategory = 'service_client'

    detection_completed = Property(False)
    '''
    To know whenever the service detection has completed. Defaults to `False`
    and it will be set automatically to `True` by the class method
    :meth:`parse_actions`.
    '''

    def __init__(self, service_type, service_id, location, control_url,
                 event_sub_url, presentation_url, scpd_url, device):
        log.LogAble.__init__(self)
        EventDispatcher.__init__(self)
        self.register_event(
            'service_detection_completed',
            'service_detection_failed',
            'service_event_processed',
            'service_notified',
        )
        self.debug('Service.__init__: ...')

        self.service_type = service_type
        self.id = service_id
        self.control_url = control_url if isinstance(location, bytes) else \
            control_url.encode('ascii') if control_url else None
        self.event_sub_url = \
            event_sub_url if isinstance(event_sub_url, bytes) else \
            event_sub_url.encode('ascii') if event_sub_url else None
        self.presentation_url = \
            presentation_url if isinstance(presentation_url, bytes) else \
            presentation_url.encode('ascii') if presentation_url else None
        self.scpd_url = scpd_url if isinstance(scpd_url, bytes) else \
            scpd_url.encode('ascii') if scpd_url else None
        self.device = device
        self._actions = {}
        self._variables = {0: {}}
        self._var_subscribers = {}
        self.subscription_id = None
        self.timeout = 0

        self.event_connection = None
        self.last_time_updated = None

        self.client = None
        self.info('\t- parsing ...')
        if isinstance(location, bytes):
            location = location.decode('utf-8')
        parsed = urlparse(location)
        self.url_base = f'{parsed[0]}://{parsed[1]}'.encode('ascii')

        self.parse_actions()
        self.info(f'{device.friendly_name} {self.service_type} '
                  f'{self.id} initialized')

    def as_tuples(self):
        r = []

        def append(name, attribute):
            try:
                if isinstance(attribute, tuple):
                    a0 = attribute[0] if isinstance(attribute[0], str) else \
                        attribute[0].decode('utf-8')
                    if callable(a0):
                        v1 = attribute[0]()
                    elif hasattr(self, a0):
                        v1 = getattr(self, a0)
                    else:
                        v1 = a0
                    if v1 in [None, 'None', b'']:
                        return
                    if callable(attribute[1]):
                        v2 = attribute[1]()
                    elif hasattr(self, attribute[1]):
                        v2 = getattr(self, attribute[1])
                    else:
                        v2 = attribute[1]
                    if v2 in [None, 'None', b'']:
                        return
                    if len(attribute) > 2:
                        r.append((name, (v1, v2, attribute[2])))
                    else:
                        r.append((name, (v1, v2)))
                    return
                elif callable(attribute):
                    v = attribute()
                elif hasattr(self, attribute):
                    v = getattr(self, attribute)
                else:
                    v = attribute
                if v not in [None, 'None', b'']:
                    r.append((name, v))
            except Exception as e:
                self.error(f'Service.as_tuples.append: {e}')
                import traceback
                self.debug(traceback.format_exc())

        r.append(('Location',
                  (self.device.get_location(), self.device.get_location())))
        append('URL base', self.device.get_urlbase)
        r.append(('UDN', self.device.get_id()))
        r.append(('Type', self.service_type))
        r.append(('ID', self.id))
        append('Service Description URL', (
            self.scpd_url, lambda: self.device.make_fullyqualified(
                self.scpd_url)))
        append('Control URL', (
            self.control_url, lambda: self.device.make_fullyqualified(
                self.control_url), False))
        append('Event Subscription URL', (
            self.event_sub_url, lambda: self.device.make_fullyqualified(
                self.event_sub_url), False))

        return r

    def as_dict(self):
        d = {'type': self.service_type}
        d['actions'] = [a.as_dict() for a in list(self._actions.values())]
        return d

    def __repr__(self):
        return f'Service {self.service_type} {self.id}'

    # def __del__(self):
    #    print('Service deleted')
    #    pass

    def _get_client(self, name):
        self.debug(f'Service._get_client: {name}')
        url = self.get_control_url()
        self.debug(f'\t- url: {url}')
        namespace = self.get_type()
        action = f'{namespace}#{name}'
        self.debug(f'\t- action: {action}')
        client = SOAPProxy(url, namespace=('u', namespace), soapaction=action)
        self.debug(f'\t- client: {client}')
        return client

    def remove(self):
        self.info(f'removal of  {self.device.friendly_name} '
                  f'{self.service_type} {self.id}')
        try:
            self.renew_subscription_call.cancel()
        except Exception:
            pass
        if self.event_connection is not None:
            self.event_connection.teardown()
        if self.subscription_id is not None:
            self.unsubscribe()
        for name, action in list(self._actions.items()):
            self.debug(f'remove {name} {action}')
            del self._actions[name]
            del action
        for instance, variables in list(self._variables.items()):
            for name, variable in list(variables.items()):
                del variables[name]
                del variable
            if instance in variables:
                del variables[instance]
            del variables
        del self

    def get_device(self):
        return self.device

    def get_type(self):
        return self.service_type

    def set_timeout(self, timeout):
        self.info(f'set timout for {self.device.friendly_name}/'
                  f'{self.service_type} to {int(timeout):d}')
        self.timeout = timeout
        try:
            self.renew_subscription_call.reset(int(self.timeout) - 30)
            self.info(f'reset renew subscription call for '
                      f'{self.device.friendly_name}/{self.service_type} to '
                      f'{int(self.timeout) - 30:d}')
        except Exception:
            self.renew_subscription_call = reactor.callLater(
                int(self.timeout) - 30, self.renew_subscription)
            self.info(f'starting renew subscription call for '
                      f'{self.device.friendly_name}/{self.service_type} to '
                      f'{int(self.timeout) - 30:d}')

    def get_timeout(self):
        return self.timeout

    def get_id(self):
        return self.id

    def get_sid(self):
        return self.subscription_id

    def set_sid(self, sid):
        self.info(f'set subscription id for {self.device.friendly_name}/'
                  f'{self.service_type} to {sid}')
        self.subscription_id = sid
        if sid is not None:
            subscribe(self)
            self.debug(f'add subscription for {self.id}')

    def get_actions(self):
        return self._actions

    def get_scpdXML(self):
        return self.scpdXML

    def get_action(self, name):
        try:
            return self._actions[name]
        except KeyError:
            return None  # not implemented

    def get_state_variables(self, instance):
        return self._variables.get(int(instance))

    def get_state_variable(self, name, instance=0):
        return self._variables.get(int(instance)).get(name)

    def get_control_url(self):
        return self.device.make_fullyqualified(self.control_url)

    def get_event_sub_url(self):
        return self.device.make_fullyqualified(self.event_sub_url)

    def get_presentation_url(self):
        return self.device.make_fullyqualified(self.presentation_url)

    def get_scpd_url(self):
        return self.device.make_fullyqualified(self.scpd_url)

    def get_base_url(self):
        return self.device.make_fullyqualified('.')

    def subscribe(self):
        self.debug(f'subscribe {self.id}')
        event.subscribe(self)
        # global subscribers
        # subscribers[self.get_sid()] = self

    def unsubscribe(self):

        def remove_it(r, sid):
            self.debug(f'remove subscription for {self.id}')
            unsubscribe(self)
            self.subscription_id = None
            # global subscribers
            # if subscribers.has_key(sid):
            #    del subscribers[sid]

        self.debug(f'unsubscribe {self.id}')
        d = event.unsubscribe(self)
        d.addCallback(remove_it, self.get_sid())
        return d

    def subscribe_for_variable(self, var_name, instance=0, callback=None,
                               signal=False):
        variable = self.get_state_variable(var_name)
        if variable:
            if callback is not None:
                if signal:
                    callback(variable)
                    variable.bind(state_variable_changed=callback)
                else:
                    variable.subscribe(callback)

    def renew_subscription(self):
        self.info('renew_subscription')
        event.subscribe(self)

    def process_event(self, event):
        self.info(f'process event {self} {event}')
        for var_name, var_value in list(event.items()):
            if var_name == 'LastChange':
                self.info('we have a LastChange event')
                self.get_state_variable(var_name, 0).update(var_value)
                tree = etree.fromstring(var_value)
                namespace_uri, tag = tree.tag[1:].split('}', 1)
                for instance in tree.findall(f'{{{namespace_uri}}}InstanceID'):
                    instance_id = instance.attrib['val']
                    self.info(f'instance_id {instance} {instance_id}')
                    for var in instance.getchildren():
                        self.info(f'var {var}')
                        namespace_uri, tag = var.tag[1:].split('}', 1)
                        self.info(f'{namespace_uri} {tag} {var.attrib["val"]}')
                        self.get_state_variable(tag, instance_id).update(
                            var.attrib['val'])
                        self.info(f'updated var {var}')
                        if len(var.attrib) > 1:
                            self.info(f'Extended StateVariable '
                                      f'{var.tag} - {var.attrib}')
                            if 'channel' in var.attrib and \
                                    var.attrib['channel'] != 'Master':
                                # TODO handle attributes that
                                # them selves have multiple instances
                                self.info(
                                    f'Skipping update to {var.tag} its not '
                                    f'for master channel {var.attrib}')
                                pass
                            else:
                                if not self.get_state_variables(instance_id):
                                    # TODO Create instance ?
                                    self.error(
                                        f'{self} update failed (not self.get_'
                                        f'state_variables(instance_id)) '
                                        f'{instance_id}')
                                elif tag not in self.get_state_variables(
                                        instance_id):
                                    # TODO Create instance StateVariable?
                                    # SONOS stuff
                                    self.error(
                                        f'{self} update failed (not self.get_'
                                        f'state_variables(instance_id).'
                                        f'has_key(tag)) {tag}')
                                else:
                                    val = None
                                    if 'val' in var.attrib:
                                        val = var.attrib['val']
                                    # self.debug(
                                    #     f'{self} update {namespace_uri} '
                                    #     f'{tag} {var.attrib["val"]}')
                                    self.get_state_variable(
                                        tag, instance_id).update(
                                        var.attrib['val'])
                                    self.debug(
                                        f'updated "attributed" var {var}')
                self.dispatch_event(
                    'service_event_processed',
                    self, (var_name, var_value, event.raw))
            else:
                self.get_state_variable(var_name, 0).update(var_value)
                self.dispatch_event(
                    'service_event_processed',
                    self, (var_name, var_value, event.raw))
        if self.last_time_updated is None:
            # The clients (e.g. media_server_client) check for last time
            # to detect whether service detection is complete so we need to
            # set it here and now to avoid a potential race condition
            self.last_time_updated = time.time()
            self.dispatch_event(
                'service_notified', sender=self.device, service=self)
            self.info(f'send signal '
                      f'Coherence.UPnP.DeviceClient.Service.notified for '
                      f'{self}')
        self.last_time_updated = time.time()

    def parse_actions(self):
        self.debug('Service.parse_actions: ...')

        def gotPage(x):
            data, headers = x
            if isinstance(data, str):
                self.scpdXML = data.encode('ascii')
            else:
                self.scpdXML = data
            try:
                tree = etree.fromstring(self.scpdXML)
            except Exception as e:
                self.warning(f'Invalid service description received from '
                             f'{self.get_scpd_url()}: {e}')
                return
            ns = UPNP_SERVICE_NS
            # self.debug(f'processPage tree is: {tree}')

            for action_node in tree.findall(f'.//{{{ns}}}action'):
                name = action_node.findtext(f'{{{ns}}}name')
                # self.debug(f'\t->processing action: {name}')
                arguments = []
                for argument in action_node.findall(f'.//{{{ns}}}argument'):
                    arg_name = argument.findtext(f'{{{ns}}}name')
                    arg_direction = argument.findtext(f'{{{ns}}}direction')
                    arg_state_var = argument.findtext(
                        f'{{{ns}}}relatedStateVariable')
                    arguments.append(action.Argument(arg_name, arg_direction,
                                                     arg_state_var))
                self._actions[name] = action.Action(self, name, 'n/a',
                                                    arguments)

            for var_node in tree.findall(f'.//{{{ns}}}stateVariable'):
                send_events = var_node.attrib.get('sendEvents', 'yes')
                name = var_node.findtext(f'{{{ns}}}name')
                data_type = var_node.findtext(f'{{{ns}}}dataType')
                values = []
                # we need to ignore this, as there we don't get there our
                # {urn:schemas-beebits-net:service-1-0}X_withVendorDefines
                # attribute there
                for allowed in var_node.findall(f'.//{{{ns}}}allowedValue'):
                    values.append(allowed.text)
                instance = 0
                self._variables.get(instance)[name] = variable.StateVariable(
                    self, name,
                    'n/a',
                    instance, send_events,
                    data_type, values)
                # we need to do this here, as there we don't get there our
                # {urn:schemas-beebits-net:service-1-0}X_withVendorDefines
                # attribute there
                self._variables.get(instance)[name].has_vendor_values = True

            # print('service parse:', self, self.device)
            self.detection_completed = True
            self.dispatch_event('service_detection_completed',
                                sender=self.device, device=self.device)
            self.info(
                f'send signal Coherence.UPnP.Service.detection_'
                f'completed for {self}')

            # if (self.last_time_updated == None):
            #     if( self.id.endswith('AVTransport') or
            #         self.id.endswith('RenderingControl')):
            #         self.dispatch_event('service_notified',
            #                             sender=self.device, service=self)
            #         self.last_time_updated = time.time()

        def gotError(failure, url):
            self.warning(f'error requesting {url}')
            self.info(f'failure {failure}')
            self.dispatch_event('service_detection_failed',
                                self.device, device=self.device)

        d = utils.getPage(self.get_scpd_url())
        d.addCallbacks(gotPage, gotError, None, None,
                       [self.get_scpd_url()], None)


moderated_variables = \
    {'urn:schemas-upnp-org:service:AVTransport:2': ['LastChange'],
     'urn:schemas-upnp-org:service:AVTransport:1':
         ['LastChange'],
     'urn:schemas-upnp-org:service:ContentDirectory:2':
         ['SystemUpdateID', 'ContainerUpdateIDs'],
     'urn:schemas-upnp-org:service:ContentDirectory:1':
         ['SystemUpdateID', 'ContainerUpdateIDs'],
     'urn:schemas-upnp-org:service:RenderingControl:2':
         ['LastChange'],
     'urn:schemas-upnp-org:service:RenderingControl:1':
         ['LastChange'],
     'urn:schemas-upnp-org:service:ScheduledRecording:1':
         ['LastChange'],
     }


class ServiceServer(log.LogAble):
    logCategory = 'service_server'

    def __init__(self, id, version, backend):
        log.LogAble.__init__(self)
        self.id = id
        self.version = version
        self.backend = backend
        self.debug(f'ServiceServer.__init__: {id} '
                   f'[version: {version}, backend: {backend}]')
        if getattr(self, 'namespace', None) is None:
            self.namespace = 'schemas-upnp-org'
        if getattr(self, 'id_namespace', None) is None:
            self.id_namespace = 'upnp-org'

        self.service_type = \
            f'urn:{self.namespace}:service:{id}:{int(version):d}'
        self.debug(f'\t-service_type: {self.service_type}')

        self.scpdXML = None
        self.scpd_url = b'scpd.xml'
        self.control_url = b'control'
        self.subscription_url = b'subscribe'
        self.event_metadata = ''
        if id == 'AVTransport':
            self.event_metadata = 'urn:schemas-upnp-org:metadata-1-0/AVT/'
        if id == 'RenderingControl':
            self.event_metadata = 'urn:schemas-upnp-org:metadata-1-0/RCS/'
        if id == 'ScheduledRecording':
            self.event_metadata = 'urn:schemas-upnp-org:av:srs-event'

        self._actions = {}
        self._variables = {0: {}}
        self._subscribers = {}

        self._pending_notifications = {}

        self.implementation = None

        self.last_change = None
        self.init_var_and_actions()

        try:
            if 'LastChange' in moderated_variables[self.service_type]:
                self.last_change = self._variables[0]['LastChange']
        except Exception:
            pass
        self.debug(f'ServiceServer.__init__: putChild '
                   f'{self.subscription_url} ...wait')
        self.putChild(  # pylint: disable=no-member
            self.subscription_url, EventSubscriptionServer(self))
        self.debug(f'ServiceServer.__init__: putChild '
                   f'{self.subscription_url} => OK')

        self.check_subscribers_loop = task.LoopingCall(self.check_subscribers)
        self.check_subscribers_loop.start(120.0, now=False)

        self.check_moderated_loop = None
        if self.service_type in moderated_variables:
            self.check_moderated_loop = task.LoopingCall(
                self.check_moderated_variables)
            self.check_moderated_loop.start(0.5, now=False)

    def _release(self):
        for p in list(self._pending_notifications.values()):
            p.disconnect()
        self._pending_notifications = {}

    def get_action(self, action_name):
        try:
            return self._actions[action_name]
        except KeyError:
            return None  # not implemented

    def get_actions(self):
        return self._actions

    def get_variables(self):
        return self._variables

    def get_subscribers(self):
        return self._subscribers

    def rm_notification(self, result, d):
        del self._pending_notifications[d]

    def new_subscriber(self, subscriber):
        notify = []
        for vdict in list(self._variables.values()):
            notify += [v for v in list(vdict.values()) if v.send_events]

        self.info(f'new_subscriber {subscriber} {notify}')
        if len(notify) <= 0:
            return

        root = etree.Element(f'{{{NS_UPNP_ORG_EVENT_1_0}}}propertyset',
                             nsmap={'e': NS_UPNP_ORG_EVENT_1_0})
        evented_variables = 0
        for n in notify:
            e = etree.SubElement(root, f'{{{NS_UPNP_ORG_EVENT_1_0}}}property')
            if n.name == 'LastChange':
                if subscriber['seq'] == 0:
                    text = self.build_last_change_event(n.instance, force=True)
                else:
                    text = self.build_last_change_event(n.instance)
                if text is not None:
                    etree.SubElement(e, n.name).text = text
                    evented_variables += 1
            else:
                etree.SubElement(e, n.name).text = str(n.value)
                evented_variables += 1

        if evented_variables > 0:
            xml = etree.tostring(root, encoding='utf-8', pretty_print=True)
            d, p = event.send_notification(subscriber, xml)
            self._pending_notifications[d] = p
            d.addBoth(self.rm_notification, d)
        self._subscribers[subscriber['sid']] = subscriber

    def get_id(self):
        return self.id

    def get_type(self):
        return self.service_type

    def create_new_instance(self, instance):
        self._variables[instance] = {}
        for v in list(self._variables[0].values()):
            self._variables[instance][v.name] = variable.StateVariable(
                v.service,
                v.name,
                v.implementation,
                instance,
                v.send_events,
                v.data_type,
                v.allowed_values)
            self._variables[instance][
                v.name].has_vendor_values = v.has_vendor_values
            self._variables[instance][v.name].default_value = v.default_value
            # self._variables[instance][v.name].value = v.default_value # FIXME
            self._variables[instance][v.name].old_value = v.old_value
            self._variables[instance][v.name].value = v.value
            self._variables[instance][
                v.name].dependant_variable = v.dependant_variable

    def remove_instance(self, instance):
        if instance == 0:
            return
        del (self._variables[instance])

    def set_variable(self, instance, variable_name, value, default=False):

        def process_value(result):
            variable.update(result)
            if default:
                variable.default_value = variable.value
            if variable.send_events and not variable.moderated and len(
                    self._subscribers) > 0:
                xml = self.build_single_notification(instance, variable_name,
                                                     variable.value)
                for s in list(self._subscribers.values()):
                    d, p = event.send_notification(s, xml)
                    self._pending_notifications[d] = p
                    d.addBoth(self.rm_notification, d)

        try:
            variable = self._variables[int(instance)][variable_name]
            if isinstance(value, defer.Deferred):
                value.addCallback(process_value)
            else:
                process_value(value)
        except KeyError:
            pass

    def get_variable(self, variable_name, instance=0):
        try:
            return self._variables[int(instance)][variable_name]
        except KeyError:
            return None

    def build_single_notification(self, instance, variable_name, value):
        root = etree.Element(f'{{{NS_UPNP_ORG_EVENT_1_0}}}propertyset',
                             nsmap={'e': NS_UPNP_ORG_EVENT_1_0})
        e = etree.SubElement(root, f'{{{NS_UPNP_ORG_EVENT_1_0}}}property')
        etree.SubElement(e, variable_name).text = str(value)
        return etree.tostring(root, encoding='utf-8', pretty_print=True)

    def build_last_change_event(self, instance=0, force=False):
        got_one = False
        root = etree.Element('Event', nsmap={None: self.event_metadata})
        for instance, vdict in list(self._variables.items()):
            e = etree.SubElement(root, 'InstanceID')
            e.attrib['val'] = str(instance)
            for variable in list(vdict.values()):
                if variable.name != 'LastChange' and \
                        variable.name[0:11] != 'A_ARG_TYPE_' and \
                        not variable.never_evented:
                    if variable.updated or force:
                        s = etree.SubElement(e, variable.name)
                        s.attrib['val'] = str(variable.value)
                        variable.updated = False
                        got_one = True
                        if variable.dependant_variable is not None:
                            dependants = variable.dependant_variable.\
                                get_allowed_values()
                            if dependants is not None and len(dependants) > 0:
                                s.attrib['channel'] = dependants[0]
        if got_one:
            return etree.tostring(root, encoding='utf-8', pretty_print=True)
        else:
            return None

    def propagate_notification(self, notify):
        if len(self._subscribers) <= 0:
            return
        if len(notify) <= 0:
            return

        root = etree.Element(f'{{{NS_UPNP_ORG_EVENT_1_0}}}propertyset',
                             nsmap={'e': NS_UPNP_ORG_EVENT_1_0})

        if isinstance(notify, variable.StateVariable):
            notify = [notify, ]

        evented_variables = 0
        for n in notify:
            e = etree.SubElement(root, f'{{{NS_UPNP_ORG_EVENT_1_0}}}property')
            if n.name == 'LastChange':
                text = self.build_last_change_event(instance=n.instance)
                if text is not None:
                    etree.SubElement(e, n.name).text = text
                    evented_variables += 1
            else:
                s = etree.SubElement(e, n.name).text = str(n.value)
                evented_variables += 1
                if n.dependant_variable is not None:
                    dependants = n.dependant_variable.get_allowed_values()
                    if dependants is not None and len(dependants) > 0:
                        e.attrib['channel'] = dependants[0]

        if evented_variables == 0:
            return
        xml = etree.tostring(root, encoding='utf-8', pretty_print=True)

        for s in list(self._subscribers.values()):
            d, p = event.send_notification(s, xml)
            self._pending_notifications[d] = p
            d.addBoth(self.rm_notification, d)

    def check_subscribers(self):
        for s in list(self._subscribers.values()):
            timeout = 86400
            if s['timeout'].startswith('Second-'):
                timeout = int(s['timeout'][len('Second-'):])
            if time.time() > s['created'] + timeout:
                del s

    def check_moderated_variables(self):
        # print(f'check_moderated for {self.id}')
        # print(self._subscribers)
        if len(self._subscribers) <= 0:
            return
        variables = moderated_variables[self.get_type()]
        notify = []
        for v in variables:
            # print self._variables[0][v].name, self._variables[0][v].updated
            for vdict in list(self._variables.values()):
                if vdict[v].updated:
                    vdict[v].updated = False
                    notify.append(vdict[v])
        self.propagate_notification(notify)

    def is_variable_moderated(self, name):
        try:
            variables = moderated_variables[self.get_type()]
            if name in variables:
                return True
        except KeyError:
            pass
        return False

    def simulate_notification(self):
        self.info(f'simulate_notification for {self.id}')
        self.set_variable(0, 'CurrentConnectionIDs', '0')

    def get_scpdXML(self):
        if self.scpdXML is None:
            self.scpdXML = scpdXML(self)
            self.scpdXML = self.scpdXML.build_xml()
        return self.scpdXML

    def register_vendor_variable(self, name, implementation='optional',
                                 instance=0, evented='no',
                                 data_type='string',
                                 dependant_variable=None,
                                 default_value=None,
                                 allowed_values=None, has_vendor_values=False,
                                 allowed_value_range=None,
                                 moderated=False):
        '''
        Enables a backend to add an own, vendor defined,
        :class:`coherence.upnp.core.variable.StateVariable` to the service.

        Args:
            name (str): the name of the new StateVariable
            implementation (str): either 'optional' or 'required'
            instance: the instance number of the service that variable
                      should be assigned to, usually '0'
            evented (str): boolean as string 'yes' 'no' or the special keyword
                           'never' if the variable doesn't show up in a
                           LastChange event too
            data_type (str): `string`, `boolean`, `bin.base64` or
                             various number formats
            dependant_variable (object): the name of another StateVariable that
                                         depends on this one
            default_value (object): the value this StateVariable should have by
                                    default when created for another instance
                                    of in the service
            allowed_values (list): a list of values this StateVariable can have
            has_vendor_values (bool): if there are values outside the
                                      allowed_values list too
            allowed_value_range (dict): a dict of 'minimum','maximum' and
                                        'step' values
            moderated (bool): True if this StateVariable should only be emitted
                              via a LastChange event

        Returns:
            A new variable of class
            :class:`coherence.upnp.core.variable.StateVariable`
        '''
        # FIXME
        # we should raise an Exception when there as a
        # StateVariable with that name already

        if evented == 'never':
            send_events = 'no'
        else:
            send_events = evented
        new_variable = variable.StateVariable(self, name, implementation,
                                              instance, send_events,
                                              data_type, allowed_values)
        if default_value is None:
            new_variable.default_value = ''
        else:
            new_variable.default_value = \
                new_variable.old_value = new_variable.value = default_value

        new_variable.dependant_variable = dependant_variable
        new_variable.has_vendor_values = has_vendor_values
        new_variable.allowed_value_range = allowed_value_range
        new_variable.moderated = moderated
        if evented == 'never':
            new_variable.never_evented = True
        self._variables.get(instance)[name] = new_variable
        return new_variable

    def register_vendor_action(self, name, implementation, arguments=None,
                               needs_callback=True):
        '''
        Enables a backend to add an own, vendor defined, Action to the service.

        Args:
            name (str): the name of the new Action
            implementation (str): either 'optional' or 'required'
            arguments (list): a C{list} if argument C{tuples},
                              like (name,direction,relatedStateVariable)
            needs_callback (bool): this Action needs a method in the backend
                                   or service class

        Returns:
            An action of class :class:`coherence.upnp.core.action.Action`
        '''
        # FIXME: we should raise an Exception when there as an Action
        # with that name already we should raise an Exception when there
        #  is no related StateVariable for an Argument

        # check for action in backend
        callback = getattr(self.backend, f'upnp_{name}', None)

        if callback is None:
            # check for action in ServiceServer
            callback = getattr(self, f'upnp_{name}', None)

        if needs_callback and callback is None:
            # we have one or more 'A_ARG_TYPE_'
            # variables issue a warning for now
            if implementation == 'optional':
                self.info(f'{self.id} has a missing callback for '
                          f'{implementation} action {name}, action disabled')
                return
            else:
                if (hasattr(self, 'implementation') and
                    self.implementation == 'required') or not hasattr(
                        self, 'implementation'):
                    self.warning(
                        f'{self.id} has a missing callback for '
                        f'{implementation} action {name}, service disabled')
                raise LookupError('missing callback')

        arguments_list = []
        for argument in arguments:
            arguments_list.append(
                action.Argument(argument[0], argument[1].lower(), argument[2]))

        new_action = action.Action(self, name, implementation, arguments_list)
        self._actions[name] = new_action
        if callback is not None:
            new_action.set_callback(callback)
            self.info(f'Add callback {callback} for {self.id}/{name}')
        return new_action

    def init_var_and_actions(self):
        desc_file = util.sibpath(
            __file__,
            os.path.join('xml-service-descriptions',
                         f'{self.id}{int(self.version):d}.xml'))
        tree = etree.parse(desc_file)

        for action_node in tree.findall('.//action'):
            name = action_node.findtext('name')
            implementation = 'required'
            needs_callback = False
            if action_node.attrib.get(
                    '{urn:schemas-beebits-net:service-1-0}X_needs_backend',
                    None) is not None:
                needs_callback = True
            if action_node.find('Optional') is not None:
                implementation = 'optional'
                if action_node.find(
                        'Optional').attrib.get(
                    '{urn:schemas-beebits-net:service-1-0}X_needs_backend',
                        None) is not None or action_node.attrib.get(
                    '{urn:schemas-beebits-net:service-1-0}X_needs_backend',
                        None) is not None:
                    needs_callback = True

            arguments = []
            for argument in action_node.findall('.//argument'):
                arg_name = argument.findtext('name')
                arg_direction = argument.findtext('direction')
                arg_state_var = argument.findtext('relatedStateVariable')
                arguments.append(
                    action.Argument(arg_name, arg_direction, arg_state_var))
                if arg_state_var[
                   0:11] == 'A_ARG_TYPE_' and arg_direction == 'out':
                    needs_callback = True

            # check for action in backend
            callback = getattr(self.backend, f'upnp_{name}', None)

            if callback is None:
                # check for action in ServiceServer
                callback = getattr(self, f'upnp_{name}', None)

            if needs_callback and callback is None:
                # we have one or more 'A_ARG_TYPE_'
                # variables issue a warning for now
                if implementation == 'optional':
                    self.info(
                        f'{self.id} has a missing callback for '
                        f'{implementation} action {name}, action disabled')
                    continue
                else:
                    if (hasattr(self, 'implementation') and
                        self.implementation == 'required') or \
                            not hasattr(self, 'implementation'):
                        self.warning(
                            f'{self.id} has a missing callback for '
                            f'{implementation} action {name}, service disabled'
                        )
                    raise LookupError('missing callback')

            new_action = action.Action(self, name, implementation, arguments)
            self._actions[name] = new_action
            if callback is not None:
                new_action.set_callback(callback)
                self.info(f'Add callback {callback} for {self.id}/{name}')

        backend_vendor_value_defaults = getattr(self.backend,
                                                'vendor_value_defaults', None)
        service_value_defaults = None
        if backend_vendor_value_defaults:
            service_value_defaults = backend_vendor_value_defaults.get(self.id,
                                                                       None)

        backend_vendor_range_defaults = getattr(self.backend,
                                                'vendor_range_defaults', None)
        service_range_defaults = None
        if backend_vendor_range_defaults:
            service_range_defaults = backend_vendor_range_defaults.get(self.id)

        for var_node in tree.findall('.//stateVariable'):
            instance = 0
            name = var_node.findtext('name')
            implementation = 'required'
            if action_node.find('Optional') is not None:
                implementation = 'optional'

            send_events = var_node.findtext('sendEventsAttribute')
            data_type = var_node.findtext('dataType')
            values = []
            for allowed in var_node.findall('.//allowedValue'):
                values.append(allowed.text)
            self._variables.get(instance)[name] = \
                variable.StateVariable(self,
                                       name,
                                       implementation,
                                       instance,
                                       send_events,
                                       data_type,
                                       values)

            dependant_variable = var_node.findtext(
                '{urn:schemas-beebits-net:service-1-0}X_dependantVariable')
            if dependant_variable:
                self._variables.get(instance)[
                    name].dependant_variable = dependant_variable
            default_value = var_node.findtext('defaultValue')
            if default_value:
                self._variables.get(instance)[name].set_default_value(
                    default_value)
            if var_node.find('sendEventsAttribute') is not None:
                never_evented = var_node.find(
                    'sendEventsAttribute').attrib.get(
                    '{urn:schemas-beebits-net:service-1-0}X_no_means_never',
                    None)
                if never_evented is not None:
                    self._variables.get(instance)[name].set_never_evented(
                        never_evented)

            allowed_value_list = var_node.find('allowedValueList')
            if allowed_value_list is not None:
                vendor_values = allowed_value_list.attrib.get(
                    '{urn:schemas-beebits-net:service-1-0}X_withVendorDefines',
                    None)
                if service_value_defaults:
                    variable_value_defaults = service_value_defaults.get(name,
                                                                         None)
                    if variable_value_defaults:
                        self.info(f'overwriting {name} default value '
                                  f'with {variable_value_defaults}')
                        self._variables.get(instance)[name].set_allowed_values(
                            variable_value_defaults)

                if vendor_values is not None:
                    self._variables.get(
                        instance)[name].has_vendor_values = True

            allowed_value_range = var_node.find('allowedValueRange')
            if allowed_value_range:
                vendor_values = \
                    allowed_value_range.attrib.get(
                        '{urn:schemas-beebits-net:service-1-0}'
                        'X_withVendorDefines', None)
                range = {}
                for e in list(allowed_value_range):
                    range[e.tag] = e.text
                    if vendor_values is not None:
                        if service_range_defaults:
                            variable_range_defaults = \
                                service_range_defaults.get(name)
                            if (variable_range_defaults is not None and
                                    variable_range_defaults.get(
                                        e.tag) is not None):
                                self.info(
                                    f'overwriting {name} attribute {e.tag} with'  # noqa
                                    f' {str(variable_range_defaults[e.tag])}')
                                range[e.tag] = variable_range_defaults[e.tag]
                            elif e.text is None:
                                self.info(f'missing vendor definition for '
                                          f'{name}, attribute {e.tag}')
                self._variables.get(instance)[name].set_allowed_value_range(
                    **range)
                if vendor_values is not None:
                    self._variables.get(
                        instance)[name].has_vendor_values = True
            elif service_range_defaults:
                variable_range_defaults = service_range_defaults.get(name)
                if variable_range_defaults is not None:
                    self._variables.get(
                        instance)[name].set_allowed_value_range(
                        **variable_range_defaults)
                    self._variables.get(
                        instance)[name].has_vendor_values = True

        for v in list(self._variables.get(0).values()):
            if isinstance(v.dependant_variable, str):
                v.dependant_variable = self._variables.get(instance).get(
                    v.dependant_variable)


class scpdXML(static.Data, log.LogAble):
    logCategory = 'service_scpdxml'

    def __init__(self, server, control=None):
        log.LogAble.__init__(self)
        self.debug(f'scpdXML.__init: {server}  [{control}]')
        self.service_server = server
        self.control = control
        static.Data.__init__(self, b'', 'text/xml')

    def render(self, request):
        if self.data in [None, b'']:
            self.data = self.build_xml()
        return static.Data.render(self, request)

    def build_xml(self):
        self.debug(f'scpdXML.build_xml: {self.service_server}')
        root = etree.Element('scpd',
                             nsmap={None: 'urn:schemas-upnp-org:service-1-0'})
        e = etree.SubElement(root, 'specVersion')
        etree.SubElement(e, 'major').text = '1'
        etree.SubElement(e, 'minor').text = '0'

        e = etree.SubElement(root, 'actionList')
        for action in list(self.service_server._actions.values()):
            s = etree.SubElement(e, 'action')
            etree.SubElement(s, 'name').text = action.get_name()
            al = etree.SubElement(s, 'argumentList')
            for argument in action.get_arguments_list():
                a = etree.SubElement(al, 'argument')
                etree.SubElement(a, 'name').text = argument.get_name()
                etree.SubElement(a, 'direction').text = \
                    argument.get_direction()
                etree.SubElement(a, 'relatedStateVariable').text = \
                    argument.get_state_variable()

        e = etree.SubElement(root, 'serviceStateTable')
        for var in list(self.service_server._variables[0].values()):
            s = etree.SubElement(e, 'stateVariable')
            if var.send_events:
                s.attrib['sendEvents'] = 'yes'
            else:
                s.attrib['sendEvents'] = 'no'
            etree.SubElement(s, 'name').text = var.name
            etree.SubElement(s, 'dataType').text = var.data_type
            if not var.has_vendor_values and len(var.allowed_values):
                v = etree.SubElement(s, 'allowedValueList')
                for value in var.allowed_values:
                    etree.SubElement(v, 'allowedValue').text = value

            if var.allowed_value_range is not None and len(
                    var.allowed_value_range) > 0:
                complete = True
                for name, value in list(var.allowed_value_range.items()):
                    if value is None:
                        complete = False
                if complete:
                    avl = etree.SubElement(s, 'allowedValueRange')
                    for name, value in list(var.allowed_value_range.items()):
                        if value is not None:
                            etree.SubElement(avl, name).text = str(value)

        return etree.tostring(root, encoding='utf-8', xml_declaration=True,
                              pretty_print=True)


from twisted.python.util import OrderedDict


class ServiceControl(log.LogAble):

    def get_action_results(self, result, action, instance):
        '''
        check for out arguments if yes:

            - check if there are related ones to StateVariables with non
              `A_ARG_TYPE_` prefix:

                if yes:

                    - check if there is a call plugin method for this action:

                        - if yes: update StateVariable values with call result
                        - if no:  get StateVariable values and add them to
                          result dict

        Args:
            result (object): The result from an action
            action (object): An instance of class
                :class:`coherence.upnp.core.action.Action`
            instance (object): An instance of
                :class:`coherence.upnp.core.variable.StateVariable`

        Returns:
            An `OrderedDict`.
        '''
        self.debug(f'get_action_results {action.name} {result}')
        r = result
        notify = []
        for argument in action.get_out_arguments():
            # print 'get_state_variable_contents', argument.name
            if argument.name[0:11] != 'A_ARG_TYPE_':
                if action.get_callback() is not None:
                    variable = \
                        self.variables[instance][  # pylint: disable=no-member
                            argument.get_state_variable()]
                    variable.update(r[argument.name])
                    if variable.send_events == 'yes' and \
                            not variable.moderated:
                        notify.append(variable)
                else:
                    variable = \
                        self.variables[instance][  # pylint: disable=no-member
                            argument.get_state_variable()]
                    r[argument.name] = variable.value
            self.service.propagate_notification(  # pylint: disable=no-member
                notify)

        if len(r) == 0:
            return r

        ordered_result = OrderedDict()
        for argument in action.get_out_arguments():
            ordered_result[argument.name] = r[argument.name]
        return ordered_result

    def soap__generic(self, *args, **kwargs):
        '''
        Generic UPnP service control method, which will be used
        if no soap_ACTIONNAME method in the server service control
        class can be found
        '''
        try:
            action = self.actions[  # pylint: disable=no-member
                kwargs['soap_methodName']]
        except KeyError:
            return failure.Failure(errorCode(401))

        try:
            instance = int(kwargs['InstanceID'])
        except Exception:
            instance = 0

        self.info(f'soap__generic {action} {__name__} {kwargs}')
        self.debug(f'\t- action.name {action.name}')
        del kwargs['soap_methodName']
        if ('X_UPnPClient' in kwargs and
                kwargs['X_UPnPClient'] == 'XBox'):
            if (action.name == 'Browse' and
                    'ContainerID' in kwargs):
                # XXX: THIS IS SICK
                kwargs['ObjectID'] = kwargs['ContainerID']
                del kwargs['ContainerID']

        in_arguments = action.get_in_arguments()
        for arg_name, arg in kwargs.items():
            if arg_name.find('X_') == 0:
                continue
            al = [a for a in in_arguments if arg_name == a.get_name()]
            if len(al) > 0:
                in_arguments.remove(al[0])
            else:
                self.critical(
                    f'argument {arg_name} not valid for action {action.name}')
                return failure.Failure(errorCode(402))
        if len(in_arguments) > 0:
            args_names = [a.get_name() for a in in_arguments]
            self.critical(f'argument {args_names} '
                          f'missing for action {action.name}')
            return failure.Failure(errorCode(402))

        def callit(*args, **kwargs):
            # self.debug('callit args', args)
            # self.debug('callit kwargs', kwargs)
            result = {}
            callback = action.get_callback()
            # self.debug('callit callback', callback)
            if callback is not None:
                return callback(**kwargs)
            return result

        def got_error(x):
            # print 'failure', x
            self.info('soap__generic error during call processing')
            return x

        # call plugin method for this action
        d = defer.maybeDeferred(callit, *args, **kwargs)
        d.addCallback(self.get_action_results, action, instance)
        d.addErrback(got_error)
        return d
